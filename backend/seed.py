"""Seed firms, users, clients, documents, versions, and audit events.

Dataset mapping (inline comments on each document below):
- Bank Statement  → Hugging Face AgamiAI/Indian-Bank-Statements
- Purchase Register / GST Return → github.com/AnujSureshkumar/synthetic-finance-data
- Sales Register → github.com/ciru-ai/invoice-sandbox-benchmark
- Expense Summary → github.com/PearlThoughts/LedgerBridge

If those remotes are unreachable, clearly labeled synthetic fallbacks in
data/seed_files/ are used instead.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.enums import AuditAction, DocumentStatus, DocumentType, Role
from app.files import configured_upload_root, save_upload
from app.models import (
    AuditEvent,
    Client,
    Document,
    DocumentVersion,
    Firm,
    User,
    init_db,
    make_engine,
    session_factory,
)

ROOT = Path(__file__).resolve().parent
SEED_DIR = ROOT / "data" / "seed_files"
IST = timezone(timedelta(hours=5, minutes=30))

# Original filenames from each dataset (one small file per type).
REMOTE_CANDIDATES: dict[str, list[str]] = {
    "bank_statement": [
        "https://huggingface.co/datasets/AgamiAI/Indian-Bank-Statements/resolve/main/train/India_Bank_Statement_Digital_Type1/00001.json",
    ],
    "bank_statement_revised": [
        "https://huggingface.co/datasets/AgamiAI/Indian-Bank-Statements/resolve/main/train/India_Bank_Statement_Digital_Type1/00001.pdf",
    ],
    "purchase_register": [
        "https://raw.githubusercontent.com/AnujSureshkumar/synthetic-finance-data/main/output/purchase_register.csv",
    ],
    "gst_return": [
        "https://raw.githubusercontent.com/AnujSureshkumar/synthetic-finance-data/main/output/gstr2b_062026.json",
    ],
    "sales_register": [
        "https://raw.githubusercontent.com/ciru-ai/invoice-sandbox-benchmark/main/answer_key/invoices.csv",
    ],
    "expense_summary": [
        "https://raw.githubusercontent.com/PearlThoughts/LedgerBridge/main/examples/pixelcraft-studios/statements/hdfc-ca-apr-2025.csv",
    ],
}

ORIGINAL_NAMES: dict[str, str] = {
    "bank_statement": "00001.json",
    "bank_statement_revised": "00001.pdf",
    "purchase_register": "purchase_register.csv",
    "gst_return": "gstr2b_062026.json",
    "sales_register": "invoices.csv",
    "expense_summary": "hdfc-ca-apr-2025.csv",
}

FALLBACK_CONTENT: dict[str, tuple[str, bytes]] = {
    "bank_statement": (
        "00001.json",
        (
            b"%PDF-1.4\n% synthetic fallback from AgamiAI/Indian-Bank-Statements schema\n"
            b"HDFC Bank - ABC Traders Pvt. Ltd. A/c 5020001122334\n"
            b"01-Apr-2026 Opening 250000.00\n"
            b"03-Apr-2026 NEFT IN 85000.00\n"
            b"05-Apr-2026 CHQ OUT 12000.00\n"
            b"Page 1 of 2 (page 3 referenced in review is not present in this file)\n"
        ),
    ),
    "bank_statement_revised": (
        "00001.pdf",
        (
            b"%PDF-1.4\n% revised bank statement - pages 1-3 present\n"
            b"HDFC Bank - ABC Traders Pvt. Ltd.\n"
            b"Page 1 opening, Page 2 transactions, Page 3 closing 323000.00\n"
        ),
    ),
    "purchase_register": (
        "purchase_register.csv",
        (
            b"source,AnujSureshkumar/synthetic-finance-data (synthetic fallback)\n"
            b"invoice_no,vendor,gstin,taxable,igst_rate,igst_amount,total\n"
            b"INV-2047,Mehra Steel,27AABCU9603R1ZM,120000,18,18000,138000\n"
            b"INV-2048,Kiran Plastics,29AAGCK1234P1Z1,40000,18,7200,47200\n"
            b"# inconsistency: INV-2047 IGST should be 21600 (18% of 120000), recorded 18000\n"
        ),
    ),
    "gst_return": (
        "gstr2b_062026.json",
        (
            b"source,AnujSureshkumar/synthetic-finance-data GSTR-2B extract (synthetic fallback)\n"
            b"gstin,invoice,taxable,igst,period\n"
            b"27AABCU9603R1ZM,INV-2047,120000,21600,2026-04\n"
        ),
    ),
    "sales_register": (
        "invoices.csv",
        (
            b"source,ciru-ai/invoice-sandbox-benchmark (synthetic fallback)\n"
            b"invoice_no,buyer,hsn,qty,rate,amount\n"
            b"SL-1001,Ravi Distributors,7208,10,1500,15000\n"
            b"SL-1002,North Star Retail,3923,40,220,8800\n"
        ),
    ),
    "expense_summary": (
        "hdfc-ca-apr-2025.csv",
        (
            b"source,PearlThoughts/LedgerBridge bookkeeping export (synthetic fallback)\n"
            b"date,account,memo,debit,credit\n"
            b"2026-04-02,Travel,Delhi client visit,8450,0\n"
            b"2026-04-08,Office,Stationery,1200,0\n"
            b"2026-04-18,Utilities,Electricity,6400,0\n"
        ),
    ),
}

DOWNLOAD_NOTES: list[str] = []


def _try_download(urls: list[str], dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "obliq-mini-audit-seed/0.1"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if not data:
                continue
            dest.write_bytes(data)
            DOWNLOAD_NOTES.append(f"downloaded {url} -> {dest.name} ({len(data)} bytes)")
            return True
        except Exception as exc:  # noqa: BLE001 — seed must not abort on network
            DOWNLOAD_NOTES.append(f"failed {url}: {exc}")
    return False


def materialize_seed_files() -> dict[str, Path]:
    """Download original dataset files; fall back only if a remote is unreachable."""
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for key, (fallback_name, fallback) in FALLBACK_CONTENT.items():
        filename = ORIGINAL_NAMES.get(key, fallback_name)
        dest = SEED_DIR / filename
        urls = REMOTE_CANDIDATES.get(key, [])
        used_remote = _try_download(urls, dest) if urls else False
        if not used_remote:
            raise SystemExit(
                f"Could not download original dataset file for {key} from {urls}. "
                "Seed requires the real files, not placeholders."
            )
        paths[key] = dest
    return paths


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def at(hour: int, minute: int, day: int = 18) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=IST)


def add_version(
    db: Session,
    document: Document,
    uploader: User,
    src: Path,
    uploaded_at: datetime,
    stored_name: str | None = None,
) -> DocumentVersion:
    data = src.read_bytes()
    filename = stored_name or src.name
    path = save_upload(document.firm_id, document.id, filename, data)
    version = DocumentVersion(
        document_id=document.id,
        firm_id=document.firm_id,
        file_path=path,
        original_filename=filename,
        uploaded_by=uploader.id,
        uploaded_at=uploaded_at,
        checksum_sha256=hashlib.sha256(data).hexdigest(),
    )
    db.add(version)
    return version


def add_event(
    db: Session,
    document: Document,
    actor: User,
    action: AuditAction,
    when: datetime,
    from_status: str | None,
    to_status: str | None,
    note: str | None = None,
) -> None:
    db.add(
        AuditEvent(
            document_id=document.id,
            firm_id=document.firm_id,
            actor=actor.name,
            actor_role=actor.role,
            action=action.value,
            from_status=from_status,
            to_status=to_status,
            note=note,
            created_at=when,
        )
    )


def seed(db: Session, files: dict[str, Path]) -> None:
    abc = Firm(name="ABC & Co.")
    xyz = Firm(name="XYZ & Co.")
    db.add_all([abc, xyz])
    db.flush()

    rohit = User(firm_id=abc.id, name="Rohit", role=Role.STAFF.value)
    aman = User(firm_id=abc.id, name="Aman", role=Role.REVIEWER.value)
    priya = User(firm_id=xyz.id, name="Priya", role=Role.STAFF.value)
    vikram = User(firm_id=xyz.id, name="Vikram", role=Role.REVIEWER.value)
    db.add_all([rohit, aman, priya, vikram])
    db.flush()

    traders = Client(firm_id=abc.id, name="ABC Traders Pvt. Ltd.")
    mill = Client(firm_id=abc.id, name="ABC Steel Mills")
    exports = Client(firm_id=xyz.id, name="XYZ Exports Pvt. Ltd.")
    logistics = Client(firm_id=xyz.id, name="XYZ Logistics LLP")
    db.add_all([traders, mill, exports, logistics])
    db.flush()

    # --- Firm A / ABC Traders: 6 documents spanning every status ---

    # Bank Statement — AgamiAI/Indian-Bank-Statements
    # Walks the brief's example timeline (upload → review → correction → re-upload → approve).
    bank = Document(
        client_id=traders.id,
        firm_id=abc.id,
        doc_type=DocumentType.BANK_STATEMENT.value,
        current_status=DocumentStatus.APPROVED.value,
        created_at=at(10, 15),
        latest_review_comment="Page 3 of the AgamiAI 00001.pdf (closing-balance block) is missing. Only the JSON extract was uploaded.",
    )
    db.add(bank)
    db.flush()
    add_event(db, bank, rohit, AuditAction.CREATED, at(10, 15), None, "Pending")
    add_version(db, bank, rohit, files["bank_statement"], at(10, 20))
    add_event(db, bank, rohit, AuditAction.UPLOADED, at(10, 20), "Pending", "Uploaded")
    add_event(db, bank, aman, AuditAction.STARTED_REVIEW, at(10, 31), "Uploaded", "Under Review")
    add_event(
        db,
        bank,
        aman,
        AuditAction.REQUESTED_CORRECTION,
        at(10, 34),
        "Under Review",
        "Correction Required",
        note="Page 3 of the AgamiAI 00001.pdf (closing-balance block) is missing. Only the JSON extract was uploaded.",
    )
    add_version(db, bank, rohit, files["bank_statement_revised"], at(11, 5))
    add_event(
        db,
        bank,
        rohit,
        AuditAction.REUPLOADED,
        at(11, 5),
        "Correction Required",
        "Uploaded",
        note="revised document",
    )
    add_event(db, bank, aman, AuditAction.STARTED_REVIEW, at(11, 10), "Uploaded", "Under Review")
    add_event(db, bank, aman, AuditAction.APPROVED, at(11, 12), "Under Review", "Approved")

    # Purchase Register — synthetic-finance-data; genuine tax inconsistency left as Correction Required.
    purchase = Document(
        client_id=traders.id,
        firm_id=abc.id,
        doc_type=DocumentType.PURCHASE_REGISTER.value,
        current_status=DocumentStatus.CORRECTION_REQUIRED.value,
        created_at=at(9, 0),
        latest_review_comment=(
            "INV-202606-045 (Pioneer Consulting LLP, GSTIN 33JDVCC3793Y1ZS) is Inter-state "
            "(place of supply Tamil Nadu) with reverse_charge=Yes, but IGST is recorded as 0 "
            "and invoice_total equals taxable_value Rs 67,100. Record IGST of Rs 12,078 (18%) "
            "or attach RCM working. Source: synthetic-finance-data output/purchase_register.csv."
        ),
    )
    db.add(purchase)
    db.flush()
    add_event(db, purchase, rohit, AuditAction.CREATED, at(9, 0), None, "Pending")
    add_version(db, purchase, rohit, files["purchase_register"], at(9, 12))
    add_event(db, purchase, rohit, AuditAction.UPLOADED, at(9, 12), "Pending", "Uploaded")
    add_event(db, purchase, aman, AuditAction.STARTED_REVIEW, at(9, 40), "Uploaded", "Under Review")
    add_event(
        db,
        purchase,
        aman,
        AuditAction.REQUESTED_CORRECTION,
        at(9, 48),
        "Under Review",
        "Correction Required",
        note=purchase.latest_review_comment,
    )

    # GST Return — synthetic-finance-data GSTR-2B extract
    gst = Document(
        client_id=traders.id,
        firm_id=abc.id,
        doc_type=DocumentType.GST_RETURN.value,
        current_status=DocumentStatus.UNDER_REVIEW.value,
        created_at=at(12, 0),
    )
    db.add(gst)
    db.flush()
    add_event(db, gst, rohit, AuditAction.CREATED, at(12, 0), None, "Pending")
    add_version(db, gst, rohit, files["gst_return"], at(12, 8))
    add_event(db, gst, rohit, AuditAction.UPLOADED, at(12, 8), "Pending", "Uploaded")
    add_event(db, gst, aman, AuditAction.STARTED_REVIEW, at(12, 20), "Uploaded", "Under Review")

    # Sales Register — invoice-sandbox-benchmark
    sales = Document(
        client_id=traders.id,
        firm_id=abc.id,
        doc_type=DocumentType.SALES_REGISTER.value,
        current_status=DocumentStatus.UPLOADED.value,
        created_at=at(13, 0),
    )
    db.add(sales)
    db.flush()
    add_event(db, sales, rohit, AuditAction.CREATED, at(13, 0), None, "Pending")
    add_version(db, sales, rohit, files["sales_register"], at(13, 5))
    add_event(db, sales, rohit, AuditAction.UPLOADED, at(13, 5), "Pending", "Uploaded")

    # Expense Summary — LedgerBridge hdfc-ca-apr-2025.csv (original)
    expense = Document(
        client_id=traders.id,
        firm_id=abc.id,
        doc_type=DocumentType.EXPENSE_SUMMARY.value,
        current_status=DocumentStatus.UPLOADED.value,
        created_at=at(14, 0),
    )
    db.add(expense)
    db.flush()
    add_event(db, expense, rohit, AuditAction.CREATED, at(14, 0), None, "Pending")
    add_version(db, expense, rohit, files["expense_summary"], at(14, 8))
    add_event(db, expense, rohit, AuditAction.UPLOADED, at(14, 8), "Pending", "Uploaded")

    # Extra Approved GST-adjacent sales for mill client so Firm A has 7 docs
    mill_sales = Document(
        client_id=mill.id,
        firm_id=abc.id,
        doc_type=DocumentType.SALES_REGISTER.value,
        current_status=DocumentStatus.APPROVED.value,
        created_at=at(8, 0),
    )
    db.add(mill_sales)
    db.flush()
    add_event(db, mill_sales, rohit, AuditAction.CREATED, at(8, 0), None, "Pending")
    add_version(db, mill_sales, rohit, files["sales_register"], at(8, 10))
    add_event(db, mill_sales, rohit, AuditAction.UPLOADED, at(8, 10), "Pending", "Uploaded")
    add_event(db, mill_sales, aman, AuditAction.STARTED_REVIEW, at(8, 25), "Uploaded", "Under Review")
    add_event(db, mill_sales, aman, AuditAction.APPROVED, at(8, 40), "Under Review", "Approved")

    mill_exp = Document(
        client_id=mill.id,
        firm_id=abc.id,
        doc_type=DocumentType.EXPENSE_SUMMARY.value,
        current_status=DocumentStatus.UPLOADED.value,
        created_at=at(15, 0),
    )
    db.add(mill_exp)
    db.flush()
    add_event(db, mill_exp, rohit, AuditAction.CREATED, at(15, 0), None, "Pending")
    add_version(db, mill_exp, rohit, files["expense_summary"], at(15, 12))
    add_event(db, mill_exp, rohit, AuditAction.UPLOADED, at(15, 12), "Pending", "Uploaded")

    # --- Firm B / XYZ Exports: 6 documents, isolated from Firm A ---

    b_bank = Document(
        client_id=exports.id,
        firm_id=xyz.id,
        doc_type=DocumentType.BANK_STATEMENT.value,
        current_status=DocumentStatus.UPLOADED.value,
        created_at=at(10, 0, day=17),
    )
    db.add(b_bank)
    db.flush()
    add_event(db, b_bank, priya, AuditAction.CREATED, at(10, 0, 17), None, "Pending")
    add_version(db, b_bank, priya, files["bank_statement"], at(10, 6, 17))
    add_event(db, b_bank, priya, AuditAction.UPLOADED, at(10, 6, 17), "Pending", "Uploaded")

    b_purchase = Document(
        client_id=exports.id,
        firm_id=xyz.id,
        doc_type=DocumentType.PURCHASE_REGISTER.value,
        current_status=DocumentStatus.CORRECTION_REQUIRED.value,
        created_at=at(11, 0, 17),
        latest_review_comment=(
            "INV-202606-045 (Pioneer Consulting LLP, GSTIN 33JDVCC3793Y1ZS) is Inter-state "
            "(place of supply Tamil Nadu) with reverse_charge=Yes, but IGST is recorded as 0 "
            "and invoice_total equals taxable_value Rs 67,100. Record IGST of Rs 12,078 (18%) "
            "or attach RCM working. Source: synthetic-finance-data output/purchase_register.csv."
        ),
    )
    db.add(b_purchase)
    db.flush()
    add_event(db, b_purchase, priya, AuditAction.CREATED, at(11, 0, 17), None, "Pending")
    add_version(db, b_purchase, priya, files["purchase_register"], at(11, 10, 17))
    add_event(db, b_purchase, priya, AuditAction.UPLOADED, at(11, 10, 17), "Pending", "Uploaded")
    add_event(db, b_purchase, vikram, AuditAction.STARTED_REVIEW, at(11, 30, 17), "Uploaded", "Under Review")
    add_event(
        db,
        b_purchase,
        vikram,
        AuditAction.REQUESTED_CORRECTION,
        at(11, 42, 17),
        "Under Review",
        "Correction Required",
        note=b_purchase.latest_review_comment,
    )

    b_gst = Document(
        client_id=exports.id,
        firm_id=xyz.id,
        doc_type=DocumentType.GST_RETURN.value,
        current_status=DocumentStatus.APPROVED.value,
        created_at=at(12, 0, 17),
    )
    db.add(b_gst)
    db.flush()
    add_event(db, b_gst, priya, AuditAction.CREATED, at(12, 0, 17), None, "Pending")
    add_version(db, b_gst, priya, files["gst_return"], at(12, 15, 17))
    add_event(db, b_gst, priya, AuditAction.UPLOADED, at(12, 15, 17), "Pending", "Uploaded")
    add_event(db, b_gst, vikram, AuditAction.STARTED_REVIEW, at(12, 40, 17), "Uploaded", "Under Review")
    add_event(db, b_gst, vikram, AuditAction.APPROVED, at(12, 55, 17), "Under Review", "Approved")

    b_sales = Document(
        client_id=exports.id,
        firm_id=xyz.id,
        doc_type=DocumentType.SALES_REGISTER.value,
        current_status=DocumentStatus.UNDER_REVIEW.value,
        created_at=at(13, 0, 17),
    )
    db.add(b_sales)
    db.flush()
    add_event(db, b_sales, priya, AuditAction.CREATED, at(13, 0, 17), None, "Pending")
    add_version(db, b_sales, priya, files["sales_register"], at(13, 8, 17))
    add_event(db, b_sales, priya, AuditAction.UPLOADED, at(13, 8, 17), "Pending", "Uploaded")
    add_event(db, b_sales, vikram, AuditAction.STARTED_REVIEW, at(13, 22, 17), "Uploaded", "Under Review")

    b_exp = Document(
        client_id=exports.id,
        firm_id=xyz.id,
        doc_type=DocumentType.EXPENSE_SUMMARY.value,
        current_status=DocumentStatus.UPLOADED.value,
        created_at=at(14, 0, 17),
    )
    db.add(b_exp)
    db.flush()
    add_event(db, b_exp, priya, AuditAction.CREATED, at(14, 0, 17), None, "Pending")
    add_version(db, b_exp, priya, files["expense_summary"], at(14, 10, 17))
    add_event(db, b_exp, priya, AuditAction.UPLOADED, at(14, 10, 17), "Pending", "Uploaded")

    b_log = Document(
        client_id=logistics.id,
        firm_id=xyz.id,
        doc_type=DocumentType.BANK_STATEMENT.value,
        current_status=DocumentStatus.APPROVED.value,
        created_at=at(9, 0, 17),
    )
    db.add(b_log)
    db.flush()
    add_event(db, b_log, priya, AuditAction.CREATED, at(9, 0, 17), None, "Pending")
    add_version(db, b_log, priya, files["bank_statement_revised"], at(9, 20, 17))
    add_event(db, b_log, priya, AuditAction.UPLOADED, at(9, 20, 17), "Pending", "Uploaded")
    add_event(db, b_log, vikram, AuditAction.STARTED_REVIEW, at(9, 45, 17), "Uploaded", "Under Review")
    add_event(db, b_log, vikram, AuditAction.APPROVED, at(10, 5, 17), "Under Review", "Approved")

    b_log_exp = Document(
        client_id=logistics.id,
        firm_id=xyz.id,
        doc_type=DocumentType.EXPENSE_SUMMARY.value,
        current_status=DocumentStatus.UPLOADED.value,
        created_at=at(16, 0, 17),
    )
    db.add(b_log_exp)
    db.flush()
    add_event(db, b_log_exp, priya, AuditAction.CREATED, at(16, 0, 17), None, "Pending")
    add_version(db, b_log_exp, priya, files["expense_summary"], at(16, 10, 17))
    add_event(db, b_log_exp, priya, AuditAction.UPLOADED, at(16, 10, 17), "Pending", "Uploaded")

    db.commit()


def main() -> None:
    db_path = ROOT / "data" / "audit.db"
    if db_path.exists():
        try:
            db_path.unlink()
        except PermissionError as exc:
            raise SystemExit(
                "Could not replace audit.db — it is locked (usually uvicorn is still running).\n"
                "Stop the backend (Ctrl+C in that terminal), then run: python seed.py"
            ) from exc
    files = materialize_seed_files()
    upload_root = configured_upload_root()
    if upload_root.exists():
        shutil.rmtree(upload_root)
    upload_root.mkdir(parents=True, exist_ok=True)
    engine = make_engine()
    init_db(engine)
    SessionLocal = session_factory(engine)
    db = SessionLocal()
    try:
        seed(db, files)
    finally:
        db.close()
    notes_path = ROOT / "data" / "seed_download_log.txt"
    notes_path.write_text("\n".join(DOWNLOAD_NOTES), encoding="utf-8")
    print("Seed complete.")
    print(f"Database: {db_path}")
    print(f"Uploads: {configured_upload_root()}")
    for line in DOWNLOAD_NOTES:
        print(f"  {line}")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
