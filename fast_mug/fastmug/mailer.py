"""Send reports to the flight surgeon over SMTP."""
from __future__ import annotations

import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QThread, Signal

KEYRING_SERVICE = "FAST-ug-smtp"


def get_password(cfg: Dict) -> str:
    """Prefer the OS keychain when the optional `keyring` package is present."""
    user = cfg.get("username", "")
    try:
        import keyring  # noqa: WPS433
        pw = keyring.get_password(KEYRING_SERVICE, user) if user else None
        if pw:
            return pw
    except Exception:  # noqa: BLE001
        pass
    return cfg.get("password", "")


def store_password(cfg: Dict, password: str) -> bool:
    """Returns True if the password went to the OS keychain (and not to settings.json)."""
    user = cfg.get("username", "")
    try:
        import keyring  # noqa: WPS433
        if user:
            keyring.set_password(KEYRING_SERVICE, user, password)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _connect(cfg: Dict, timeout: float = 25.0):
    host, port = cfg.get("host", ""), int(cfg.get("port", 465))
    security = (cfg.get("security") or "SSL").upper()
    ctx = ssl.create_default_context()
    if security == "SSL":
        server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx)
    else:
        server = smtplib.SMTP(host, port, timeout=timeout)
        server.ehlo()
        if security == "STARTTLS":
            server.starttls(context=ctx)
            server.ehlo()
    user = cfg.get("username", "")
    if user:
        server.login(user, get_password(cfg))
    return server


def test_connection(cfg: Dict) -> str:
    server = _connect(cfg)
    try:
        server.noop()
    finally:
        server.quit()
    return "Connected to %s and signed in." % cfg.get("host")


def build_message(cfg: Dict, subject: str, body: str, attachments: List[Path],
                  to: Optional[str] = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = cfg.get("sender") or cfg.get("username")
    msg["To"] = to or cfg.get("flight_surgeon")
    if cfg.get("cc"):
        msg["Cc"] = cfg["cc"]
    msg["Subject"] = subject
    msg.set_content(body)
    for path in attachments:
        ctype, _ = mimetypes.guess_type(str(path))
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        with open(path, "rb") as fh:
            msg.add_attachment(fh.read(), maintype=maintype, subtype=subtype, filename=path.name)
    return msg


def send(cfg: Dict, msg: EmailMessage) -> None:
    if not msg["To"]:
        raise ValueError("No flight surgeon address set. Add one in Settings > Ground link.")
    server = _connect(cfg)
    try:
        server.send_message(msg)
    finally:
        server.quit()


def summary_body(session: Dict) -> str:
    v = session["verdict"]
    crew = session.get("crew", {})
    lines = [
        "%s for %s" % (session.get("type_title", "Exam"), crew.get("name", "crew member")),
        "Started: %s" % session.get("started_utc", ""),
        "Result: %s" % v["headline"],
        "",
    ]
    side = session.get("weaker_side")
    if side and v["neuro_status"] in ("watch", "alert"):
        lines.append("Weaker side on paired measures: %s" % ("left" if side == "L" else "right"))
    words = {"ok": "within baseline", "watch": "watch", "alert": "ALERT", "na": "not measured"}
    for dk, d in v["domains"].items():
        lines.append("  %-14s %s" % (d["name"], words.get(d["status"], d["status"])))
    lines += ["", "Recommended actions:"] + ["  - " + r for r in v["recommendations"]]
    sr = session.get("self_report") or {}
    if sr.get("symptoms"):
        lines += ["", "Reported symptoms: " + ", ".join(sr["symptoms"])]
    lines += ["", "The full report with charts and images is attached.",
              "Screening and decision support only, not a diagnosis."]
    return "\n".join(lines)


class MailWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, cfg: Dict, msg: EmailMessage, parent=None):
        super().__init__(parent)
        self.cfg, self.msg = cfg, msg

    def run(self) -> None:
        try:
            send(self.cfg, self.msg)
            self.done.emit(True, "Sent to %s" % self.msg["To"])
        except Exception as exc:  # noqa: BLE001
            self.done.emit(False, _friendly(exc))


class TestWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, cfg: Dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg

    def run(self) -> None:
        try:
            self.done.emit(True, test_connection(self.cfg))
        except Exception as exc:  # noqa: BLE001
            self.done.emit(False, _friendly(exc))


def _friendly(exc: Exception) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return ("The mail server rejected the username or password. For Gmail, create an app "
                "password (Google account > Security > App passwords) and use it here.")
    if isinstance(exc, (TimeoutError, OSError)) and "timed out" in str(exc).lower():
        return "The mail server did not answer. Check the host, port and network link."
    return "%s: %s" % (type(exc).__name__, exc)
