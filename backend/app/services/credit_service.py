from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BarterContract, Collateral, CollateralStatus, ContractStatus, CreditTransaction, CreditTransactionType, Provider
from .event_service import record_event


OPEN_CREDIT_OBLIGATIONS = [
    ContractStatus.PROPOSED,
    ContractStatus.SCHEDULED,
    ContractStatus.AT_RISK,
    ContractStatus.ACTIVE,
]


def available_credit(db: Session, provider: Provider, run_id: int | None) -> float:
    """Return spendable credit after reserving all unsettled consumer contracts."""
    obligations = db.scalars(select(BarterContract).where(
        BarterContract.run_id == run_id,
        BarterContract.consumer_id == provider.id,
        BarterContract.status.in_(OPEN_CREDIT_OBLIGATIONS),
    )).all()
    return round(provider.credit_balance - sum(item.barter_cost for item in obligations), 2)


def _post_transaction(
    db: Session,
    provider: Provider,
    contract: BarterContract,
    amount: float,
    transaction_type: CreditTransactionType,
    description: str,
    simulation_time: datetime | None = None,
) -> CreditTransaction:
    provider.credit_balance = round(provider.credit_balance + amount, 2)
    transaction = CreditTransaction(
        run_id=contract.run_id,
        provider_id=provider.id,
        contract_id=contract.id,
        amount=round(amount, 2),
        transaction_type=transaction_type,
        balance_after=provider.credit_balance,
        description=description,
        simulation_time=simulation_time,
    )
    db.add(transaction)
    db.flush()
    return transaction


def lock_collateral(db: Session, contract: BarterContract, amount: float, simulation_time: datetime | None = None) -> Collateral:
    provider = contract.provider
    amount = round(amount, 2)
    if available_credit(db, provider, contract.run_id) < amount:
        raise HTTPException(status_code=409, detail=f"{provider.name} does not have enough uncommitted credits for collateral")
    collateral = Collateral(run_id=contract.run_id, contract_id=contract.id, provider_id=provider.id, amount=amount)
    db.add(collateral)
    _post_transaction(
        db,
        provider,
        contract,
        -amount,
        CreditTransactionType.COLLATERAL_LOCK,
        f"Collateral locked for contract #{contract.id}",
        simulation_time,
    )
    record_event(
        db,
        "collateral.locked",
        f"{amount:g} {provider.name} credits locked as collateral for contract #{contract.id}",
        provider_id=provider.id,
        contract_id=contract.id,
        details={"amount": amount},
        simulation_time=simulation_time,
    )
    return collateral


def release_collateral(
    db: Session,
    contract: BarterContract,
    reason: str = "Commitment fulfilled",
    simulation_time: datetime | None = None,
) -> None:
    collateral = contract.collateral
    if not collateral or collateral.status != CollateralStatus.LOCKED:
        return
    collateral.status = CollateralStatus.RELEASED
    collateral.resolved_at = datetime.utcnow()
    _post_transaction(
        db,
        contract.provider,
        contract,
        collateral.amount,
        CreditTransactionType.COLLATERAL_RELEASE,
        f"Collateral released for contract #{contract.id}: {reason}",
        simulation_time,
    )
    record_event(
        db,
        "collateral.released",
        f"{collateral.amount:g} credits returned to {contract.provider.name}",
        provider_id=contract.provider_id,
        contract_id=contract.id,
        simulation_time=simulation_time,
    )


def settle_success(db: Session, contract: BarterContract, simulation_time: datetime | None = None) -> None:
    consumer = contract.consumer
    provider = contract.provider
    if consumer.credit_balance < contract.barter_cost:
        raise HTTPException(status_code=409, detail=f"{consumer.name} cannot settle contract #{contract.id}")
    _post_transaction(
        db,
        consumer,
        contract,
        -contract.barter_cost,
        CreditTransactionType.CONTRACT_PAYMENT,
        f"Paid {provider.name} for contract #{contract.id}",
        simulation_time,
    )
    _post_transaction(
        db,
        provider,
        contract,
        contract.barter_cost,
        CreditTransactionType.CONTRACT_EARNING,
        f"Earned for resources delivered under contract #{contract.id}",
        simulation_time,
    )
    release_collateral(db, contract, simulation_time=simulation_time)
    record_event(
        db,
        "credits.settled",
        f"{contract.barter_cost:g} credits transferred from {consumer.name} to {provider.name}",
        contract_id=contract.id,
        details={"amount": contract.barter_cost},
        simulation_time=simulation_time,
    )


def forfeit_collateral(db: Session, contract: BarterContract, simulation_time: datetime | None = None) -> None:
    collateral = contract.collateral
    if not collateral or collateral.status != CollateralStatus.LOCKED:
        return
    collateral.status = CollateralStatus.FORFEITED
    collateral.resolved_at = datetime.utcnow()
    # The lock already removed these credits from the provider, so only credit the consumer.
    _post_transaction(
        db,
        contract.consumer,
        contract,
        collateral.amount,
        CreditTransactionType.COMPENSATION,
        f"Compensation for failed contract #{contract.id}",
        simulation_time,
    )
    db.add(
        CreditTransaction(
            run_id=contract.run_id,
            provider_id=contract.provider_id,
            contract_id=contract.id,
            amount=0,
            transaction_type=CreditTransactionType.COLLATERAL_FORFEIT,
            balance_after=contract.provider.credit_balance,
            description=f"Collateral forfeited for contract #{contract.id}",
            simulation_time=simulation_time,
        )
    )
    record_event(
        db,
        "collateral.forfeited",
        f"{collateral.amount:g} credits forfeited by {contract.provider.name} and paid to {contract.consumer.name}",
        severity="warning",
        provider_id=contract.provider_id,
        contract_id=contract.id,
        simulation_time=simulation_time,
    )
