from __future__ import annotations

import json
from typing import Any

import requests

import config
import db


def resend_send(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    if not config.RESEND_API_KEY:
        return False, "RESEND_API_KEY no configurado"
    payload: dict[str, Any] = {
        "from": config.EMAIL_FROM,
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    if config.EMAIL_REPLY_TO:
        payload["reply_to"] = [config.EMAIL_REPLY_TO]
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {config.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload),
            timeout=config.EMAIL_API_TIMEOUT_SECONDS,
        )
        if 200 <= resp.status_code < 300:
            return True, resp.text[:1000]
        return False, f"HTTP {resp.status_code}: {resp.text[:1000]}"
    except Exception as exc:
        return False, str(exc)


def send_email(to_email: str, subject: str, body: str) -> tuple[bool, str, str]:
    if not config.EMAIL_ENABLED:
        return True, "disabled", "EMAIL_ENABLED=false; correo no enviado"
    if config.EMAIL_PROVIDER == "resend_api":
        ok, msg = resend_send(to_email, subject, body)
        return ok, "resend_api", msg
    return False, config.EMAIL_PROVIDER, "Proveedor no soportado. Usa EMAIL_PROVIDER=resend_api"


def process_outbox(max_items: int | None = None) -> dict[str, int]:
    max_items = max_items or config.EMAIL_PROCESS_MAX_PER_RUN
    rows = db.execute(
        """
        SELECT id, recipient, subject, body
        FROM email_outbox
        WHERE status='queued'
        ORDER BY created_at ASC
        LIMIT %s
        """,
        (max_items,),
        fetch="all",
    ) or []
    sent = errors = 0
    for row in rows:
        ok, provider, response = send_email(row["recipient"], row["subject"], row["body"])
        if ok:
            status = "sent"
            sent += 1
        else:
            status = "error"
            errors += 1
        db.execute(
            """
            UPDATE email_outbox
            SET status=%s, provider=%s, provider_response=%s, processed_at=now()
            WHERE id=%s
            """,
            (status, provider, response, row["id"]),
        )
    return {"processed": len(rows), "sent": sent, "errors": errors}


def queue_email(user_id: int, recipient: str, kind: str, subject: str, body: str, dedupe_key: str | None) -> bool:
    row = db.execute(
        """
        INSERT INTO email_outbox(user_id, recipient, kind, subject, body, dedupe_key, status)
        VALUES (%s,%s,%s,%s,%s,%s,'queued')
        ON CONFLICT(dedupe_key) DO NOTHING
        RETURNING id
        """,
        (user_id, recipient, kind, subject, body, dedupe_key),
        fetch="one",
    )
    return bool(row)
