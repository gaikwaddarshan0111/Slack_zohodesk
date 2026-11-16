
import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

API_URL = os.environ["ZOHO_DESK_API_URL"]
ORG_ID = os.environ["ZOHO_ORG_ID"]
ACCESS_TOKEN = os.environ["ZOHO_ACCESS_TOKEN"]

headers = {
    "Authorization": f"Zoho-oauthtoken {ACCESS_TOKEN}",
    "orgId": ORG_ID
}

url = f"{API_URL}/departments"

try:
    response = requests.get(
        url,
        headers=headers,
        params={"limit": 100},
        timeout=30
    )

    print("HTTP Status:", response.status_code)

    if response.ok:
        departments = response.json().get("data", [])

        print("\nZoho Desk Departments:")
        print("----------------------------")

        for department in departments:
            print("Name:", department.get("name"))
            print("Department ID:", department.get("id"))
            print("Enabled:", department.get("isEnabled"))
            print("----------------------------")

        if not departments:
            print("No departments returned.")
    else:
        # Do not print authentication tokens or headers.
        error = response.json()
        print("Error Code:", error.get("errorCode", error.get("error")))
        print("Message:", error.get("message"))

except requests.exceptions.RequestException as exc:
    print("Connection failed:", type(exc).__name__)
