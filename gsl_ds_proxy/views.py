import json
import logging
import time
import uuid

import requests
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from graphql import GraphQLError, OperationType, parse
from graphql.language.ast import FieldNode, OperationDefinitionNode

from gsl_ds_proxy.filters import filter_response
from gsl_ds_proxy.models import ProxyToken
from gsl_ds_proxy.query_guard import validate_demarche_selections

logger = logging.getLogger(__name__)

_INTROSPECTION_FIELDS = {"__schema", "__type", "__typename"}
_BUSINESS_FIELDS = {"demarche", "dossier"}
_ALLOWED_ROOT_FIELDS = _BUSINESS_FIELDS | _INTROSPECTION_FIELDS
_INTROSPECTION_SENTINEL = "__introspection__"

# Same three connections as filters._filter_dossier_nodes; kept in sync so the
# pre/post counts in the per-request log match what filter_response actually
# touched.
_DEMARCHE_DOSSIER_CONNECTIONS = (
    "dossiers",
    "pendingDeletedDossiers",
    "deletedDossiers",
)

# Read timeout stays below Scalingo's 59s post-first-byte inactivity ceiling.
_DS_TIMEOUT = (5, 55)


def _error_entry(message, request_id):
    return {"message": message, "extensions": {"requestId": request_id}}


def _count_dossiers(response_data, root_field):
    """Total dossiers in a DS response, summed across all connections.

    Returns None for introspection (not applicable).
    """
    if root_field == _INTROSPECTION_SENTINEL:
        return None
    data = (response_data or {}).get("data") or {}
    if root_field == "demarche":
        demarche = data.get("demarche")
        if not isinstance(demarche, dict):
            return 0
        total = 0
        for field in _DEMARCHE_DOSSIER_CONNECTIONS:
            connection = demarche.get(field)
            if isinstance(connection, dict):
                nodes = connection.get("nodes")
                if isinstance(nodes, list):
                    total += len(nodes)
        return total
    if root_field == "dossier":
        dossier = data.get("dossier")
        if isinstance(dossier, dict) and "number" in dossier:
            return 1
        return 0
    return None


def _error_response(message, status, request_id):
    return JsonResponse({"errors": [_error_entry(message, request_id)]}, status=status)


def _graphql_error_bytes(message, request_id):
    return json.dumps({"errors": [_error_entry(message, request_id)]}).encode()


def _pick_operation(doc, operation_name, request_id):
    """Return (OperationDefinitionNode, None) or (None, error_response).

    Mirrors the GraphQL spec's GetOperation algorithm:
    - If operation_name is given, find the definition with that name.
    - Else, require exactly one OperationDefinitionNode in the document.
    """
    operations = [d for d in doc.definitions if isinstance(d, OperationDefinitionNode)]
    if not operations:
        return None, _error_response(
            "Aucune opération dans la requête.", 400, request_id
        )
    if operation_name:
        for op in operations:
            if op.name and op.name.value == operation_name:
                return op, None
        return None, _error_response(
            f"Opération '{operation_name}' introuvable dans la requête.",
            400,
            request_id,
        )
    if len(operations) > 1:
        return None, _error_response(
            "operationName est requis quand plusieurs opérations sont définies.",
            400,
            request_id,
        )
    return operations[0], None


def _root_field(operation, request_id):
    """Return (root_field, None) or (None, error_response).

    Inspects the operation's top-level selection set and identifies which
    schema field the caller is querying. Operation names are caller-defined
    labels with no semantic meaning, so the root field is the trustworthy
    signal for scoping decisions.

    Rules:
    - All root selections must be plain FieldNodes (no fragment spreads or
      inline fragments at the root — they'd hide the actual field name from
      this check).
    - Aliases are forbidden on root fields, since downstream scope checks
      and the response filter look up `data["demarche"]` / `data["dossier"]`
      by the schema name.
    - At most one business field (demarche/dossier) per operation; mixing
      business and introspection fields is rejected.
    - Pure introspection returns the _INTROSPECTION_SENTINEL.
    """
    selections = operation.selection_set.selections
    field_names = []
    for sel in selections:
        if not isinstance(sel, FieldNode):
            return None, _error_response(
                "Les fragments à la racine de l'opération ne sont pas autorisés.",
                403,
                request_id,
            )
        if sel.alias is not None:
            return None, _error_response(
                "Les alias sur les champs racine ne sont pas autorisés.",
                403,
                request_id,
            )
        if sel.name.value not in _ALLOWED_ROOT_FIELDS:
            return None, _error_response(
                "Opération non autorisée pour cette démarche.", 403, request_id
            )
        field_names.append(sel.name.value)

    business = [n for n in field_names if n in _BUSINESS_FIELDS]
    if len(business) > 1:
        return None, _error_response(
            "Une seule opération métier est autorisée à la racine.",
            403,
            request_id,
        )
    if business:
        introspection = [n for n in field_names if n in _INTROSPECTION_FIELDS]
        if introspection:
            return None, _error_response(
                "Mélanger introspection et opération métier n'est pas autorisé.",
                403,
                request_id,
            )
        return business[0], None

    return _INTROSPECTION_SENTINEL, None


