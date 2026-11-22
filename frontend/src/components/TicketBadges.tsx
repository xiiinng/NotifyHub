import type { TicketPriority, TicketStatus } from '../types'

const STATUS_LABELS: Record<TicketStatus, string> = {
  pending: '待处理',
  in_progress: '处理中',
  resolved: '已解决',
  closed: '已关闭',
}

const PRIORITY_LABELS: Record<TicketPriority, string> = {
  low: '低',
  medium: '中',
  high: '高',
  urgent: '紧急',
}

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span className={`ticket-badge ticket-status-${status}`}>
      {STATUS_LABELS[status]}
    </span>
  )
}

export function TicketPriorityBadge({ priority }: { priority: TicketPriority }) {
  return (
    <span className={`ticket-badge ticket-priority-${priority}`}>
      {PRIORITY_LABELS[priority]}
    </span>
  )
}

export const TICKET_STATUS_LABELS = STATUS_LABELS
export const TICKET_PRIORITY_LABELS = PRIORITY_LABELS

export const TICKET_CATEGORY_LABELS: Record<string, string> = {
  hardware: '硬件',
  network: '网络',
  software: '软件',
  account: '账号权限',
  other: '其他',
}
