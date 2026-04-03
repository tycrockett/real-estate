from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _get_twilio_client():
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        return None, "Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env"
    from twilio.rest import Client
    return Client(account_sid, auth_token), None


def get_twilio_number() -> str:
    return os.environ.get("TWILIO_PHONE_NUMBER", "")


def send_sms(to: str, body: str) -> dict:
    """Send an SMS via Twilio. Returns {success, sid, error}."""
    client, err = _get_twilio_client()
    if err:
        return {"success": False, "error": err}

    from_number = get_twilio_number()
    if not from_number:
        return {"success": False, "error": "Set TWILIO_PHONE_NUMBER in .env"}

    try:
        message = client.messages.create(
            body=body,
            from_=from_number,
            to=to,
        )
        return {"success": True, "sid": message.sid, "status": message.status}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_sendgrid_config() -> tuple[str, str]:
    api_key = os.environ.get("SENDGRID_API_KEY", "")
    from_email = os.environ.get("SENDGRID_FROM_EMAIL", "")
    return api_key, from_email


def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email via SendGrid. Returns {success, message_id, error}."""
    api_key, from_email = get_sendgrid_config()
    if not api_key:
        return {"success": False, "error": "Set SENDGRID_API_KEY in .env"}
    if not from_email:
        return {"success": False, "error": "Set SENDGRID_FROM_EMAIL in .env"}

    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    try:
        message = Mail(
            from_email=from_email,
            to_emails=to,
            subject=subject,
            plain_text_content=body,
        )
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        return {
            "success": response.status_code in (200, 201, 202),
            "status_code": response.status_code,
            "message_id": response.headers.get("X-Message-Id", ""),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