def _check_root_field_allowed(proxy_token, root_field, variables, request_id):
    """Pre-forward validation, based on what we can check without hitting DS."""
    variables = variables or {}
    if (
        root_field == "demarche"
        and variables.get("demarcheNumber") != proxy_token.demarche.ds_number
    ):
        return _error_response(
            "Opération non autorisée pour cette démarche.", 403, request_id
        )
    return None


def _scoped_field_present(root_field, response_data):
    if root_field == _INTROSPECTION_SENTINEL:
        return True
    data = (response_data or {}).get("data") or {}
    if root_field == "demarche":
        return isinstance(data.get("demarche"), dict) and "number" in data["demarche"]
    if root_field == "dossier":
        dossier = data.get("dossier")
        return (
            isinstance(dossier, dict)
            and isinstance(dossier.get("demarche"), dict)
            and "number" in dossier["demarche"]
        )
    return True


def _check_response_allowed(proxy_token, root_field, response_data):
    """Post-fetch validation: authoritative check against the DS payload.

    This is the security boundary. The pre-forward check trusts request
    variables, which the caller controls; the only trustworthy scoping
    signal is the data DS actually returned.

    Returns an error message string if the response is out of scope, else None.
    """
    if root_field == _INTROSPECTION_SENTINEL:
        return None

    data = (response_data or {}).get("data") or {}

    if root_field == "demarche":
        demarche = data.get("demarche") or {}
        if demarche.get("number") != proxy_token.demarche.ds_number:
            return (
                "Opération non autorisée pour cette démarche. "
                "La requête doit inclure `demarche { number }`."
            )
        return None

    if root_field == "dossier":
        dossier = data.get("dossier") or {}
        demarche_number = (dossier.get("demarche") or {}).get("number")
        if demarche_number != proxy_token.demarche.ds_number:
            return (
                "Opération non autorisée pour cette démarche. "
                "La requête doit inclure `dossier { demarche { number } }`."
            )
        return None

    return None


