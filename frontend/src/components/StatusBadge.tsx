import type { ContractStatus } from '../types'

export function StatusBadge({ status }: { status: ContractStatus | string }) {
  return <span className={`status status-${status.toLowerCase()}`}>{status}</span>
}

