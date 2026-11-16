
import os
import requests
from dotenv import load_dotenv, set_key

load_dotenv(override=True)

ENV_FILE = os.path.join(
    os.path.dirname(__file__), ".env"
)


def refresh_access_token():
    url = (
        os.environ["ZOHO_ACCOUNTS_URL"].rstrip("/")
        + "/oauth/v2/token"
    )

    payload = {
        "grant_type": "refresh_token",
        "client_id": os.environ["ZOHO_CLIENT_ID"],
        "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
        "refresh_token": os.environ["ZOHO_REFRESH_TOKEN"]
    }

    response = requests.post(
        url,
        data=payload,
        timeout=30
    )

    result = response.json()

    if not response.ok or "access_token" not in result:
        error = result.get("error", "unknown_error")
        raise RuntimeError(
            f"Token refresh failed: {error}"
        )

    new_token = result["access_token"]

    # Save new token to .env
    set_key(
        ENV_FILE,
        "ZOHO_ACCESS_TOKEN",
        new_token
    )

    os.environ["ZOHO_ACCESS_TOKEN"] = new_token

    print("Zoho access token refreshed successfully!")

    return new_token


if __name__ == "__main__":
    refresh_access_token()