def _forward_to_ds(
    query, variables, operation_name, proxy_token, request_id
) -> tuple[dict | None, str | None, int]:
    """Call DS and return (response_data, None, elapsed_ms)
    or (None, error_message, elapsed_ms)."""
    headers = {
        "Authorization": f"Bearer {settings.DS_API_TOKEN}",
        "Content-Type": "application/json",
    }
    ds_payload = {"query": query}
    if variables:
        ds_payload["variables"] = variables
    if operation_name:
        ds_payload["operationName"] = operation_name

    log_extra = {
        "request_id": request_id,
        "proxy_token_id": proxy_token.id,
        "demarche_number": proxy_token.demarche.ds_number,
    }

    started_at = time.monotonic()
    try:
        ds_response = requests.post(
            settings.DS_API_URL,
            json=ds_payload,
            headers=headers,
            timeout=_DS_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        log_extra["elapsed_ms"] = elapsed_ms
        logger.exception("DS proxy: connection error to DS API", extra=log_extra)
        return None, "Erreur de connexion à Démarches Simplifiées.", elapsed_ms
    except requests.exceptions.Timeout:
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        log_extra["elapsed_ms"] = elapsed_ms
        logger.exception("DS proxy: timeout from DS API", extra=log_extra)
        return None, "Délai d'attente dépassé pour Démarches Simplifiées.", elapsed_ms

    elapsed_ms = int((time.monotonic() - started_at) * 1000)

    try:
        ds_response.raise_for_status()
    except requests.exceptions.HTTPError:
        log_extra["elapsed_ms"] = elapsed_ms
        log_extra["ds_status"] = ds_response.status_code
        logger.exception(
            "DS proxy: HTTP %s from DS API",
            ds_response.status_code,
            extra=log_extra,
        )
        return None, "Erreur de Démarches Simplifiées.", elapsed_ms

    return ds_response.json(), None, elapsed_ms


def _resolve_token(request, request_id):
    """Return (proxy_token, None) or (None, error_response)."""
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Bearer "):
        return None, _error_response(
            "Authorization header manquant ou invalide.", 401, request_id
        )

    token_key = auth_header[7:]
    try:
        proxy_token = ProxyToken.objects.get(
            key_hash=ProxyToken.hash_key(token_key), is_active=True
        )
    except ProxyToken.DoesNotExist:
        return None, _error_response("Token invalide ou désactivé.", 401, request_id)

    if not proxy_token.groupe_instructeur_ds_id:
        return None, _error_response("Token non configuré.", 403, request_id)

    return proxy_token, None


@csrf_exempt
@require_POST
def graphql_proxy(request):
    request_id = uuid.uuid4().hex

    proxy_token, error = _resolve_token(request, request_id)
    if error is not None:
        return error

    # Parse body
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return _error_response("Corps de requête JSON invalide.", 400, request_id)

    query = body.get("query", "")
    variables = body.get("variables")

    try:
        doc = parse(query)
    except GraphQLError as exc:
        return _error_response(
            f"Requête GraphQL invalide : {exc.message}", 400, request_id
        )

    operation, error = _pick_operation(doc, body.get("operationName"), request_id)
    if error is not None:
        return error

    if operation.operation is not OperationType.QUERY:
        return _error_response("Les mutations ne sont pas autorisées.", 403, request_id)

    root_field, error = _root_field(operation, request_id)
    if error is not None:
        return error

    operation_name = operation.name.value if operation.name else None

    # Scope check: the token is tied to a single démarche
    error = _check_root_field_allowed(proxy_token, root_field, variables, request_id)
    if error is not None:
        return error

    forbidden_field = validate_demarche_selections(doc, operation)
    if forbidden_field is not None:
        return _error_response(
            f"Champ démarche non autorisé : `{forbidden_field}`.", 403, request_id
        )

    allowed_groupe_ds_id = proxy_token.groupe_instructeur_ds_id
    stream = _stream_ds_response(
        proxy_token,
        root_field,
        operation_name,
        query,
        variables,
        allowed_groupe_ds_id,
        request_id,
    )
    return StreamingHttpResponse(stream, content_type="application/json", status=200)


def _stream_ds_response(
    proxy_token,
    root_field,
    operation_name,
    query,
    variables,
    allowed_groupe_ds_id,
    request_id,
):
    # Send a single whitespace byte immediately to close Scalingo's
    # 30s-to-first-byte window. Leading whitespace is valid JSON.
    yield b" "

    response_data, error_message, elapsed_ms = _forward_to_ds(
        query, variables, operation_name, proxy_token, request_id
    )
    if error_message is not None:
        yield _graphql_error_bytes(error_message, request_id)
        return

    def _log_request(*, outcome, filtered=None):
        original = _count_dossiers(response_data, root_field)
        extra = {
            "request_id": request_id,
            "proxy_token_id": proxy_token.id,
            "demarche_number": proxy_token.demarche.ds_number,
            "operation_name": operation_name,
            "root_field": root_field,
            "elapsed_ms": elapsed_ms,
            "ds_errors_count": len(response_data.get("errors") or []),
            "outcome": outcome,
        }
        if original is not None:
            post = _count_dossiers(filtered, root_field) if filtered is not None else 0
            extra["ds_results_count"] = original
            extra["filtered_out_count"] = original - post
        logger.info("DS proxy: request", extra=extra)

    # If DS itself reported errors and returned no scopable data, forward the
    # upstream response verbatim so the caller can see the real error. There is
    # nothing to scope-check (data is null/absent), so no risk of leaking
    # out-of-scope data. We prepend a marker error carrying our request_id so
    # the partner can correlate with our server logs.
    if response_data.get("errors") and not _scoped_field_present(
        root_field, response_data
    ):
        forwarded = dict(response_data)
        forwarded["errors"] = [
            _error_entry("Erreur Démarches Simplifiées transmise.", request_id),
            *response_data["errors"],
        ]
        _log_request(outcome="verbatim_forward", filtered=response_data)
        yield json.dumps(forwarded).encode()
        return

    scope_error = _check_response_allowed(proxy_token, root_field, response_data)
    if scope_error is not None:
        # Preserve any upstream DS errors so the caller still sees what DS
        # signalled (e.g. partial Timeout on PersonneMorale.entreprise rows)
        # alongside our own scope rejection.
        upstream_errors = response_data.get("errors") or []
        payload = {
            "data": None,
            "errors": [*upstream_errors, _error_entry(scope_error, request_id)],
        }
        _log_request(outcome="scope_error")
        yield json.dumps(payload).encode()
        return

    filtered = filter_response(response_data, allowed_groupe_ds_id)
    _log_request(outcome="ok", filtered=filtered)
    yield json.dumps(filtered).encode()


graphql_proxy.login_required = False
