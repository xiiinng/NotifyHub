import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { getErrorMessage } from '../api/client'
import { createNotificationApi } from '../api/notifications'
import { listTemplatesApi } from '../api/templates'
import StatusBadge from '../components/StatusBadge'
import type { Notification, Template } from '../types'

type Mode = 'template' | 'manual'

export default function SendPage() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [mode, setMode] = useState<Mode>('manual')
  const [templateId, setTemplateId] = useState<number | ''>('')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<Notification | null>(null)
  const [loadingTemplates, setLoadingTemplates] = useState(true)

  const loadTemplates = useCallback(async () => {
    setLoadingTemplates(true)
    try {
      const data = await listTemplatesApi()
      setTemplates(data)
      if (data.length > 0) {
        setMode('template')
        setTemplateId(data[0].id)
      }
    } catch (err) {
      setError(getErrorMessage(err, '模板加载失败，仍可手动输入内容'))
    } finally {
      setLoadingTemplates(false)
    }
  }, [])

  useEffect(() => {
    void loadTemplates()
  }, [loadTemplates])

  const selectedTemplate = templates.find((item) => item.id === templateId) ?? null

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setResult(null)

    if (mode === 'template' && templateId === '') {
      setError('请选择一个模板')
      return
    }
    if (mode === 'manual' && (!title.trim() || !content.trim())) {
      setError('请填写标题和内容')
      return
    }

    setSubmitting(true)
    try {
      const notification =
        mode === 'template'
          ? await createNotificationApi({ template_id: Number(templateId) })
          : await createNotificationApi({
              title: title.trim(),
              content: content.trim(),
            })
      setResult(notification)
      setTitle('')
      setContent('')
    } catch (err) {
      setError(getErrorMessage(err, '创建通知失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>发送通知</h1>
          <p className="muted">通知会进入异步队列，由 Celery Worker 处理</p>
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}

      {result && (
        <div className="alert success">
          <span>
            通知 #{result.id} 已创建，当前状态：<StatusBadge status={result.status} />
          </span>
          <Link to={`/notifications/${result.id}`}>查看详情</Link>
        </div>
      )}

      <form className="card form-card" onSubmit={handleSubmit} noValidate>
        <div className="segmented">
          <button
            type="button"
            className={mode === 'template' ? 'segment active' : 'segment'}
            onClick={() => setMode('template')}
          >
            使用模板
          </button>
          <button
            type="button"
            className={mode === 'manual' ? 'segment active' : 'segment'}
            onClick={() => setMode('manual')}
          >
            手动填写
          </button>
        </div>

        {mode === 'template' ? (
          <>
            {loadingTemplates ? (
              <div className="empty">正在加载模板…</div>
            ) : templates.length === 0 ? (
              <div className="empty">
                还没有模板，<Link to="/templates">先去创建一个模板</Link>。
              </div>
            ) : (
              <>
                <label className="field">
                  <span>选择模板</span>
                  <select
                    value={templateId}
                    onChange={(event) => setTemplateId(Number(event.target.value))}
                  >
                    {templates.map((template) => (
                      <option key={template.id} value={template.id}>
                        {template.name} - {template.title}
                      </option>
                    ))}
                  </select>
                </label>
                {selectedTemplate && (
                  <div className="preview">
                    <strong>{selectedTemplate.title}</strong>
                    <p className="pre-wrap">{selectedTemplate.content}</p>
                    <span className="muted">
                      发送时会复制当前内容作为快照，之后修改模板不影响已发送通知。
                    </span>
                  </div>
                )}
              </>
            )}
          </>
        ) : (
          <>
            <label className="field">
              <span>标题</span>
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="通知标题"
                maxLength={200}
              />
            </label>
            <label className="field">
              <span>内容</span>
              <textarea
                value={content}
                onChange={(event) => setContent(event.target.value)}
                rows={5}
                placeholder="通知正文"
                maxLength={10000}
              />
            </label>
          </>
        )}

        <div className="form-actions">
          <button
            className="button primary"
            type="submit"
            disabled={submitting || (mode === 'template' && templates.length === 0)}
          >
            {submitting ? '发送中…' : '发送通知'}
          </button>
        </div>
      </form>
    </div>
  )
}
