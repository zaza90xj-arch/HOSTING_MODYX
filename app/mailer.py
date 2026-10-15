"""E-mail delivery. SMTP when configured; otherwise the message is logged (development only)."""
import smtplib
from email.message import EmailMessage


def send_mail(app, to, subject, body):
    mode = app.config["MAIL_MODE"]
    if mode == "memory":  # used by the automated tests
        app.extensions.setdefault("outbox", []).append({"to": to, "subject": subject, "body": body})
        return True
    if mode == "console":
        app.logger.warning("[DEV MAIL - SMTP not configured] to=%s subject=%s\n%s", to, subject, body)
        return True
    msg = EmailMessage()
    msg["From"] = app.config["MAIL_FROM"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(app.config["SMTP_HOST"], app.config["SMTP_PORT"], timeout=10) as s:
            if app.config["SMTP_TLS"]:
                s.starttls()
            if app.config["SMTP_USER"]:
                s.login(app.config["SMTP_USER"], app.config["SMTP_PASSWORD"])
            s.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001 - never leak SMTP details to the user
        app.logger.error("SMTP send failed: %s", exc)
        return False
