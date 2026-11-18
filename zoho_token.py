import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

_cached_token = None
_token_expires_at = 0


def refresh_access_token():
    global _cached_token, _token_expires_at

    # Reuse cached token if still valid (with 60s buffer)
    if _cached_token and time.time() < (_token_expires_at - 60):
        return _cached_token

    url = os.environ["ZOHO_ACCOUNTS_URL"].rstrip("/") + "/oauth/v2/token"

    payload = {
        "grant_type": "refresh_token",
        "client_id": os.environ["ZOHO_CLIENT_ID"],
        "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
        "refresh_token": os.environ["ZOHO_REFRESH_TOKEN"],
    }

    response = requests.post(url, data=payload, timeout=30)
    result = response.json()

    if not response.ok or "access_token" not in result:
        error = result.get("error", "unknown_error")
        raise RuntimeError(f"Token refresh failed: {error}")

    _cached_token = result["access_token"]
    _token_expires_at = time.time() + int(result.get("expires_in", 3600))
    os.environ["ZOHO_ACCESS_TOKEN"] = _cached_token

    return _cached_token
