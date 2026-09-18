from __future__ import annotations

from app.enums import AuditAction
from app.models import AuditEvent, Document, User, utcnow
from app.schemas import AuditEventOut


def record_event(
    *,
    document: Document,
    actor: User,
    action: AuditAction,
    from_status: str | None,
    to_status: str | None,
    note: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        document_id=document.id,
        firm_id=document.firm_id,
        actor=actor.name,
        actor_role=actor.role,
        action=action.value,
        from_status=from_status,
        to_status=to_status,
        note=note,
        created_at=utcnow(),
    )
    return event


def format_event(event: AuditEvent, document_label: str) -> str:
    """Human-readable lines matching the brief's example timeline."""
    time = event.created_at.strftime("%I:%M %p").lstrip("0")
    actor = event.actor
    if event.action == AuditAction.UPLOADED.value:
        return f"{time} — {actor} uploaded {document_label}"
    if event.action == AuditAction.REUPLOADED.value:
        return f"{time} — {actor} uploaded revised document."
    if event.action == AuditAction.STARTED_REVIEW.value:
        return f"{time} — {actor} started reviewing {document_label}"
    if event.action == AuditAction.REQUESTED_CORRECTION.value:
        reason = event.note or ""
        return f"{time} — {actor} requested correction. Reason: {reason}"
    if event.action == AuditAction.APPROVED.value:
        return f"{time} — {actor} approved {document_label}"
    if event.action == AuditAction.CREATED.value:
        return f"{time} — {actor} created {document_label} ({event.to_status})"
    if event.action == AuditAction.DELETED.value:
        return f"{time} — {actor} deleted {document_label}"
    if event.action == AuditAction.VERSION_DELETED.value:
        return f"{time} — {actor} deleted file {event.note or document_label}"
    return f"{time} — {actor} ({event.actor_role}) {event.action} {document_label}"


def to_audit_out(event: AuditEvent, document_label: str) -> AuditEventOut:
    return AuditEventOut(
        id=event.id,
        document_id=event.document_id,
        document_label=document_label,
        firm_id=event.firm_id,
        actor=event.actor,
        actor_role=event.actor_role,
        action=event.action,
        from_status=event.from_status,
        to_status=event.to_status,
        note=event.note,
        created_at=event.created_at,
        display_text=format_event(event, document_label),
    )
