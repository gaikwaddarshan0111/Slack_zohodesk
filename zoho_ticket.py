
import os
import requests
from dotenv import load_dotenv
from zoho_token import refresh_access_token

load_dotenv(override=True)


def create_zoho_ticket(subject, description, email, priority):
    # Get a fresh access token
    access_token = refresh_access_token()

    url = (
        os.environ["ZOHO_DESK_API_URL"].rstrip("/")
        + "/tickets"
    )

    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "orgId": os.environ["ZOHO_ORG_ID"],
        "Content-Type": "application/json"
    }

    payload = {
        "subject": subject,
        "description": description,
        "departmentId": os.environ["ZOHO_DEPARTMENT_ID"],
        "contact": {
            "email": email
        },
        "priority": priority
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=30
    )

    result = response.json()

    print("HTTP Status:", response.status_code)

    if response.ok:
        print("Ticket created successfully!")
        print("Ticket Number:", result.get("ticketNumber"))
        print("Ticket ID:", result.get("id"))
        print("Ticket URL:", result.get("webUrl"))
        return result

    print("Ticket creation failed.")
    print("Error Code:", result.get("errorCode", result.get("error")))
    print("Message:", result.get("message"))

    return None


if __name__ == "__main__":
    create_zoho_ticket(
        subject="Slack Bot Integration Test",
        description="Test ticket created using Python API.",
        email=os.environ["ZOHO_TEST_EMAIL"],
        priority="Low"
    )
