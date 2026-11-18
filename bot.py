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

app = App(token=os.environ["SLACK_BOT_TOKEN"])

# Read conversation history using an authorized Slack user token.
slack_user_client = WebClient(token=os.environ["SLACK_USER_TOKEN"])


# ------------------------------------------
# 2. Build Description from Slack Conversation
# ------------------------------------------

MAX_DESCRIPTION_LENGTH = 3000
MAX_REPLIES = 5
MAX_CHAT_MESSAGES = 5



def get_slack_thread_description(body):
    """Return thread context, or recent top-level messages ending at selection."""
    channel_id = body["channel"]["id"]
    selected_message = body["message"]
    selected_ts = selected_message["ts"]

    # Some parent messages have thread_ts equal to their own ts.
    is_reply = (
        bool(selected_message.get("thread_ts"))
        and selected_message["thread_ts"] != selected_ts
    )
    is_thread_parent = int(selected_message.get("reply_count") or 0) > 0
    is_thread = is_reply or is_thread_parent

    try:
        if is_thread:
            logger.info("MODE: Slack Thread")
            thread_ts = selected_message.get("thread_ts") or selected_ts
            messages = []
            cursor = None

            # Read a bounded number of pages to avoid very long waits.
            for _ in range(10):
                params = {"channel": channel_id, "ts": thread_ts, "limit": 100}
                if cursor:
                    params["cursor"] = cursor

                response = slack_user_client.conversations_replies(**params)
                messages.extend(response.get("messages", []))
                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

            messages.sort(key=lambda message: float(message["ts"]))
            if not messages:
                return selected_message.get("text", "")[:MAX_DESCRIPTION_LENGTH]

            parent = next((m for m in messages if m["ts"] == thread_ts), messages[0])
            replies = [m for m in messages if m["ts"] != parent["ts"]]
            parts = ["Original Slack Message:", parent.get("text", "").strip()]

            recent_replies = [m.get("text", "").strip() for m in replies[-MAX_REPLIES:]]
            recent_replies = [text for text in recent_replies if text]
            if recent_replies:
                parts.extend(["Latest Thread Replies:", *recent_replies])

            if cursor:
                parts.append("[Thread was too long to retrieve completely.]")

        else:
            logger.info("MODE: Regular Slack Conversation")
            messages = [selected_message]
            cursor = None

            # Earlier messages only: don't include messages posted after selection.
            for _ in range(5):
                if len(messages) >= MAX_CHAT_MESSAGES:
                    break

                params = {
                    "channel": channel_id,
                    "latest": selected_ts,
                    "inclusive": False,
                    "limit": 100,
                }
                if cursor:
                    params["cursor"] = cursor

                response = slack_user_client.conversations_history(**params)
                for msg in response.get("messages", []):
                    # Only top-level human-authored text, no system events.
                    if msg.get("subtype") or not msg.get("text", "").strip():
                        continue
                    if msg.get("thread_ts") and msg["thread_ts"] != msg["ts"]:
                        continue
                    if msg["ts"] == selected_ts:
                        continue
                    messages.append(msg)
                    if len(messages) >= MAX_CHAT_MESSAGES:
                        break

                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

            messages.sort(key=lambda message: float(message["ts"]))
            parts = ["Recent Slack Conversation:"]
            parts.extend(m["text"].strip() for m in messages if m.get("text", "").strip())

        description = "\n\n".join(parts)
        if len(description) > MAX_DESCRIPTION_LENGTH:
            description = "[Earlier conversation truncated]\n\n" + description[-2900:]
        logger.info("Description generated (%d characters)", len(description))
        return description

    except SlackApiError as error:
        logger.error("Slack conversation retrieval failed: %s", error.response.get("error"))
        return selected_message.get("text", "")[:MAX_DESCRIPTION_LENGTH]


# ------------------------------------------
# 3. Slack Ticket Modal Builder
# ------------------------------------------

def build_ticket_modal(description=""):
    """Build the redesigned, Slack-native ticket creation form."""
    description_element = {
        "type": "plain_text_input",
        "action_id": "description",
        "multiline": True,
        "max_length": MAX_DESCRIPTION_LENGTH,
        "placeholder": {
            "type": "plain_text",
            "text": "Enter or review the issue description"
        }
    }
    if description:
        description_element["initial_value"] = description[:MAX_DESCRIPTION_LENGTH]

    return {
        "type": "modal",
        "callback_id": "ticket_modal",
        "title": {"type": "plain_text", "text": "Create Support Ticket"},
        "submit": {"type": "plain_text", "text": "Create Ticket"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        ":ticket: *Zoho Desk Support*\n"
                        "Create a support ticket from this Slack conversation."
                    )
                }
            },
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": (
                        ":information_source: *Conversation auto-filled.* "
                        "Review and edit the details before creating the ticket."
                    )
                }]
            },
            {"type": "divider"},
            {
                "type": "input",
                "block_id": "subject_block",
                "label": {"type": "plain_text", "text": "Ticket Subject"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "subject",
                    "max_length": 200,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g. SMS History not visible in Zoho CRM"
                    }
                }
            },
            {
                "type": "input",
                "block_id": "description_block",
                "label": {"type": "plain_text", "text": "Conversation Description"},
                "hint": {
                    "type": "plain_text",
                    "text": "Auto-filled from Slack. Editable before submission."
                },
                "element": description_element
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Ticket Details*"}
            },
            {
                "type": "input",
                "block_id": "email_block",
                "label": {"type": "plain_text", "text": "Customer Email"},
                "element": {
                    "type": "email_text_input",
                    "action_id": "email",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "customer@example.com"
                    }
                }
            },
            {
                "type": "input",
                "block_id": "priority_block",
                "label": {"type": "plain_text", "text": "Ticket Priority"},
                "element": {
                    "type": "static_select",
                    "action_id": "priority",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select ticket priority"
                    },
                    "initial_option": {
                        "text": {"type": "plain_text", "text": "Medium"},
                        "value": "Medium"
                    },
                    "options": [
                        {
                            "text": {"type": "plain_text", "text": priority},
                            "value": priority
                        }
                        for priority in ["High", "Medium", "Low"]
                    ]
                }
            },
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": ":office: *Department:* Ayon (configured in Zoho Desk)"
                }]
            },
            {"type": "divider"},
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": (
                        ":lock: Remove unrelated or sensitive content "
                        "from the description before submitting."
                    )
                }]
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
                "Fetching Slack conversation..."
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
            "Conversation description retrieved. "
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
