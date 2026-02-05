from enum import Enum
from typing import Dict, Set
from datetime import datetime, timezone
import uuid
import json

# Escrow states as Enum for usage in code
class EscrowState(str, Enum):
    CREATED = "CREATED"
    FORM_SUBMITTED = "FORM_SUBMITTED"
    AGREEMENT_PREVIEW = "AGREEMENT_PREVIEW"
    AGREED = "AGREED"
    FUNDED = "FUNDED"
    DELIVERED = "DELIVERED"
    RELEASE_REQUESTED = "RELEASE_REQUESTED"
    RELEASE_CONFIRMED = "RELEASE_CONFIRMED"
    COMPLETED = "COMPLETED"
    DISPUTED = "DISPUTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"

# Define allowed transitions (strict)
ALLOWED_TRANSITIONS: Dict[EscrowState, Set[EscrowState]] = {
    EscrowState.CREATED: {EscrowState.FORM_SUBMITTED, EscrowState.CANCELLED},
    EscrowState.FORM_SUBMITTED: {EscrowState.AGREEMENT_PREVIEW, EscrowState.CANCELLED},
    EscrowState.AGREEMENT_PREVIEW: {EscrowState.AGREED, EscrowState.CANCELLED},
    EscrowState.AGREED: {EscrowState.FUNDED, EscrowState.CANCELLED},
    EscrowState.FUNDED: {EscrowState.DELIVERED, EscrowState.DISPUTED, EscrowState.CANCELLED},
    EscrowState.DELIVERED: {EscrowState.RELEASE_REQUESTED, EscrowState.DISPUTED},
    EscrowState.RELEASE_REQUESTED: {EscrowState.RELEASE_CONFIRMED, EscrowState.DISPUTED},
    EscrowState.RELEASE_CONFIRMED: {EscrowState.COMPLETED},
    EscrowState.COMPLETED: set(),
    EscrowState.DISPUTED: {EscrowState.RELEASE_CONFIRMED, EscrowState.CANCELLED},
    EscrowState.CANCELLED: set(),
    EscrowState.EXPIRED: set(),
}

class InvalidTransition(Exception):
    pass