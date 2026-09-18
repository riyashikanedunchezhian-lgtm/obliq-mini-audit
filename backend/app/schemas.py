from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.enums import DocumentType


class UserOut(BaseModel):
    id: int
    firm_id: int
    firm_name: str
    name: str
    role: str

    model_config = {"from_attributes": True}


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ClientOut(BaseModel):
    id: int
    firm_id: int
    name: str

    model_config = {"from_attributes": True}


class VersionOut(BaseModel):
    id: int
    original_filename: str
    uploaded_by: int
    uploaded_by_name: str | None = None
    uploaded_at: datetime
    checksum_sha256: str

    model_config = {"from_attributes": True}


class DocumentCreate(BaseModel):
    client_id: int
    doc_type: DocumentType


class DocumentOut(BaseModel):
    id: int
    client_id: int
    client_name: str
    firm_id: int
    doc_type: str
    current_status: str
    created_at: datetime
    latest_review_comment: str | None
    versions: list[VersionOut] = []
    uploaded_by_name: str | None = None
    uploaded_at: datetime | None = None
    current_filename: str | None = None

    model_config = {"from_attributes": True}


class CorrectionRequest(BaseModel):
    comment: str = Field(min_length=1)

    @field_validator("comment")
    @classmethod
    def comment_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Correction request requires a non-empty comment")
        return stripped


class AuditEventOut(BaseModel):
    id: int
    document_id: int
    document_label: str | None = None
    firm_id: int
    actor: str
    actor_role: str
    action: str
    from_status: str | None
    to_status: str | None
    note: str | None
    created_at: datetime
    display_text: str

    model_config = {"from_attributes": True}
