import json
import logging

import requests
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from graphql import GraphQLError, OperationType, parse
from graphql.language.ast import OperationDefinitionNode

from gsl_ds_proxy.filters import filter_response
from gsl_ds_proxy.models import ProxyToken

logger = logging.getLogger(__name__)

_ALLOWED_OPERATIONS = {
    "IntrospectionQuery",
    "getDemarche",
    "getDossier",
}

# Read timeout stays below Scalingo's 59s post-first-byte inactivity ceiling.
_DS_TIMEOUT = (5, 55)


def _error_response(message, status):
    return JsonResponse({"errors": [{"message": message}]}, status=status)


def _graphql_error_bytes(message):
    return json.dumps({"errors": [{"message": message}]}).encode()


def _pick_operation(doc, operation_name):
    """Return (OperationDefinitionNode, None) or (None, error_response).

    Mirrors the GraphQL spec's GetOperation algorithm:
    - If operation_name is given, find the definition with that name.
    - Else, require exactly one OperationDefinitionNode in the document.
    """
    operations = [d for d in doc.definitions if isinstance(d, OperationDefinitionNode)]
    if not operations:
        return None, _error_response("Aucune opération dans la requête.", 400)
    if operation_name:
        for op in operations:
            if op.name and op.name.value == operation_name:
                return op, None
        return None, _error_response(
            f"Opération '{operation_name}' introuvable dans la requête.", 400
        )
    if len(operations) > 1:
        return None, _error_response(
            "operationName est requis quand plusieurs opérations sont définies.",
            400,
        )
    return operations[0], None


def _check_operation_allowed(proxy_token, operation_name, variables):
    """Pre-forward validation, based on what we can check without hitting DS."""
    variables = variables or {}
    if operation_name not in _ALLOWED_OPERATIONS:
        return _error_response("Opération non autorisée pour cette démarche.", 403)
    if (
        operation_name == "getDemarche"
        and variables.get("demarcheNumber") != proxy_token.demarche.ds_number
    ):
        return _error_response("Opération non autorisée pour cette démarche.", 403)
    return None


def _scoped_field_present(operation_name, response_data):
    data = (response_data or {}).get("data") or {}
    if operation_name == "getDemarche":
        return isinstance(data.get("demarche"), dict) and "number" in data["demarche"]
    if operation_name == "getDossier":
        dossier = data.get("dossier")
        return (
            isinstance(dossier, dict)
            and isinstance(dossier.get("demarche"), dict)
            and "number" in dossier["demarche"]
        )
    return True


def _check_response_allowed(proxy_token, operation_name, response_data):
    """Post-fetch validation: authoritative check against the DS payload.

    This is the security boundary. The pre-forward check trusts request
    variables, which the caller controls; the only trustworthy scoping
    signal is the data DS actually returned.

    Returns an error message string if the response is out of scope, else None.
    """
    data = (response_data or {}).get("data") or {}

    if operation_name == "getDemarche":
        demarche = data.get("demarche") or {}
        if demarche.get("number") != proxy_token.demarche.ds_number:
            return (
                "Opération non autorisée pour cette démarche. "
                "La requête doit inclure `demarche { number }`."
            )
        return None

    if operation_name == "getDossier":
        dossier = data.get("dossier") or {}
        demarche_number = (dossier.get("demarche") or {}).get("number")
        if demarche_number != proxy_token.demarche.ds_number:
            return (
                "Opération non autorisée pour cette démarche. "
                "La requête doit inclure `dossier { demarche { number } }`."
            )
        return None

    return None


def _forward_to_ds(query, variables, operation_name):
    """Call DS and return (response_data, None) or (None, error_message)."""
    headers = {
        "Authorization": f"Bearer {settings.DS_API_TOKEN}",
        "Content-Type": "application/json",
    }
    ds_payload = {"query": query}
    if variables:
        ds_payload["variables"] = variables
    if operation_name:
        ds_payload["operationName"] = operation_name

    try:
        ds_response = requests.post(
            settings.DS_API_URL,
            json=ds_payload,
            headers=headers,
            timeout=_DS_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        logger.exception("DS proxy: connection error to DS API")
        return None, "Erreur de connexion à Démarches Simplifiées."
    except requests.exceptions.Timeout:
        logger.exception("DS proxy: timeout from DS API")
        return None, "Délai d'attente dépassé pour Démarches Simplifiées."

    try:
        ds_response.raise_for_status()
    except requests.exceptions.HTTPError:
        logger.exception("DS proxy: HTTP %s from DS API", ds_response.status_code)
        return None, "Erreur de Démarches Simplifiées."

    return ds_response.json(), None


@csrf_exempt
@require_POST
def graphql_proxy(request):
    # Auth
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Bearer "):
        return _error_response("Authorization header manquant ou invalide.", 401)

    token_key = auth_header[7:]
    try:
        proxy_token = ProxyToken.objects.prefetch_related("instructeurs").get(
            key_hash=ProxyToken.hash_key(token_key), is_active=True
        )
    except ProxyToken.DoesNotExist:
        return _error_response("Token invalide ou désactivé.", 401)

    # Parse body
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return _error_response("Corps de requête JSON invalide.", 400)

    query = body.get("query", "")
    variables = body.get("variables")

    try:
        doc = parse(query)
    except GraphQLError as exc:
        return _error_response(f"Requête GraphQL invalide : {exc.message}", 400)

    operation, error = _pick_operation(doc, body.get("operationName"))
    if error is not None:
        return error

    if operation.operation is not OperationType.QUERY:
        return _error_response("Les mutations ne sont pas autorisées.", 403)

    operation_name = operation.name.value if operation.name else None

    # Scope check: the token is tied to a single démarche
    error = _check_operation_allowed(proxy_token, operation_name, variables)
    if error is not None:
        return error

    allowed_ids = set(proxy_token.instructeurs.values_list("ds_id", flat=True))
    stream = _stream_ds_response(
        proxy_token, operation_name, query, variables, allowed_ids
    )
    return StreamingHttpResponse(stream, content_type="application/json", status=200)


def _stream_ds_response(proxy_token, operation_name, query, variables, allowed_ids):
    # Send a single whitespace byte immediately to close Scalingo's
    # 30s-to-first-byte window. Leading whitespace is valid JSON.
    yield b" "

    response_data, error_message = _forward_to_ds(query, variables, operation_name)
    if error_message is not None:
        yield _graphql_error_bytes(error_message)
        return

    # If DS itself reported errors and returned no scopable data, forward the
    # upstream response verbatim so the caller can see the real error. There is
    # nothing to scope-check (data is null/absent), so no risk of leaking
    # out-of-scope data.
    if response_data.get("errors") and not _scoped_field_present(
        operation_name, response_data
    ):
        yield json.dumps(response_data).encode()
        return

    scope_error = _check_response_allowed(proxy_token, operation_name, response_data)
    if scope_error is not None:
        yield _graphql_error_bytes(scope_error)
        return

    filtered = filter_response(response_data, allowed_ids)
    yield json.dumps(filtered).encode()


graphql_proxy.login_required = False
