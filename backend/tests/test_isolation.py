from __future__ import annotations

from fastapi.testclient import TestClient


def test_firm_a_cannot_get_firm_b_document(client: TestClient, seeded):
    rohit = seeded["rohit"]
    doc_b = seeded["doc_b"]
    res = client.get(
        f"/api/documents/{doc_b.id}",
        headers={"X-User-Id": str(rohit.id)},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Document not found"


def test_firm_a_cannot_download_firm_b_document(client: TestClient, seeded):
    rohit = seeded["rohit"]
    doc_b = seeded["doc_b"]
    res = client.get(
        f"/api/documents/{doc_b.id}/download",
        headers={"X-User-Id": str(rohit.id)},
    )
    assert res.status_code == 404


def test_firm_a_cannot_list_firm_b_clients(client: TestClient, seeded):
    rohit = seeded["rohit"]
    client_b = seeded["client_b"]
    res = client.get("/api/clients", headers={"X-User-Id": str(rohit.id)})
    assert res.status_code == 200
    ids = {c["id"] for c in res.json()}
    assert client_b.id not in ids
    assert seeded["client_a"].id in ids


def test_firm_a_cannot_fetch_firm_b_client_by_id(client: TestClient, seeded):
    rohit = seeded["rohit"]
    client_b = seeded["client_b"]
    res = client.get(
        f"/api/clients/{client_b.id}",
        headers={"X-User-Id": str(rohit.id)},
    )
    assert res.status_code == 404


def test_firm_a_cannot_list_firm_b_documents(client: TestClient, seeded):
    rohit = seeded["rohit"]
    res = client.get("/api/documents", headers={"X-User-Id": str(rohit.id)})
    assert res.status_code == 200
    ids = {d["id"] for d in res.json()}
    assert seeded["doc_b"].id not in ids
    assert seeded["doc_a"].id in ids


def test_firm_a_cannot_read_firm_b_document_audit(client: TestClient, seeded):
    rohit = seeded["rohit"]
    res = client.get(
        f"/api/documents/{seeded['doc_b'].id}/audit",
        headers={"X-User-Id": str(rohit.id)},
    )
    assert res.status_code == 404


def test_firm_a_audit_feed_excludes_firm_b_events(client: TestClient, seeded, db):
    from app.audit import record_event
    from app.enums import AuditAction

    db.add(
        record_event(
            document=seeded["doc_b"],
            actor=seeded["priya"],
            action=AuditAction.CREATED,
            from_status=None,
            to_status="Pending",
        )
    )
    db.add(
        record_event(
            document=seeded["doc_a"],
            actor=seeded["rohit"],
            action=AuditAction.CREATED,
            from_status=None,
            to_status="Pending",
        )
    )
    db.commit()
    res = client.get("/api/audit", headers={"X-User-Id": str(seeded["rohit"].id)})
    assert res.status_code == 200
    doc_ids = {e["document_id"] for e in res.json()}
    assert seeded["doc_a"].id in doc_ids
    assert seeded["doc_b"].id not in doc_ids
