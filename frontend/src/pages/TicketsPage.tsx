import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { getErrorMessage } from '../api/client'
import {
  listTicketAssigneesApi,
  listTicketsApi,
} from '../api/tickets'
import { useAuth } from '../auth/AuthContext'
import {
  TICKET_CATEGORY_LABELS,
  TicketPriorityBadge,
  TicketStatusBadge,
} from '../components/TicketBadges'
import type {
  Ticket,
  TicketCategory,
  TicketPriority,
  TicketStatus,
  UserDirectoryEntry,
} from '../types'

const PAGE_SIZE = 10

const STATUS_OPTIONS: Array<{ value: TicketStatus | ''; label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '待处理' },
  { value: 'in_progress', label: '处理中' },
  { value: 'resolved', label: '已解决' },
  { value: 'closed', label: '已关闭' },
]

const PRIORITY_OPTIONS: Array<{ value: TicketPriority | ''; label: string }> = [
  { value: '', label: '全部优先级' },
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'urgent', label: '紧急' },
]

const CATEGORY_OPTIONS: Array<{ value: TicketCategory | ''; label: string }> = [
  { value: '', label: '全部分类' },
  { value: 'hardware', label: '硬件' },
  { value: 'network', label: '网络' },
  { value: 'software', label: '软件' },
  { value: 'account', label: '账号权限' },
  { value: 'other', label: '其他' },
]

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

function slaLabel(ticket: Ticket): string {
  if (ticket.is_overdue) {
    return '已超时'
  }
  if (ticket.sla_remaining_seconds === null) {
    return '-'
  }
  if (ticket.sla_remaining_seconds <= 0) {
    return '已到期'
  }
  const hours = Math.floor(ticket.sla_remaining_seconds / 3600)
  const minutes = Math.floor((ticket.sla_remaining_seconds % 3600) / 60)
  return hours > 0 ? `${hours} 小时 ${minutes} 分钟` : `${minutes} 分钟`
}

export default function TicketsPage({ supportMode = false }: { supportMode?: boolean }) {
  const { user } = useAuth()
  const isSupport = user?.role === 'it_support'
  const [items, setItems] = useState<Ticket[]>([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(0)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<TicketStatus | ''>('')
  const [priority, setPriority] = useState<TicketPriority | ''>('')
  const [category, setCategory] = useState<TicketCategory | ''>('')
  const [assigneeId, setAssigneeId] = useState('')
  const [keyword, setKeyword] = useState('')
  const [search, setSearch] = useState('')
  const [assignees, setAssignees] = useState<UserDirectoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listTicketsApi({
        page,
        page_size: PAGE_SIZE,
        status,
        priority,
        category,
        assignee_id: assigneeId ? Number(assigneeId) : '',
        q: search,
      })
      setItems(data.items)
      setTotal(data.total)
      setPages(data.pages)
      setError('')
    } catch (err) {
      setError(getErrorMessage(err, '工单列表加载失败'))
    } finally {
      setLoading(false)
    }
  }, [page, status, priority, category, assigneeId, search])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!isSupport) {
      return
    }
    void listTicketAssigneesApi()
      .then(setAssignees)
      .catch(() => setAssignees([]))
  }, [isSupport])

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPage(1)
    setSearch(keyword)
  }

  const heading = supportMode
    ? '支持工作台'
    : isSupport
      ? '全部工单'
      : '我的工单'

  const firstRow = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const lastRow = Math.min(page * PAGE_SIZE, total)

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{heading}</h1>
          <p className="muted">
            {isSupport ? '查看和处理全部 IT 服务工单' : '查看和跟踪自己的 IT 服务工单'}
          </p>
        </div>
        <Link className="button primary" to="/tickets/new">
          新建工单
        </Link>
      </header>

      {error && <div className="alert error">{error}</div>}

      <div className="card">
        <div className="filter-bar">
          <form className="search-form" onSubmit={handleSearch}>
            <input
              aria-label="搜索工单"
              placeholder="搜索标题、编号或描述"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            <button className="button" type="submit">
              搜索
            </button>
          </form>
          <select
            aria-label="状态筛选"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as TicketStatus | '')
              setPage(1)
            }}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value || 'all'} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <select
            aria-label="优先级筛选"
            value={priority}
            onChange={(event) => {
              setPriority(event.target.value as TicketPriority | '')
              setPage(1)
            }}
          >
            {PRIORITY_OPTIONS.map((option) => (
              <option key={option.value || 'all'} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <select
            aria-label="分类筛选"
            value={category}
            onChange={(event) => {
              setCategory(event.target.value as TicketCategory | '')
              setPage(1)
            }}
          >
            {CATEGORY_OPTIONS.map((option) => (
              <option key={option.value || 'all'} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {isSupport && (
            <select
              aria-label="处理人筛选"
              value={assigneeId}
              onChange={(event) => {
                setAssigneeId(event.target.value)
                setPage(1)
              }}
            >
              <option value="">全部处理人</option>
              {assignees.map((assignee) => (
                <option key={assignee.id} value={assignee.id}>
                  {assignee.username}
                </option>
              ))}
            </select>
          )}
          <button className="button ghost" type="button" onClick={() => void load()}>
            刷新
          </button>
        </div>
      </div>

      <div className="card">
        {loading ? (
          <div className="empty">正在加载工单…</div>
        ) : items.length === 0 ? (
          <div className="empty">暂无工单</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>编号</th>
                  <th>标题</th>
                  <th>分类</th>
                  <th>优先级</th>
                  <th>状态</th>
                  <th>处理人</th>
                  <th>SLA</th>
                  <th>创建时间</th>
                  <th className="actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((ticket) => (
                  <tr key={ticket.id}>
                    <td className="mono">{ticket.ticket_no}</td>
                    <td>{ticket.title}</td>
                    <td>{TICKET_CATEGORY_LABELS[ticket.category]}</td>
                    <td>
                      <TicketPriorityBadge priority={ticket.priority} />
                    </td>
                    <td>
                      <TicketStatusBadge status={ticket.status} />
                    </td>
                    <td>{ticket.assignee?.username ?? '未分配'}</td>
                    <td className={ticket.is_overdue ? 'text-danger' : ''}>
                      {slaLabel(ticket)}
                    </td>
                    <td className="muted">{formatTime(ticket.created_at)}</td>
                    <td className="actions">
                      <Link className="button small" to={`/tickets/${ticket.id}`}>
                        查看详情
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
