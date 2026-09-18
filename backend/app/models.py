from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from app.enums import DocumentStatus, DocumentType, Role

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "audit.db"


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Firm(Base):
    __tablename__ = "firms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

    users: Mapped[list["User"]] = relationship(back_populates="firm")
    clients: Mapped[list["Client"]] = relationship(back_populates="firm")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('staff', 'reviewer')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    firm_id: Mapped[int] = mapped_column(ForeignKey("firms.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    firm: Mapped[Firm] = relationship(back_populates="users")

    @property
    def role_enum(self) -> Role:
        return Role(self.role)


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    firm_id: Mapped[int] = mapped_column(ForeignKey("firms.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    firm: Mapped[Firm] = relationship(back_populates="clients")
    documents: Mapped[list["Document"]] = relationship(back_populates="client")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "current_status IN ('Pending', 'Uploaded', 'Under Review', 'Correction Required', 'Approved')",
            name="ck_documents_status",
        ),
        CheckConstraint(
            "doc_type IN ('Bank Statement', 'Sales Register', 'Purchase Register', 'GST Return', 'Expense Summary')",
            name="ck_documents_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    # Denormalized for tenant isolation — every document query filters on this column.
    firm_id: Mapped[int] = mapped_column(ForeignKey("firms.id"), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    current_status: Mapped[str] = mapped_column(String(64), nullable=False, default=DocumentStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    latest_review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    client: Mapped[Client] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        order_by="DocumentVersion.uploaded_at",
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="document",
        order_by="AuditEvent.created_at",
    )

    @property
    def status_enum(self) -> DocumentStatus:
        return DocumentStatus(self.current_status)

    @property
    def type_enum(self) -> DocumentType:
        return DocumentType(self.doc_type)


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    # Denormalized so version/download queries never rely on a join for isolation.
    firm_id: Mapped[int] = mapped_column(ForeignKey("firms.id"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    document: Mapped[Document] = relationship(back_populates="versions")
    uploader: Mapped[User] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    # Denormalized tenant key — audit listings never join through documents/clients to filter.
    firm_id: Mapped[int] = mapped_column(ForeignKey("firms.id"), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    document: Mapped[Document] = relationship(back_populates="audit_events")


AUDIT_NO_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
  SELECT RAISE(ABORT, 'audit_events is append-only');
END;
"""

AUDIT_NO_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
  SELECT RAISE(ABORT, 'audit_events is append-only');
END;
"""


def make_engine(db_url: str | None = None, *, echo: bool = False):
    if db_url is None:
        DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_engine(db_url, echo=echo, connect_args=connect_args)

    if db_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_on_connect(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def init_db(engine) -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(AUDIT_NO_UPDATE_TRIGGER))
        conn.execute(text(AUDIT_NO_DELETE_TRIGGER))
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(documents)")).fetchall()}
        if "deleted_at" not in cols:
            conn.execute(text("ALTER TABLE documents ADD COLUMN deleted_at DATETIME"))


def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
