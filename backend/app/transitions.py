"""Explicit server-side document status machine.

The frontend never decides legality. Every transition is looked up here.
"""

from __future__ import annotations

from app.enums import DocumentStatus, Role

# (from_status, to_status, allowed_roles)
ALLOWED_TRANSITIONS: dict[tuple[DocumentStatus, DocumentStatus], frozenset[Role]] = {
    (DocumentStatus.PENDING, DocumentStatus.UPLOADED): frozenset({Role.STAFF}),
    (DocumentStatus.UPLOADED, DocumentStatus.UNDER_REVIEW): frozenset({Role.REVIEWER}),
    (DocumentStatus.UNDER_REVIEW, DocumentStatus.APPROVED): frozenset({Role.REVIEWER}),
    (DocumentStatus.UNDER_REVIEW, DocumentStatus.CORRECTION_REQUIRED): frozenset({Role.REVIEWER}),
    (DocumentStatus.CORRECTION_REQUIRED, DocumentStatus.UPLOADED): frozenset({Role.STAFF}),
}


class IllegalTransitionError(ValueError):
    def __init__(self, current: DocumentStatus, requested: DocumentStatus) -> None:
        self.current = current
        self.requested = requested
        super().__init__(
            f"Illegal status transition: {current.value} → {requested.value}"
        )


def assert_transition_allowed(
    current: DocumentStatus,
    requested: DocumentStatus,
    role: Role,
) -> None:
    key = (current, requested)
    allowed_roles = ALLOWED_TRANSITIONS.get(key)
    if allowed_roles is None:
        raise IllegalTransitionError(current, requested)
    if role not in allowed_roles:
        raise IllegalTransitionError(current, requested)
