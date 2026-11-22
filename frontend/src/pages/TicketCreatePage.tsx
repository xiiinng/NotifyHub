import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getErrorMessage } from '../api/client'
import { createTicketApi } from '../api/tickets'
import type { TicketCategory, TicketPriority } from '../types'

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

export default function TicketCreatePage() {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState<TicketCategory>('hardware')
  const [priority, setPriority] = useState<TicketPriority>('medium')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    if (!title.trim() || !description.trim()) {
      setError('请填写工单标题和描述')
      return
    }

    setSubmitting(true)
    try {
      const ticket = await createTicketApi({
        title: title.trim(),
        description: description.trim(),
        category,
        priority,
      })
      navigate(`/tickets/${ticket.id}`, { replace: true })
    } catch (err) {
      setError(getErrorMessage(err, '工单创建失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>新建工单</h1>
          <p className="muted">提交 IT 服务请求后，系统会自动计算 SLA 并发送站内通知</p>
        </div>
        <Link className="button ghost" to="/tickets">
          返回列表
        </Link>
      </header>

      {error && <div className="alert error">{error}</div>}

      <form className="card form-card" onSubmit={handleSubmit} noValidate>
        <label className="field">
          <span>工单标题</span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="例如：VPN 无法连接"
            maxLength={200}
          />
        </label>
        <label className="field">
          <span>问题描述</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="请描述问题现象、影响范围和已尝试的处理方式"
            rows={6}
            maxLength={10000}
          />
        </label>
        <label className="field">
          <span>分类</span>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value as TicketCategory)}
          >
            {CATEGORY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>优先级</span>
          <select
            value={priority}
            onChange={(event) => setPriority(event.target.value as TicketPriority)}
          >
            {PRIORITY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <div className="form-actions">
          <button className="button primary" type="submit" disabled={submitting}>
            {submitting ? '创建中…' : '创建工单'}
          </button>
        </div>
      </form>
    </div>
  )
}
