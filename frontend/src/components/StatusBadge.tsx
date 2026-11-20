import type { NotificationStatus } from '../types'

const LABELS: Record<NotificationStatus, string> = {
  pending: '等待中',
  processing: '处理中',
  success: '成功',
  failed: '失败',
}

export default function StatusBadge({ status }: { status: NotificationStatus }) {
  return <span className={`badge badge-${status}`}>{LABELS[status]}</span>
}
