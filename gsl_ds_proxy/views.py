import json
import logging

import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from gsl_ds_proxy.filters import filter_response
from gsl_ds_proxy.models import ProxyToken

logger = logging.getLogger(__name__)


def _error_response(message, status):
    return JsonResponse({"errors": [{"message": message}]}, status=status)


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
    operation_name = body.get("operationName")

    # Reject mutations
    stripped = query.lstrip()
    if stripped.startswith("mutation") or "\nmutation" in query:
        return _error_response("Les mutations ne sont pas autorisées.", 403)

    # Forward to DS
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
            settings.DS_API_URL, json=ds_payload, headers=headers
        )
        ds_response.raise_for_status()
    except requests.exceptions.ConnectionError:
        logger.error("DS proxy: connection error to DS API")
        return _error_response("Erreur de connexion à Démarches Simplifiées.", 502)
    except requests.exceptions.HTTPError:
        logger.error("DS proxy: HTTP %s from DS API", ds_response.status_code)
        return _error_response("Erreur de Démarches Simplifiées.", 502)

    response_data = ds_response.json()

    # Filter
    allowed_ids = set(proxy_token.instructeurs.values_list("ds_id", flat=True))
    filtered = filter_response(response_data, allowed_ids)

    return JsonResponse(filtered)


graphql_proxy.login_required = False
