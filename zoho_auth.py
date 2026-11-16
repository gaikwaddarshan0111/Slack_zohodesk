
import os
import requests
from dotenv import load_dotenv, set_key

load_dotenv(override=True)

url = "https://accounts.zoho.eu/oauth/v2/token"

payload = {
    "grant_type": "authorization_code",
    "client_id": os.environ["ZOHO_CLIENT_ID"],
    "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
    "code": os.environ["ZOHO_AUTH_CODE"]
}

response = requests.post(
    url,
    data=payload,
    timeout=30
)

result = response.json()

if response.ok and "access_token" in result:
    print("Zoho OAuth authentication successful!")

    access_token = result["access_token"]
    refresh_token = result.get("refresh_token")

    set_key(".env", "ZOHO_ACCESS_TOKEN", access_token)

    if refresh_token:
        set_key(".env", "ZOHO_REFRESH_TOKEN", refresh_token)
        print("Refresh token saved successfully.")
    else:
        print("No refresh token returned.")

    print("Access token saved successfully.")
    print("Expires in:", result.get("expires_in"), "seconds")

    # Authorization code is single-use.
    set_key(".env", "ZOHO_AUTH_CODE", "")

else:
    print("Zoho OAuth failed.")
    print("Error:", result.get("error", response.status_code))
    print("Description:", result.get("error_description", ""))
