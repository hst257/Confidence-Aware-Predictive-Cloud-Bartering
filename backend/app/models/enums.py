from enum import Enum


class ContractStatus(str, Enum):
    PROPOSED = "Proposed"
    SCHEDULED = "Scheduled"
    AT_RISK = "At Risk"
    ACTIVE = "Active"
    COMPLETED = "Completed"
    RENEGOTIATED = "Renegotiated"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class CollateralStatus(str, Enum):
    LOCKED = "Locked"
    RELEASED = "Released"
    FORFEITED = "Forfeited"


class CreditTransactionType(str, Enum):
    COLLATERAL_LOCK = "Collateral lock"
    COLLATERAL_RELEASE = "Collateral release"
    COLLATERAL_FORFEIT = "Collateral forfeit"
    CONTRACT_PAYMENT = "Contract payment"
    CONTRACT_EARNING = "Contract earning"
    COMPENSATION = "Failure compensation"


class PredictionKind(str, Enum):
    INITIAL = "Initial"
    REVISED = "Revised"
