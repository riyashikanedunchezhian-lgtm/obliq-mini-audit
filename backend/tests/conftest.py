from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import reset_engine
from app.enums import DocumentStatus, DocumentType, Role
from app.models import Client, Document, Firm, User, init_db, make_engine, session_factory


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def engine(db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path / "uploads"))
    reset_engine()
    engine = make_engine(os.environ["DATABASE_URL"])
    init_db(engine)
    yield engine
    reset_engine()


@pytest.fixture()
def db(engine) -> Session:
    SessionLocal = session_factory(engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def seeded(db: Session) -> dict:
    firm_a = Firm(name="ABC & Co.")
    firm_b = Firm(name="XYZ & Co.")
    db.add_all([firm_a, firm_b])
    db.flush()

    rohit = User(firm_id=firm_a.id, name="Rohit", role=Role.STAFF.value)
    aman = User(firm_id=firm_a.id, name="Aman", role=Role.REVIEWER.value)
    priya = User(firm_id=firm_b.id, name="Priya", role=Role.STAFF.value)
    vikram = User(firm_id=firm_b.id, name="Vikram", role=Role.REVIEWER.value)
    db.add_all([rohit, aman, priya, vikram])
    db.flush()

    client_a = Client(firm_id=firm_a.id, name="ABC Traders Pvt. Ltd.")
    client_b = Client(firm_id=firm_b.id, name="XYZ Exports Pvt. Ltd.")
    db.add_all([client_a, client_b])
    db.flush()

    doc_a = Document(
        client_id=client_a.id,
        firm_id=firm_a.id,
        doc_type=DocumentType.BANK_STATEMENT.value,
        current_status=DocumentStatus.PENDING.value,
    )
    doc_b = Document(
        client_id=client_b.id,
        firm_id=firm_b.id,
        doc_type=DocumentType.GST_RETURN.value,
        current_status=DocumentStatus.PENDING.value,
    )
    db.add_all([doc_a, doc_b])
    db.commit()
    db.refresh(rohit)
    db.refresh(aman)
    db.refresh(priya)
    db.refresh(vikram)
    db.refresh(client_a)
    db.refresh(client_b)
    db.refresh(doc_a)
    db.refresh(doc_b)
    db.refresh(firm_a)
    db.refresh(firm_b)
    return {
        "firm_a": firm_a,
        "firm_b": firm_b,
        "rohit": rohit,
        "aman": aman,
        "priya": priya,
        "vikram": vikram,
        "client_a": client_a,
        "client_b": client_b,
        "doc_a": doc_a,
        "doc_b": doc_b,
    }


@pytest.fixture()
def client(engine, seeded) -> TestClient:
    from app.main import app

    return TestClient(app)
