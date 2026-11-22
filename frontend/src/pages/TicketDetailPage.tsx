import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getErrorMessage } from '../api/client'
import {
  addTicketCommentApi,
  assignTicketApi,
  deleteTicketApi,
  getTicketApi,
  listTicketAssigneesApi,
  listTicketCommentsApi,
  listTicketHistoryApi,
  notifyTicketCreatorApi,
  updateTicketApi,
  updateTicketStatusApi,
} from '../api/tickets'
import { useAuth } from '../auth/AuthContext'
import {
  TICKET_CATEGORY_LABELS,
  TICKET_PRIORITY_LABELS,
  TICKET_STATUS_LABELS,
  TicketPriorityBadge,
  TicketStatusBadge,
} from '../components/TicketBadges'
import type {
  Ticket,
  TicketCategory,
  TicketComment,
  TicketHistory,
  TicketPriority,
  TicketStatus,
  UserDirectoryEntry,
} from '../types'

const CATEGORY_OPTIONS: Array<{ value: TicketCategory; label: string }> = [
  { value: 'hardware', label: '硬件' },
  { value: 'network', label: '网络' },
  { value: 'software', label: '软件' },
  { value: 'account', label: '账号权限' },
  { value: 'other', label: '其他' },
]

const PRIORITY_OPTIONS: Array<{ value: TicketPriority; label: string }> = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'urgent', label: '紧急' },
]

function toLocalDateTimeInput(value: string | null): string {
  if (!value) {
    return ''
  }
  const date = new Date(value)
  const adjusted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return adjusted.toISOString().slice(0, 16)
}

const ALLOWED_TRANSITIONS: Record<TicketStatus, TicketStatus[]> = {
  pending: ['in_progress', 'resolved'],
  in_progress: ['resolved'],
  resolved: ['in_progress', 'closed'],
  closed: [],
}

const ACTION_LABELS: Record<string, string> = {
  created: '创建工单',
  updated: '修改基本信息',
  assigned: '分配工单',
  reassigned: '重新分配',
  status_changed: '状态变更',
  resolved: '解决工单',
  closed: '关闭工单',
  priority_changed: '修改优先级',
  due_date_changed: '调整截止时间',
  deleted: '删除工单',
}

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

function slaText(ticket: Ticket): string {
  if (ticket.due_at === null) {
    return '未设置'
  }
  if (ticket.is_overdue) {
    return `已超时（截止 ${formatTime(ticket.due_at)}）`
  }
  if (ticket.sla_remaining_seconds === null) {
    return formatTime(ticket.due_at)
  }
  const hours = Math.floor(ticket.sla_remaining_seconds / 3600)
  const minutes = Math.floor((ticket.sla_remaining_seconds % 3600) / 60)
  return `剩余 ${hours} 小时 ${minutes} 分钟（截止 ${formatTime(ticket.due_at)}）`
}

