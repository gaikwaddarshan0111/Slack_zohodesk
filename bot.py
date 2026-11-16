
import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from zoho_ticket import create_zoho_ticket

load_dotenv()

print("Bot token prefix:", os.getenv("SLACK_BOT_TOKEN", "")[:5])
print("App token prefix:", os.getenv("SLACK_APP_TOKEN", "")[:5])

app = App(token=os.environ["SLACK_BOT_TOKEN"])


# Handle Slack message shortcut
@app.shortcut("create_zoho_ticket")
def create_ticket(ack, body, client):
    ack()

    client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "ticket_modal",
            "title": {
                "type": "plain_text",
                "text": "Zoho Desk Ticket"
            },
            "submit": {
                "type": "plain_text",
                "text": "Create Ticket"
            },
            "close": {
                "type": "plain_text",
                "text": "Close"
            },
            "blocks": [
                {
                    "type": "input",
                    "block_id": "subject_block",
                    "label": {
                        "type": "plain_text",
                        "text": "Subject"
                    },
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "subject"
                    }
                },
                {
                    "type": "input",
                    "block_id": "description_block",
                    "label": {
                        "type": "plain_text",
                        "text": "Description"
                    },
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "description",
                        "multiline": True
                    }
                },
                {
                    "type": "input",
                    "block_id": "email_block",
                    "label": {
                        "type": "plain_text",
                        "text": "Customer Email"
                    },
                    "element": {
                        "type": "email_text_input",
                        "action_id": "email"
                    }
                },
                {
                    "type": "input",
                    "block_id": "priority_block",
                    "label": {
                        "type": "plain_text",
                        "text": "Priority"
                    },
                    "element": {
                        "type": "static_select",
                        "action_id": "priority",
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": p
                                },
                                "value": p
                            }
                            for p in ["High", "Medium", "Low"]
                        ]
                    }
                }
            ]
        }
    )


# Handle form submission

@app.view("ticket_modal")
def handle_ticket_submission(ack, body, view, client):
    values = view["state"]["values"]

    subject = values["subject_block"]["subject"]["value"]
    description = values["description_block"]["description"]["value"]
    email = values["email_block"]["email"]["value"]
    priority = (
        values["priority_block"]["priority"]
        ["selected_option"]["value"]
    )

    # Acknowledge immediately and show a progress message.
    ack(
        response_action="update",
        view={
            "type": "modal",
            "title": {
                "type": "plain_text",
                "text": "Creating Ticket"
            },
            "close": {
                "type": "plain_text",
                "text": "Close"
            },
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "plain_text",
                        "text": "Creating your Zoho Desk ticket..."
                    }
                }
            ]
        }
    )

    try:
        result = create_zoho_ticket(
            subject=subject,
            description=description,
            email=email,
            priority=priority
        )

        if result:
            ticket_number = result.get("ticketNumber", "N/A")
            ticket_id = result.get("id", "N/A")
            ticket_url = result.get("webUrl")

            message = (
                f"Ticket #{ticket_number} created successfully!\n"
                f"Ticket ID: {ticket_id}"
            )

            if ticket_url:
                message += f"\n<{ticket_url}|Open in Zoho Desk>"

            print(f"Created Zoho Desk ticket #{ticket_number}")

        else:
            message = (
                "Ticket creation failed. "
                "Check the Python terminal for the API error."
            )

    except Exception as exc:
        print("Ticket creation error:", type(exc).__name__)
        message = (
            "Unable to create the ticket. "
            "Please check the Python terminal."
        )

    # Replace the progress message with the final result.
    client.views_update(
        view_id=view["id"],
        view={
            "type": "modal",
            "title": {
                "type": "plain_text",
                "text": "Zoho Desk Result"
            },
            "close": {
                "type": "plain_text",
                "text": "Close"
            },
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                }
            ]
        }
    )


if __name__ == "__main__":
    print("Slack Zoho Desk Bot is running...")

    SocketModeHandler(
        app,
        os.environ["SLACK_APP_TOKEN"]
    ).start()