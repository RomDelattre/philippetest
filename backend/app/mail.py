"""Connecteur d'envoi des mails (section 4) : une interface, plusieurs implémentations.
L'expéditeur est Philippe (F-52). Aucun mail ne part sans validation (P2) : seul l'écran
« Mails à valider » appelle ce module."""

import smtplib
import uuid
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Protocol

from app.config import Settings, get_settings


class MailError(RuntimeError):
    pass


class MailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


def _message(sender: str, to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1] or "planning.local")
    msg.set_content(body)
    return msg


class FileMailSender:
    """Développement : chaque mail est écrit dans un fichier .eml."""

    def __init__(self, directory: str, sender: str) -> None:
        self.directory, self.sender = Path(directory), sender

    def send(self, to: str, subject: str, body: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{uuid.uuid4()}.eml"
        path.write_bytes(bytes(_message(self.sender, to, subject, body)))


class SmtpMailSender:
    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_host:
            raise MailError("SMTP_HOST n'est pas configuré")
        self.s = settings

    def send(self, to: str, subject: str, body: str) -> None:
        try:
            with smtplib.SMTP(self.s.smtp_host or "", self.s.smtp_port, timeout=30) as smtp:
                if self.s.smtp_starttls:
                    smtp.starttls()
                if self.s.smtp_user:
                    smtp.login(self.s.smtp_user, self.s.smtp_password or "")
                smtp.send_message(_message(self.s.mail_from, to, subject, body))
        except (OSError, smtplib.SMTPException) as exc:
            raise MailError(f"Échec d'envoi SMTP : {exc}") from exc


class DisabledMailSender:
    def send(self, to: str, subject: str, body: str) -> None:
        raise MailError("L'envoi de mails est désactivé (MAIL_BACKEND=disabled)")


def get_mail_sender() -> MailSender:
    s = get_settings()
    if s.mail_backend == "smtp":
        return SmtpMailSender(s)
    if s.mail_backend == "disabled":
        return DisabledMailSender()
    return FileMailSender(s.mail_file_dir, s.mail_from)
