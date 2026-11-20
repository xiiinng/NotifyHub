import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { getErrorMessage } from '../api/client'
import {
  createTemplateApi,
  deleteTemplateApi,
  listTemplatesApi,
  updateTemplateApi,
} from '../api/templates'
import type { Template, TemplatePayload } from '../types'

const EMPTY_FORM: TemplatePayload = { name: '', title: '', content: '' }

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN')
}

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [form, setForm] = useState<TemplatePayload>(EMPTY_FORM)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setTemplates(await listTemplatesApi())
      setError('')
    } catch (err) {
      setError(getErrorMessage(err, '模板加载失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  function resetForm() {
    setForm(EMPTY_FORM)
    setEditingId(null)
    setShowForm(false)
  }

  function startCreate() {
    setForm(EMPTY_FORM)
    setEditingId(null)
    setShowForm(true)
  }

  function startEdit(template: Template) {
    setForm({ name: template.name, title: template.title, content: template.content })
    setEditingId(template.id)
    setShowForm(true)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!form.name.trim() || !form.title.trim() || !form.content.trim()) {
      setError('名称、标题和内容都不能为空')
      return
    }

    setSubmitting(true)
    try {
      const payload = {
        name: form.name.trim(),
        title: form.title.trim(),
        content: form.content.trim(),
      }
      if (editingId === null) {
        await createTemplateApi(payload)
      } else {
        await updateTemplateApi(editingId, payload)
      }
      resetForm()
      setError('')
      await load()
    } catch (err) {
      setError(getErrorMessage(err, '保存模板失败'))
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(template: Template) {
    if (!window.confirm(`确定删除模板「${template.name}」吗？`)) {
      return
    }
    try {
      await deleteTemplateApi(template.id)
      await load()
    } catch (err) {
      setError(getErrorMessage(err, '删除模板失败'))
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>通知模板</h1>
          <p className="muted">管理你自己的通知内容模板</p>
        </div>
        <button className="button primary" type="button" onClick={startCreate}>
          新建模板
        </button>
      </header>

      {error && <div className="alert error">{error}</div>}

      {showForm && (
        <form className="card form-card" onSubmit={handleSubmit} noValidate>
          <h2>{editingId === null ? '新建模板' : '编辑模板'}</h2>
          <label className="field">
            <span>模板名称</span>
            <input
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="例如：welcome"
              maxLength={100}
            />
          </label>
          <label className="field">
            <span>通知标题</span>
            <input
              value={form.title}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
              placeholder="通知的标题"
              maxLength={200}
            />
          </label>
          <label className="field">
            <span>通知内容</span>
            <textarea
              value={form.content}
              onChange={(event) => setForm({ ...form, content: event.target.value })}
              rows={4}
              placeholder="通知的正文内容"
              maxLength={10000}
            />
          </label>
          <div className="form-actions">
            <button className="button primary" type="submit" disabled={submitting}>
              {submitting ? '保存中…' : '保存'}
            </button>
            <button className="button ghost" type="button" onClick={resetForm}>
              取消
            </button>
          </div>
        </form>
      )}

      <div className="card">
        {loading ? (
          <div className="empty">正在加载模板…</div>
        ) : templates.length === 0 ? (
          <div className="empty">还没有模板，点击右上角新建一个吧。</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>标题</th>
                  <th>内容</th>
                  <th>创建时间</th>
                  <th className="actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {templates.map((template) => (
                  <TemplateRow
                    key={template.id}
                    template={template}
                    expanded={expandedId === template.id}
                    onToggle={() =>
                      setExpandedId(expandedId === template.id ? null : template.id)
                    }
                    onEdit={() => startEdit(template)}
                    onDelete={() => void handleDelete(template)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

interface TemplateRowProps {
  template: Template
  expanded: boolean
  onToggle: () => void
  onEdit: () => void
  onDelete: () => void
}

function TemplateRow({ template, expanded, onToggle, onEdit, onDelete }: TemplateRowProps) {
  return (
    <>
      <tr>
        <td>
          <button className="link-button" type="button" onClick={onToggle}>
            {template.name}
          </button>
        </td>
        <td>{template.title}</td>
        <td className="cell-summary">{template.content}</td>
        <td className="muted">{formatTime(template.created_at)}</td>
        <td className="actions">
          <button className="button small" type="button" onClick={onEdit}>
            编辑
          </button>
          <button className="button small danger" type="button" onClick={onDelete}>
            删除
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="detail-row">
          <td colSpan={5}>
            <div className="detail-panel">
              <div>
                <strong>模板内容</strong>
                <p className="pre-wrap">{template.content}</p>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
