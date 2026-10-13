"""The only code that talks to the outside world. Tests replace these two functions."""

import ipaddress
import json
import smtplib
import socket
import ssl
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.core.config import settings

TIMEOUT = 15


class IntegrationError(Exception):
    """Safe to show to the user."""


def check_public_host(host: str) -> None:
    """Block tenant-supplied hosts that point inside our network (SSRF)."""
    if settings.allow_private_hosts:
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise IntegrationError(f"Cannot resolve host '{host}'")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise IntegrationError("That host is not allowed (private or local address)")


def send_email(cfg: dict, to: str, subject: str, body: str) -> str:
    """cfg: host, port, security (starttls|ssl|none), username, password, from_email, from_name. Returns the message id."""
    check_public_host(cfg["host"])
    msg = EmailMessage()
    try:
        msg["Subject"] = " ".join(subject.split())
        msg["From"] = formataddr((cfg.get("from_name") or "", cfg["from_email"]))
        msg["To"] = to
        msg["Message-ID"] = make_msgid(domain=cfg["from_email"].rsplit("@", 1)[-1])
    except ValueError as e:
        raise IntegrationError(f"Invalid email header: {e}")
    msg.set_content(body)
    try:
        if cfg.get("security") == "ssl":
            smtp = smtplib.SMTP_SSL(cfg["host"], int(cfg["port"]), timeout=TIMEOUT, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=TIMEOUT)
        with smtp:
            if cfg.get("security") == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if cfg.get("username"):
                smtp.login(cfg["username"], cfg.get("password", ""))
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise IntegrationError("The mail server rejected the username or password")
    except smtplib.SMTPRecipientsRefused:
        raise IntegrationError("The mail server refused the recipient address")
    except (smtplib.SMTPException, OSError) as e:
        raise IntegrationError(f"Could not send through the mail server: {str(e)[:150]}")
    return msg["Message-ID"]


def post_slack(webhook_url: str, text: str) -> None:
    req = urllib.request.Request(
        webhook_url, data=json.dumps({"text": text[:3000]}).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 (host is restricted to hooks.slack.com)
            if r.status >= 300:
                raise IntegrationError(f"Slack answered {r.status}")
    except IntegrationError:
        raise
    except Exception as e:
        raise IntegrationError(f"Could not reach Slack: {str(e)[:150]}")
