
import os
import logging

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from zoho_ticket import create_zoho_ticket


# ------------------------------------------
# 1. Environment Configuration
# ------------------------------------------

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App(
    token=os.environ["SLACK_BOT_TOKEN"]
)

# User token for reading Slack channel threads
slack_user_client = WebClient(
    token=os.environ["SLACK_USER_TOKEN"]
)


# ------------------------------------------
# 2. Fetch Slack Thread Description
# ------------------------------------------

def get_slack_thread_description(body):

    channel_id = body["channel"]["id"]
    selected_message = body["message"]

    thread_ts = (
        selected_message.get("thread_ts")
        or selected_message["ts"]
    )

    messages = []
    cursor = None

    try:
        while True:

            params = {
                "channel": channel_id,
                "ts": thread_ts,
                "limit": 100
            }

            if cursor:
                params["cursor"] = cursor

            response = (
                slack_user_client.conversations_replies(
                    **params
                )
            )

            messages.extend(
                response.get("messages", [])
            )

            cursor = (
                response.get("response_metadata", {})
                .get("next_cursor")
            )

            if not cursor:
                break

        if not messages:
            return selected_message.get(
                "text", ""
            )[:3000]

        # Sort messages chronologically
        messages.sort(
            key=lambda msg: float(msg["ts"])
        )

        parent = messages[0]
        replies = messages[1:]

        # Get latest 5 replies
        latest_replies = replies[-5:]

        description = (
            "Original Slack Message:\n"
            + parent.get("text", "")
        )

        if latest_replies:

            description += (
                "\n\nLatest Thread Replies:\n"
            )

            for reply in latest_replies:

                text = reply.get(
                    "text", ""
                ).strip()

                if text:
                    description += f"\n\n {text}"
                

        # Slack text input limit
        return description[:3000]

    except SlackApiError as error:

        logger.error(
            "Thread retrieval failed: %s",
            error.response.get("error")
        )

        # Fallback to selected message
        return selected_message.get(
            "text", ""
        )[:3000]


# ------------------------------------------
# 3. Slack Ticket Modal Builder
# ------------------------------------------

def build_ticket_modal(description=""):

    description_element = {
        "type": "plain_text_input",
        "action_id": "description",
        "multiline": True
    }

    if description:
        description_element["initial_value"] = (
            description[:3000]
        )

    return {
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

            # Subject
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

            # Description
            {
                "type": "input",
                "block_id": "description_block",

                "label": {
                    "type": "plain_text",
                    "text": "Description"
                },

                "element": description_element
            },

            # Customer Email
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

            # Priority
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
                                "text": priority
                            },

                            "value": priority
                        }

                        for priority in [
                            "High",
                            "Medium",
                            "Low"
                        ]
                    ]
                }
            }
        ]
    }


# ------------------------------------------
# 4. Loading / Result Modal
# ------------------------------------------

def build_status_modal(title, message):

    return {
        "type": "modal",

        "title": {
            "type": "plain_text",
            "text": title
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


# ------------------------------------------
# 5. Slack Message Shortcut
# ------------------------------------------

@app.shortcut("create_zoho_ticket")
def create_ticket(ack, body, client):

    # Acknowledge Slack immediately
    ack()

    try:

        # First open a loading modal
        loading_view = build_status_modal(
            title="Zoho Desk Ticket",
            message=(
                "Fetching the latest "
                "Slack thread messages..."
            )
        )

        opened = client.views_open(
            trigger_id=body["trigger_id"],
            view=loading_view
        )

        view_id = opened["view"]["id"]

        logger.info(
            "Slack ticket modal opened."
        )

        # Fetch the original message and replies
        description = (
            get_slack_thread_description(body)
        )

        logger.info(
            "Thread description retrieved. "
            "Length: %s characters",
            len(description)
        )

        # Create final form with description
        ticket_view = build_ticket_modal(
            description=description
        )

        # Replace loading modal with ticket form
        response = client.views_update(
            view_id=view_id,
            view=ticket_view
        )

        logger.info(
            "Modal update successful: %s",
            response["ok"]
        )

        # Verify description in Slack response
        for block in response["view"]["blocks"]:

            if (
                block.get("block_id")
                == "description_block"
            ):

                populated_value = (
                    block["element"].get(
                        "initial_value", ""
                    )
                )

                logger.info(
                    "Prefilled description length: %s",
                    len(populated_value)
                )

                break

        logger.info(
            "Ticket form displayed successfully."
        )

    except SlackApiError as error:

        logger.error(
            "Slack shortcut API error: %s",
            error.response.get("error")
        )

    except Exception:

        logger.exception(
            "Unexpected shortcut error"
        )


# ------------------------------------------
# 6. Handle Ticket Form Submission
# ------------------------------------------

@app.view("ticket_modal")
def handle_ticket_submission(
    ack,
    body,
    view,
    client
):

    logger.info(
        "Slack ticket form submitted."
    )

    values = view["state"]["values"]

    subject = (
        values["subject_block"]
        ["subject"]["value"]
    )

    description = (
        values["description_block"]
        ["description"]["value"]
    )

    email = (
        values["email_block"]
        ["email"]["value"]
    )

    priority = (
        values["priority_block"]
        ["priority"]["selected_option"]["value"]
    )

    # Keep modal open with processing status
    ack(
        response_action="update",
        view=build_status_modal(
            title="Creating Ticket",
            message=(
                "Creating your "
                "Zoho Desk ticket..."
            )
        )
    )

    logger.info(
        "Processing ticket request from Slack."
    )

    try:

        # Send request to Zoho Desk EU
        result = create_zoho_ticket(
            subject=subject,
            description=description,
            email=email,
            priority=priority
        )

        if result:

            ticket_number = result.get(
                "ticketNumber", "N/A"
            )

            ticket_id = result.get(
                "id", "N/A"
            )

            ticket_url = result.get(
                "webUrl"
            )

            message = (
                "*Ticket created successfully!*\n\n"
                f"*Ticket Number:* {ticket_number}\n"
                f"*Ticket ID:* {ticket_id}\n"
                f"*Priority:* {priority}"
            )

            if ticket_url:
                message += (
                    f"\n\n<{ticket_url}|Open in Zoho Desk>"
                )

            logger.info(
                "Zoho Desk ticket created: %s",
                ticket_number
            )

        else:

            message = (
                ":warning: *Ticket creation failed.*\n"
                "Check the Python terminal for "
                "the Zoho Desk API error."
            )

    except Exception:

        logger.exception(
            "Zoho Desk ticket creation error"
        )

        message = (
            ":warning: *Unable to create ticket.*\n"
            "Please check the application logs."
        )

    # Display final result in Slack
    try:

        response = client.views_update(
            view_id=view["id"],
            view=build_status_modal(
                title="Zoho Desk Result",
                message=message
            )
        )

        logger.info(
            "Ticket result modal updated: %s",
            response["ok"]
        )

    except SlackApiError as error:

        logger.error(
            "Result modal update failed: %s",
            error.response.get("error")
        )


# ------------------------------------------
# 7. Start Slack Bot
# ------------------------------------------

if __name__ == "__main__":

    print("Slack Zoho Desk Bot is running...")

    SocketModeHandler(
        app,
        os.environ["SLACK_APP_TOKEN"]
    ).start()
