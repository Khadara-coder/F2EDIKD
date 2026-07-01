"""BI BOT rejection email service.

Subject format:
  [BI BOT][{REJECTION_CODE}][DEPT {DEPT}] {FILENAME} (corr={CORRELATION_ID})

All SMTP credentials come from environment variables — nothing is hardcoded.
Required env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD.
Optional: SMTP_FROM (default: TEAM.BI@fr.bosch.com)
          REJECTION_EMAIL_TO (default: botrejet.Commandes@fr.bosch.com)
"""
from __future__ import annotations

import logging
import os
import smtplib
import textwrap
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from . import rejection_catalog as rc  # type: ignore

log = logging.getLogger("edifact.email_service")

_DEFAULT_FROM = "TEAM.BI@fr.bosch.com"
_DEFAULT_TO   = "botrejet.Commandes@fr.bosch.com"


@dataclass
class RejectionContext:
    """All fields needed to render a BI BOT rejection email."""
    rejection_code: str
    filename: str
    correlation_id: str
    pdf_hash: str = ""
    order_key: str = ""
    selected_soldto: str = ""
    selected_shipto: str = ""
    buyer_sap: str = ""
    dp_sap: str = ""
    failed_node: str = ""
    error_detail: str = ""
    dept: str = "NA"
    extra_recipients: list[str] = field(default_factory=list)


def _dept_from_postal(postal: str) -> str:
    """Extract French departement prefix from a postal code (first 2 digits)."""
    digits = "".join(c for c in postal if c.isdigit())
    return digits[:2] if len(digits) >= 2 else "NA"


def build_subject(ctx: RejectionContext) -> str:
    """Render the BI BOT email subject line."""
    return (
        f"[BI BOT][{ctx.rejection_code}][DEPT {ctx.dept}]"
        f" {ctx.filename} (corr={ctx.correlation_id})"
    )


def build_body(ctx: RejectionContext) -> str:
    """Render the BI BOT email body from *ctx*."""
    entry = rc.get(ctx.rejection_code)
    action = rc.action_text(ctx.rejection_code, lang="fr")
    retry_txt   = "Oui" if entry["retry_allowed"]         else "Non"
    review_txt  = "Oui" if entry["manual_review_required"] else "Non"

    return textwrap.dedent(f"""
    Bonjour,

    Le traitement automatique BI BOT / EDIFACT Generator n'a pas pu finaliser cette commande.

    Résumé
    - Code rejet        : {ctx.rejection_code}
    - Motif             : {entry["message_fr"]}
    - Sévérité          : {entry["severity"]}
    - Statut métier     : {entry["business_status"]}
    - Retry autorisé    : {retry_txt}
    - Revue manuelle    : {review_txt}

    Document
    - Fichier PDF       : {ctx.filename}
    - Numéro commande   : {ctx.order_key or "(non extrait)"}
    - Correlation ID    : {ctx.correlation_id}
    - PDF hash          : {ctx.pdf_hash or "(non disponible)"}

    Résolution partenaire
    - SOLD-TO sélectionné : {ctx.selected_soldto or "(non résolu)"}
    - SHIP-TO sélectionné : {ctx.selected_shipto or "(non résolu)"}
    - Buyer SAP           : {ctx.buyer_sap or "(non résolu)"}
    - DP SAP              : {ctx.dp_sap   or "(non résolu)"}

    Diagnostic
    - Nœud / étape en erreur : {ctx.failed_node  or "(inconnu)"}
    - Détail technique       : {ctx.error_detail or "(aucun)"}

    Action attendue
    {action}

    Cordialement,
    BI BOT - EDIFACT Generator
    """).strip()


def send_rejection_email(
    ctx: RejectionContext,
    dry_run: bool = False,
) -> bool:
    """Send the BI BOT rejection email for *ctx*.

    Returns True if sent (or dry-run), False on delivery failure.
    Never raises — all errors are logged.
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", os.environ.get("SMTP_USERNAME", ""))
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    from_addr = os.environ.get("SMTP_FROM", _DEFAULT_FROM)
    to_addr   = os.environ.get("REJECTION_EMAIL_TO", _DEFAULT_TO)

    recipients = [to_addr] + ctx.extra_recipients

    subject = build_subject(ctx)
    body    = build_body(ctx)

    if dry_run:
        log.info("[DRY RUN] Would send rejection email:\n  To: %s\n  Subject: %s", recipients, subject)
        return True

    if not smtp_host:
        log.warning("SMTP_HOST not configured — rejection email NOT sent (code=%s, file=%s)",
                    ctx.rejection_code, ctx.filename)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_addr
        msg["To"]      = ", ".join(recipients)
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            if smtp_user and smtp_pass:
                server.starttls()
                server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, recipients, msg.as_string())

        log.info("Rejection email sent: %s -> %s", subject, recipients)
        return True

    except Exception as exc:
        log.error("Rejection email delivery failed (%s): %s", ctx.rejection_code, exc)
        return False
