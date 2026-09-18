from __future__ import annotations

from sqlalchemy import text

from app.enums import AuditAction, DocumentStatus
from app.models import AuditEvent, DocumentVersion
from fastapi.testclient import TestClient


def test_audit_events_update_blocked(engine, seeded):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audit_events
                (document_id, firm_id, actor, actor_role, action, from_status, to_status, note, created_at)
                VALUES (:doc, :firm, 'Rohit', 'staff', 'created', NULL, 'Pending', NULL, '2026-09-18 10:00:00')
                """
            ),
            {"doc": seeded["doc_a"].id, "firm": seeded["firm_a"].id},
        )
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id FROM audit_events LIMIT 1")).fetchone()
        assert row is not None
        try:
            conn.execute(
                text("UPDATE audit_events SET note = 'tamper' WHERE id = :id"),
                {"id": row[0]},
            )
            conn.commit()
            raised = False
        except Exception as exc:
            raised = True
            assert "append-only" in str(exc).lower()
        assert raised, "UPDATE on audit_events should be blocked by trigger"


def test_audit_events_delete_blocked(engine, seeded):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audit_events
                (document_id, firm_id, actor, actor_role, action, from_status, to_status, note, created_at)
                VALUES (:doc, :firm, 'Rohit', 'staff', 'created', NULL, 'Pending', NULL, '2026-09-18 10:00:00')
                """
            ),
            {"doc": seeded["doc_a"].id, "firm": seeded["firm_a"].id},
        )
    with engine.connect() as conn:
        try:
            conn.execute(text("DELETE FROM audit_events"))
            conn.commit()
            raised = False
        except Exception as exc:
            raised = True
            assert "append-only" in str(exc).lower()
        assert raised, "DELETE on audit_events should be blocked by trigger"


def test_each_transition_creates_one_audit_event(client: TestClient, seeded, db):
    rohit = seeded["rohit"]
    aman = seeded["aman"]
    doc_a = seeded["doc_a"]
    headers_staff = {"X-User-Id": str(rohit.id)}
    headers_rev = {"X-User-Id": str(aman.id)}

    create = client.post(
        "/api/documents",
        headers=headers_staff,
        json={"client_id": seeded["client_a"].id, "doc_type": "Bank Statement"},
    )
    assert create.status_code == 201
    doc_id = create.json()["id"]

    def count_for(action: str) -> int:
        return (
            db.query(AuditEvent)
            .filter(AuditEvent.document_id == doc_id, AuditEvent.action == action)
            .count()
        )

    assert count_for(AuditAction.CREATED.value) == 1

    up = client.post(
        f"/api/documents/{doc_id}/upload",
        headers=headers_staff,
        files={"file": ("Bank_Statement.pdf", b"%PDF-1.4 v1", "application/pdf")},
    )
    assert up.status_code == 200
    db.expire_all()
    assert count_for(AuditAction.UPLOADED.value) == 1
    event = (
        db.query(AuditEvent)
        .filter(AuditEvent.document_id == doc_id, AuditEvent.action == AuditAction.UPLOADED.value)
        .one()
    )
    assert event.actor == "Rohit"
    assert event.actor_role == "staff"
    assert event.from_status == DocumentStatus.PENDING.value
    assert event.to_status == DocumentStatus.UPLOADED.value
    assert event.created_at is not None

    start = client.post(f"/api/documents/{doc_id}/start-review", headers=headers_rev)
    assert start.status_code == 200
    db.expire_all()
    assert count_for(AuditAction.STARTED_REVIEW.value) == 1

    corr = client.post(
        f"/api/documents/{doc_id}/request-correction",
        headers=headers_rev,
        json={"comment": "Page 3 is missing. Please upload the complete bank statement."},
    )
    assert corr.status_code == 200
    db.expire_all()
    corr_event = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.document_id == doc_id,
            AuditEvent.action == AuditAction.REQUESTED_CORRECTION.value,
        )
        .one()
    )
    assert corr_event.note == "Page 3 is missing. Please upload the complete bank statement."
    assert corr_event.actor == "Aman"

    reup = client.post(
        f"/api/documents/{doc_id}/upload",
        headers=headers_staff,
        files={"file": ("Bank_Statement.pdf", b"%PDF-1.4 v2 complete", "application/pdf")},
    )
    assert reup.status_code == 200
    db.expire_all()
    assert count_for(AuditAction.REUPLOADED.value) == 1

    start2 = client.post(f"/api/documents/{doc_id}/start-review", headers=headers_rev)
    assert start2.status_code == 200
    approve = client.post(f"/api/documents/{doc_id}/approve", headers=headers_rev)
    assert approve.status_code == 200
    db.expire_all()
    assert count_for(AuditAction.APPROVED.value) == 1
    total = db.query(AuditEvent).filter(AuditEvent.document_id == doc_id).count()
    # created, uploaded, started, correction, reuploaded, started, approved
    assert total == 7


def test_reupload_creates_new_version_keeps_old(client: TestClient, seeded, db):
    rohit = seeded["rohit"]
    aman = seeded["aman"]
    doc_id = seeded["doc_a"].id
    headers_staff = {"X-User-Id": str(rohit.id)}
    headers_rev = {"X-User-Id": str(aman.id)}

    first = client.post(
        f"/api/documents/{doc_id}/upload",
        headers=headers_staff,
        files={"file": ("Bank_Statement.pdf", b"version-one", "application/pdf")},
    )
    assert first.status_code == 200
    start = client.post(f"/api/documents/{doc_id}/start-review", headers=headers_rev)
    assert start.status_code == 200
    corr = client.post(
        f"/api/documents/{doc_id}/request-correction",
        headers=headers_rev,
        json={"comment": "Page 3 was missing."},
    )
    assert corr.status_code == 200
    second = client.post(
        f"/api/documents/{doc_id}/upload",
        headers=headers_staff,
        files={"file": ("Bank_Statement_revised.pdf", b"version-two", "application/pdf")},
    )
    assert second.status_code == 200
    db.expire_all()
    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == doc_id)
        .order_by(DocumentVersion.id)
        .all()
    )
    assert len(versions) == 2
    assert versions[0].original_filename == "Bank_Statement.pdf"
    assert versions[1].original_filename == "Bank_Statement_revised.pdf"
    assert versions[0].checksum_sha256 != versions[1].checksum_sha256
