import { useEffect, useState } from 'react'
import { getErrorMessage } from '../api/client'
import { getTicketStatsApi } from '../api/tickets'
import { useAuth } from '../auth/AuthContext'
import { TICKET_PRIORITY_LABELS } from '../components/TicketBadges'
import type { TicketPriority, TicketStats } from '../types'

const PRIORITY_ORDER: TicketPriority[] = ['urgent', 'high', 'medium', 'low']

export default function DashboardPage() {
  const { user } = useAuth()
  const [stats, setStats] = useState<TicketStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    void getTicketStatsApi()
      .then((data) => {
        setStats(data)
        setError('')
      })
      .catch((err) => setError(getErrorMessage(err, '统计数据加载失败')))
      .finally(() => setLoading(false))
  }, [])

  const isSupport = user?.role === 'it_support'

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>工单统计</h1>
          <p className="muted">
            {isSupport ? '全局 IT 服务台运营数据' : '我的工单概览'}
          </p>
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}

      {loading ? (
        <div className="card empty">正在加载统计…</div>
      ) : stats ? (
        <>
          <div className="stat-grid">
            <StatCard label="工单总数" value={stats.total} />
            <StatCard label="待处理" value={stats.pending} />
            <StatCard label="处理中" value={stats.in_progress} />
            <StatCard label="已解决" value={stats.resolved} />
            <StatCard label="已关闭" value={stats.closed} />
            <StatCard label="超时" value={stats.overdue} tone="danger" />
            {isSupport && (
              <StatCard label="未分配" value={stats.unassigned} />
            )}
          </div>

          <div className="card">
            <h2>各优先级工单</h2>
            <div className="stat-grid compact">
              {PRIORITY_ORDER.map((priority) => (
                <StatCard
                  key={priority}
                  label={`${TICKET_PRIORITY_LABELS[priority]}优先级`}
                  value={stats.priorities[priority] ?? 0}
                />
              ))}
            </div>
          </div>

          {isSupport && (
            <div className="card">
              <h2>处理人员工单</h2>
              {stats.assignees.length === 0 ? (
                <div className="empty">暂无已分配工单</div>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>处理人</th>
                        <th>工单总数</th>
                        <th>进行中</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.assignees.map((item) => (
                        <tr key={item.assignee_id}>
                          <td>{item.username}</td>
                          <td>{item.total}</td>
                          <td>{item.open}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      ) : null}
    </div>
  )
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone?: 'danger'
}) {
  return (
    <div className={`stat-card${tone === 'danger' ? ' stat-danger' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
