import os
import httpx


def _build_auth_headers(request):
    auth_header = request.headers.get("Authorization")
    headers = {}

    if auth_header:
        headers["Authorization"] = auth_header

    headers["Content-Type"] = "application/json"
    return headers


def fetch_incident_context(request, incident_id):
    if not incident_id:
        return None

    base_url = os.getenv("INCIDENT_SERVICE_URL", "http://localhost:8002")
    url = f"{base_url}/api/incidents/{incident_id}/"

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, headers=_build_auth_headers(request))
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return {
            "fetch_error": f"Failed to fetch incident context: {str(e)}",
            "incident_id": incident_id,
        }


def fetch_site_context(request, nodeb_name):
    if not nodeb_name:
        return None

    base_url = os.getenv("KPI_SERVICE_URL", "http://localhost:8001")
    url = f"{base_url}/api/cartography/site/{nodeb_name}/"

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, headers=_build_auth_headers(request))
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return {
            "fetch_error": f"Failed to fetch site context: {str(e)}",
            "nodeb_name": nodeb_name,
        }