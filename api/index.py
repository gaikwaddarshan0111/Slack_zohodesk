import os
import sys


# Ensure root directory is in Python path so `bot`, `zoho_ticket`, and `zoho_token` import cleanly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

# Import your existing helper functions from bot.py
from bot import (
    logger,
    get_slack_thread_description,
    build_ticket_modal,
    build_status_modal,
    create_zoho_ticket,
)

# process_before_response=True is required for serverless platforms like Vercel
bolt_app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
    process_before_response=True,
)


def ack_shortcut(ack):
    ack()


def run_shortcut(body, client):
    try:
        loading_view = build_status_modal(
            title="Zoho Desk Ticket",
            message="Fetching Slack conversation...",
        )
        opened = client.views_open(
            trigger_id=body["trigger_id"],
            view=loading_view,
        )
        view_id = opened["view"]["id"]

        description = get_slack_thread_description(body)
        ticket_view = build_ticket_modal(description=description)

        client.views_update(view_id=view_id, view=ticket_view)
    except Exception:
        logger.exception("Unexpected shortcut error")


# Lazy listener: acknowledges Slack immediately, then fetches history & updates modal
bolt_app.shortcut("create_zoho_ticket")(ack=ack_shortcut, lazy=[run_shortcut])


def ack_submission(ack):
    ack(
        response_action="update",
        view=build_status_modal(
            title="Creating Ticket",
            message="Creating your Zoho Desk ticket...",
        ),
    )


def run_submission(body, view, client):
    values = view["state"]["values"]
    subject = values["subject_block"]["subject"]["value"]
    description = values["description_block"]["description"]["value"]
    email = values["email_block"]["email"]["value"]
    priority = values["priority_block"]["priority"]["selected_option"]["value"]

    try:
        result = create_zoho_ticket(
            subject=subject,
            description=description,
            email=email,
            priority=priority,
        )

        if result:
            ticket_number = result.get("ticketNumber", "N/A")
            ticket_id = result.get("id", "N/A")
            ticket_url = result.get("webUrl")

            message = (
                "*Ticket created successfully!*\n\n"
                f"*Ticket Number:* {ticket_number}\n"
                f"*Ticket ID:* {ticket_id}\n"
                f"*Priority:* {priority}"
            )
            if ticket_url:
                message += f"\n\n<{ticket_url}|Open in Zoho Desk>"
        else:
            message = (
                ":warning: *Ticket creation failed.*\n"
                "Check Vercel logs for the Zoho Desk API error."
            )
    except Exception:
        logger.exception("Zoho Desk ticket creation error")
        message = (
            ":warning: *Unable to create ticket.*\n"
            "Please check the Vercel application logs."
        )

    client.views_update(
        view_id=view["id"],
        view=build_status_modal(title="Zoho Desk Result", message=message),
    )


bolt_app.view("ticket_modal")(ack=ack_submission, lazy=[run_submission])

app = FastAPI()
handler = SlackRequestHandler(bolt_app)


@app.post("/slack/events")
async def slack_events(req: Request):
    return await handler.handle(req)


@app.get("/")
async def health():
    return {"status": "Slack Zoho Desk Bot is running on Vercel"}
