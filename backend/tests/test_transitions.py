from __future__ import annotations

from fastapi.testclient import TestClient


def test_pending_to_approved_rejected(client: TestClient, seeded):
    aman = seeded["aman"]
    doc_a = seeded["doc_a"]
    res = client.post(
        f"/api/documents/{doc_a.id}/approve",
        headers={"X-User-Id": str(aman.id)},
    )
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "Pending" in detail
    assert "Approved" in detail


def test_empty_correction_comment_rejected(client: TestClient, seeded):
    rohit = seeded["rohit"]
    aman = seeded["aman"]
    doc_a = seeded["doc_a"]
    upload = client.post(
        f"/api/documents/{doc_a.id}/upload",
        headers={"X-User-Id": str(rohit.id)},
        files={"file": ("Bank_Statement.pdf", b"%PDF-1.4 bank", "application/pdf")},
    )
    assert upload.status_code == 200
    start = client.post(
        f"/api/documents/{doc_a.id}/start-review",
        headers={"X-User-Id": str(aman.id)},
    )
    assert start.status_code == 200
    res = client.post(
        f"/api/documents/{doc_a.id}/request-correction",
        headers={"X-User-Id": str(aman.id)},
        json={"comment": "   "},
    )
    assert res.status_code in (400, 422)


def test_empty_string_comment_rejected_by_validation(client: TestClient, seeded):
    aman = seeded["aman"]
    doc_a = seeded["doc_a"]
    res = client.post(
        f"/api/documents/{doc_a.id}/request-correction",
        headers={"X-User-Id": str(aman.id)},
        json={"comment": ""},
    )
    assert res.status_code in (400, 422)
