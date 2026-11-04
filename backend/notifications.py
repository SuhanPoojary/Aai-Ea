import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def send_notification(
    recipient: str,
    subject: str,
    body: str,
    *,
    transport=None,
) -> bool:
    """Send an email when SMTP is configured; return false without affecting persistence."""
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", username)
    if transport is None and not all((host, username, password, sender, recipient)):
        logger.info("Notification skipped because SMTP is not configured.")
        return False
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    try:
        if transport is not None:
            transport(message)
        else:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(username, password)
                smtp.send_message(message)
        logger.info("Notification delivered.")
        return True
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("Notification delivery failed: %s", type(exc).__name__)
        return False
