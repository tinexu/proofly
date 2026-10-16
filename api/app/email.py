"""Sending email. Development prints messages to the terminal instead."""

import logging
from dataclasses import dataclass
from typing import Protocol

from app.config import get_settings

log = logging.getLogger("proofly.email")


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    def send(self, email: Email) -> None: ...


class ConsoleEmailSender:
    """Prints the email so you can click the link while developing."""

    def send(self, email: Email) -> None:
        divider = "-" * 64
        print(f"\n{divider}\nEMAIL to {email.to}\nSubject: {email.subject}\n\n{email.body}\n{divider}\n", flush=True)


def get_email_sender() -> EmailSender:
    settings = get_settings()
    if settings.email_backend == "console":
        if settings.is_production:
            raise RuntimeError("The console email backend can't be used in production.")
        return ConsoleEmailSender()
    raise RuntimeError(f"Unknown email backend: {settings.email_backend!r}")


def magic_link_email(to: str, link: str, ttl_minutes: int) -> Email:
    body = (
        "Use this link to sign in to Proofly:\n\n"
        f"{link}\n\n"
        f"It works once and expires in {ttl_minutes} minutes.\n"
        "If you didn't ask to sign in, you can ignore this email. Nobody can sign in without the link."
    )
    return Email(to=to, subject="Your Proofly sign-in link", body=body)