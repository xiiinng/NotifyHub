import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getErrorMessage } from '../api/client'
import { getNotificationApi, isActiveStatus } from '../api/notifications'
import StatusBadge from '../components/StatusBadge'
import type { Notification } from '../types'

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN')
}

export default function NotificationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const notificationId = Number(id)
  const [notification, setNotification] = useState<Notification | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const data = await getNotificationApi(notificationId)
      setNotification(data)
      setError('')
    } catch (err) {
      setError(getErrorMessage(err, '通知加载失败'))
    } finally {
      setLoading(false)
    }
  }, [notificationId])

  useEffect(() => {
    if (!Number.isInteger(notificationId) || notificationId <= 0) {
      setError('无效的通知编号')
      setLoading(false)
      return
    }
    void load()
  }, [load, notificationId])

  useEffect(() => {
    if (!notification || !isActiveStatus(notification.status)) {
      return
    }
    const timer = window.setInterval(() => {
      void load()
    }, 2000)
    return () => window.clearInterval(timer)
  }, [notification, load])

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>通知详情</h1>
          <p className="muted">通知 #{Number.isInteger(notificationId) ? notificationId : '-'}</p>
        </div>
        <Link className="button ghost" to="/notifications">
          返回列表
        </Link>
      </header>

      {error && <div className="alert error">{error}</div>}

      {loading ? (
        <div className="card empty">正在加载通知…</div>
      ) : notification ? (
        <div className="card detail-card">
          <div className="detail-grid">
            <span>标题</span>
            <strong>{notification.title}</strong>
            <span>状态</span>
            <span>
              <StatusBadge status={notification.status} />
            </span>
            <span>重试次数</span>
            <span>{notification.retry_count}</span>
            <span>模板</span>
            <span>{notification.template_id ? `#${notification.template_id}` : '无（手动创建）'}</span>
            <span>创建时间</span>
            <span>{formatTime(notification.created_at)}</span>
            <span>更新时间</span>
            <span>{formatTime(notification.updated_at)}</span>
          </div>

          <div className="detail-content">
            <span className="muted">通知内容</span>
            <p className="pre-wrap">{notification.content}</p>
          </div>

          {notification.error_message && (
            <div className="alert error">
              处理信息：{notification.error_message}
            </div>
          )}

          {isActiveStatus(notification.status) && (
            <p className="muted">通知正在异步处理中，页面会自动刷新状态。</p>
          )}
        </div>
      ) : null}
    </div>
  )
}
