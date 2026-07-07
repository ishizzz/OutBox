"""Send approved emails through Gmail SMTP with the resume attached.

Uses a Gmail App Password (Google Account > Security > 2-Step Verification
> App passwords). Never your normal password.
"""

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from .resume import resume_attachment_path


def send_email(to_email, subject, body):
    address = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not address or not app_password:
        raise RuntimeError("GMAIL_ADDRESS or GMAIL_APP_PASSWORD missing from .env.")

    msg = EmailMessage()
    msg["From"] = address
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    resume_path = Path(resume_attachment_path())
    if resume_path.exists():
        data = resume_path.read_bytes()
        if resume_path.suffix.lower() == ".pdf":
            maintype, subtype = "application", "pdf"
        else:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(data, maintype=maintype, subtype=subtype,
                           filename=resume_path.name)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(address, app_password)
        smtp.send_message(msg)
