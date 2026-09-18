from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    STAFF = "staff"
    REVIEWER = "reviewer"


class DocumentType(str, Enum):
    BANK_STATEMENT = "Bank Statement"
    SALES_REGISTER = "Sales Register"
    PURCHASE_REGISTER = "Purchase Register"
    GST_RETURN = "GST Return"
    EXPENSE_SUMMARY = "Expense Summary"


class DocumentStatus(str, Enum):
    PENDING = "Pending"
    UPLOADED = "Uploaded"
    UNDER_REVIEW = "Under Review"
    CORRECTION_REQUIRED = "Correction Required"
    APPROVED = "Approved"


class AuditAction(str, Enum):
    CREATED = "created"
    UPLOADED = "uploaded"
    REUPLOADED = "reuploaded"
    STARTED_REVIEW = "started_review"
    REQUESTED_CORRECTION = "requested_correction"
    APPROVED = "approved"
