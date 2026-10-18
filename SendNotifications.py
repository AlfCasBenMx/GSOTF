"""Optional SMTP notifications. Credentials come from the environment."""
from email.message import EmailMessage
import json
import os
import smtplib
import ssl
import HandlingEvents as events
import StartSettings


def sendErrorAlert(step, detail):
    sender = os.environ.get("GDF_SMTP_USER")
    password = os.environ.get("GDF_SMTP_PASSWORD")
    recipient = os.environ.get("GDF_SMTP_TO")
    if not all((sender, password, recipient)):
        events.logEvent("SMTP alert skipped: SMTP configuration missing")
        return False
    message = EmailMessage()
    message["From"], message["To"] = sender, recipient
    message["Subject"] = "GDF alert: " + str(step)
    message.set_content(json.dumps({"Cliente": getattr(StartSettings, "myClient", ""),
        "Estacion": getattr(StartSettings, "myStation", ""),
        "Bomba": getattr(StartSettings, "myPump", ""), "Accion": step, "Detalle": detail}, ensure_ascii=False))
    try:
        with smtplib.SMTP(os.environ.get("GDF_SMTP_HOST", "smtp-mail.outlook.com"), 587, timeout=10) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(sender, password)
            server.send_message(message)
        return True
    except Exception:
        events.setup_logging().exception("SMTP alert failed")
        return False


def sendResetWarning(reason):
    return sendErrorAlert("Restart requested", reason)