export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>()
  const ticketId = Number(id)
  const { user } = useAuth()
  const navigate = useNavigate()
  const isSupport = user?.role === 'it_support'

  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [history, setHistory] = useState<TicketHistory[]>([])
  const [comments, setComments] = useState<TicketComment[]>([])
  const [assignees, setAssignees] = useState<UserDirectoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [editTitle, setEditTitle] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editCategory, setEditCategory] = useState<TicketCategory>('other')
  const [editPriority, setEditPriority] = useState<TicketPriority>('medium')
  const [editDueAt, setEditDueAt] = useState('')
  const [originalDueAt, setOriginalDueAt] = useState('')
  const [assigneeId, setAssigneeId] = useState('')
  const [nextStatus, setNextStatus] = useState<TicketStatus>('in_progress')
  const [comment, setComment] = useState('')
  const [notifyTitle, setNotifyTitle] = useState('')
  const [notifyContent, setNotifyContent] = useState('')

  const load = useCallback(async () => {
    if (!Number.isInteger(ticketId) || ticketId <= 0) {
      setError('无效的工单编号')
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const [ticketData, historyData, commentsData] = await Promise.all([
        getTicketApi(ticketId),
        listTicketHistoryApi(ticketId),
        listTicketCommentsApi(ticketId),
      ])
      setTicket(ticketData)
      setHistory(historyData)
      setComments(commentsData)
      setEditTitle(ticketData.title)
      setEditDescription(ticketData.description)
      setEditCategory(ticketData.category)
      setEditPriority(ticketData.priority)
      const dueInput = toLocalDateTimeInput(ticketData.due_at)
      setEditDueAt(dueInput)
      setOriginalDueAt(dueInput)
      setAssigneeId(ticketData.assignee?.id.toString() ?? '')
      setNextStatus(
        ALLOWED_TRANSITIONS[ticketData.status][0] ?? ticketData.status,
      )
      setError('')
    } catch (err) {
      setError(getErrorMessage(err, '工单加载失败'))
    } finally {
      setLoading(false)
    }
  }, [ticketId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!isSupport) {
      return
    }
    void listTicketAssigneesApi()
      .then((data) => {
        setAssignees(data)
        setAssigneeId((current) => current || data[0]?.id.toString() || '')
      })
      .catch(() => setAssignees([]))
  }, [isSupport])

  async function runAction(action: () => Promise<void>, message: string) {
    setError('')
    setSuccess('')
    setSubmitting(true)
    try {
      await action()
      setSuccess(message)
      await load()
    } catch (err) {
      setError(getErrorMessage(err, '操作失败'))
    } finally {
      setSubmitting(false)
    }
  }

  async function saveBasic(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await runAction(async () => {
      await updateTicketApi(ticketId, {
        title: editTitle.trim(),
        description: editDescription.trim(),
        category: editCategory,
        ...(isSupport
          ? {
              priority: editPriority,
              ...(editDueAt && editDueAt !== originalDueAt
                ? { due_at: new Date(editDueAt).toISOString() }
                : {}),
            }
          : {}),
      })
    }, '工单信息已保存')
  }

  async function assign() {
    if (!assigneeId) {
      setError('请选择处理人')
      return
    }
    await runAction(
      async () => {
        await assignTicketApi(ticketId, Number(assigneeId))
      },
      '工单已分配',
    )
  }

  async function changeStatus() {
    await runAction(
      async () => {
        await updateTicketStatusApi(ticketId, nextStatus)
      },
      '工单状态已更新',
    )
  }

  async function addComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!comment.trim()) {
      setError('处理备注不能为空')
      return
    }
    await runAction(async () => {
      await addTicketCommentApi(ticketId, comment.trim())
      setComment('')
    }, '处理备注已添加')
  }

  async function notifyCreator(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!notifyTitle.trim() || !notifyContent.trim()) {
      setError('通知标题和内容不能为空')
      return
    }
    await runAction(async () => {
      await notifyTicketCreatorApi(ticketId, notifyTitle.trim(), notifyContent.trim())
      setNotifyTitle('')
      setNotifyContent('')
    }, '通知已发送给工单创建者')
  }

  async function removeTicket() {
    if (!window.confirm(`确定删除工单「${ticket?.title ?? ''}」吗？`)) {
      return
    }
    setError('')
    setSuccess('')
    setSubmitting(true)
    try {
      await deleteTicketApi(ticketId)
      navigate('/tickets', { replace: true })
    } catch (err) {
      setError(getErrorMessage(err, '删除工单失败'))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="page">
        <div className="card empty">正在加载工单…</div>
      </div>
    )
  }

  if (!ticket) {
    return (
      <div className="page">
        <header className="page-header">
          <h1>工单详情</h1>
          <Link className="button ghost" to="/tickets">
            返回工单列表
          </Link>
        </header>
        {error && <div className="alert error">{error}</div>}
      </div>
    )
  }

  const transitions = ALLOWED_TRANSITIONS[ticket.status]

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>工单详情</h1>
          <p className="muted">{ticket.ticket_no}</p>
        </div>
        <div className="toolbar">
          <TicketPriorityBadge priority={ticket.priority} />
          <TicketStatusBadge status={ticket.status} />
          <Link className="button ghost" to="/tickets">
            返回工单列表
          </Link>
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}
      {success && <div className="alert success">{success}</div>}

      <div className="card detail-card">
        <div className="detail-grid">
          <span>标题</span>
          <strong>{ticket.title}</strong>
          <span>分类</span>
          <span>{TICKET_CATEGORY_LABELS[ticket.category]}</span>
          <span>优先级</span>
          <span>{TICKET_PRIORITY_LABELS[ticket.priority]}</span>
          <span>状态</span>
          <span>{TICKET_STATUS_LABELS[ticket.status]}</span>
          <span>创建人</span>
          <span>
            {ticket.creator.username}（{ticket.creator.email}）
          </span>
          <span>处理人</span>
          <span>{ticket.assignee?.username ?? '未分配'}</span>
          <span>SLA</span>
          <span className={ticket.is_overdue ? 'text-danger' : ''}>
            {slaText(ticket)}
          </span>
          <span>创建时间</span>
          <span>{formatTime(ticket.created_at)}</span>
          <span>更新时间</span>
          <span>{formatTime(ticket.updated_at)}</span>
          <span>解决时间</span>
          <span>{formatTime(ticket.resolved_at)}</span>
          <span>关闭时间</span>
          <span>{formatTime(ticket.closed_at)}</span>
        </div>

        <div className="detail-content">
          <span className="muted">问题描述</span>
          <p className="pre-wrap">{ticket.description}</p>
        </div>
      </div>

      {ticket.status !== 'closed' && (
        <form className="card form-card" onSubmit={saveBasic}>
          <h2>编辑工单</h2>
          <label className="field">
            <span>工单标题</span>
            <input
              value={editTitle}
              onChange={(event) => setEditTitle(event.target.value)}
              maxLength={200}
            />
          </label>
          <label className="field">
            <span>问题描述</span>
            <textarea
              value={editDescription}
              onChange={(event) => setEditDescription(event.target.value)}
              rows={4}
              maxLength={10000}
            />
          </label>
          <label className="field">
            <span>分类</span>
            <select
              value={editCategory}
              onChange={(event) =>
                setEditCategory(event.target.value as TicketCategory)
              }
            >
              {CATEGORY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          {isSupport && (
            <>
              <label className="field">
                <span>优先级</span>
                <select
                  value={editPriority}
                  onChange={(event) =>
                    setEditPriority(event.target.value as TicketPriority)
                  }
                >
                  {PRIORITY_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>截止时间</span>
                <input
                  type="datetime-local"
                  value={editDueAt}
                  onChange={(event) => setEditDueAt(event.target.value)}
                />
              </label>
            </>
          )}
          <div className="form-actions">
            <button className="button primary" type="submit" disabled={submitting}>
              保存修改
            </button>
          </div>
        </form>
      )}

      {isSupport && (
        <div className="card form-card">
          <h2>支持操作</h2>
          <label className="field">
            <span>处理人</span>
            <select
              value={assigneeId}
              onChange={(event) => setAssigneeId(event.target.value)}
            >
              <option value="">请选择 IT 支持人员</option>
              {assignees.map((assignee) => (
                <option key={assignee.id} value={assignee.id}>
                  {assignee.username}（{assignee.email}）
                </option>
              ))}
            </select>
          </label>
          <div className="form-actions">
            <button
              className="button"
              type="button"
              onClick={() => void assign()}
              disabled={submitting}
            >
              分配工单
            </button>
          </div>

          {transitions.length > 0 && (
            <>
              <label className="field">
                <span>更新状态</span>
                <select
                  value={nextStatus}
                  onChange={(event) =>
                    setNextStatus(event.target.value as TicketStatus)
                  }
                >
                  {transitions.map((status) => (
                    <option key={status} value={status}>
                      {TICKET_STATUS_LABELS[status]}
                    </option>
                  ))}
                </select>
              </label>
              <div className="form-actions">
                <button
                  className="button"
                  type="button"
                  onClick={() => void changeStatus()}
                  disabled={submitting}
                >
                  更新状态
                </button>
              </div>
            </>
          )}

          <form onSubmit={addComment}>
            <label className="field">
              <span>处理备注</span>
              <textarea
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                rows={3}
                maxLength={5000}
                placeholder="记录排查过程或处理方案"
              />
            </label>
            <div className="form-actions">
              <button className="button" type="submit" disabled={submitting}>
                添加备注
              </button>
            </div>
          </form>

          <form onSubmit={notifyCreator}>
            <label className="field">
              <span>通知标题</span>
              <input
                value={notifyTitle}
                onChange={(event) => setNotifyTitle(event.target.value)}
                maxLength={200}
              />
            </label>
            <label className="field">
              <span>通知内容</span>
              <textarea
                value={notifyContent}
                onChange={(event) => setNotifyContent(event.target.value)}
                rows={3}
                maxLength={10000}
              />
            </label>
            <div className="form-actions">
              <button className="button" type="submit" disabled={submitting}>
                发送通知
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <h2>处理记录</h2>
        {history.length === 0 ? (
          <div className="empty">暂无处理记录</div>
        ) : (
          <ul className="timeline">
            {history.map((item) => (
              <li key={item.id}>
                <strong>{ACTION_LABELS[item.action] ?? item.action}</strong>
                <span className="muted">
                  {item.actor?.username ?? '系统'} · {formatTime(item.created_at)}
                </span>
                {(item.old_value || item.new_value) && (
                  <p className="pre-wrap">
                    {item.old_value ?? '-'} → {item.new_value ?? '-'}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h2>处理备注</h2>
        {comments.length === 0 ? (
          <div className="empty">暂无处理备注</div>
        ) : (
          <ul className="comment-list">
            {comments.map((item) => (
              <li key={item.id}>
                <strong>{item.author?.username ?? '系统'}</strong>
                <span className="muted">{formatTime(item.created_at)}</span>
                <p className="pre-wrap">{item.content}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      {isSupport && ticket.status !== 'closed' && (
        <div className="form-actions">
          <button
            className="button danger"
            type="button"
            onClick={() => {
              if (ticket.status === 'pending' && ticket.assignee === null) {
                void removeTicket()
              } else {
                setError('只有未分配且待处理的工单可以删除')
              }
            }}
          >
            删除工单
          </button>
        </div>
      )}
    </div>
  )
}
