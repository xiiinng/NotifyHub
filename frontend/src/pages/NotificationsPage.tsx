import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getErrorMessage } from '../api/client'
import { isActiveStatus, listNotificationsApi } from '../api/notifications'
import StatusBadge from '../components/StatusBadge'
import type { Notification, NotificationStatus } from '../types'

const PAGE_SIZE = 10

const STATUS_OPTIONS: Array<{ value: NotificationStatus | ''; label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '等待中' },
  { value: 'processing', label: '处理中' },
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
]

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN')
}

export default function NotificationsPage() {
  const [items, setItems] = useState<Notification[]>([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(0)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<NotificationStatus | ''>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(
    async (silent = false) => {
      if (!silent) {
        setLoading(true)
      }
      try {
        const data = await listNotificationsApi({
          page,
          page_size: PAGE_SIZE,
          status,
        })
        setItems(data.items)
        setTotal(data.total)
        setPages(data.pages)
        setError('')
      } catch (err) {
        setError(getErrorMessage(err, '通知列表加载失败'))
      } finally {
        if (!silent) {
          setLoading(false)
        }
      }
    },
    [page, status],
  )

  useEffect(() => {
    void load()
  }, [load])

  // 有未完成任务时轮询刷新，展示异步处理结果
  useEffect(() => {
    if (!items.some((item) => isActiveStatus(item.status))) {
      return
    }
    const timer = window.setInterval(() => {
      void load(true)
    }, 3000)
    return () => window.clearInterval(timer)
  }, [items, load])

  const firstRow = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const lastRow = Math.min(page * PAGE_SIZE, total)

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>通知历史</h1>
          <p className="muted">只展示属于你自己的通知</p>
        </div>
        <div className="toolbar">
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as NotificationStatus | '')
              setPage(1)
            }}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value || 'all'} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <button className="button ghost" type="button" onClick={() => void load()}>
            刷新
          </button>
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}

      <div className="card">
        {loading ? (
          <div className="empty">正在加载通知…</div>
        ) : items.length === 0 ? (
          <div className="empty">
            暂无通知，去<Link to="/send">发送一条</Link>吧。
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>标题</th>
                  <th>内容摘要</th>
                  <th>状态</th>
                  <th>重试</th>
                  <th>创建时间</th>
                  <th className="actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.title}</td>
                    <td className="cell-summary">{item.content}</td>
                    <td>
                      <StatusBadge status={item.status} />
                    </td>
                    <td>{item.retry_count}</td>
                    <td className="muted">{formatTime(item.created_at)}</td>
                    <td className="actions">
                      <Link className="button small" to={`/notifications/${item.id}`}>
                        详情
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="pagination">
        <span className="muted">
          {total === 0 ? '共 0 条' : `第 ${firstRow}-${lastRow} 条，共 ${total} 条`}
        </span>
        <div className="pagination-actions">
          <button
            className="button small"
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            上一页
          </button>
          <span className="muted">
            {page} / {Math.max(pages, 1)}
          </span>
          <button
            className="button small"
            type="button"
            disabled={pages === 0 || page >= pages}
            onClick={() => setPage((current) => current + 1)}
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  )
}
