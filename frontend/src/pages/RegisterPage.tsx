import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { getErrorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'

export default function RegisterPage() {
  const { user, register } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (user) {
    return <Navigate to="/notifications" replace />
  }

  function validate(): string {
    if (username.trim().length < 3) {
      return '用户名至少 3 个字符'
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      return '请输入有效的邮箱地址'
    }
    if (password.length < 8) {
      return '密码至少 8 个字符'
    }
    if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
      return '密码必须同时包含字母和数字'
    }
    if (password !== confirmPassword) {
      return '两次输入的密码不一致'
    }
    return ''
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }

    setError('')
    setSubmitting(true)
    try {
      await register({
        username: username.trim(),
        email: email.trim().toLowerCase(),
        password,
      })
      navigate('/notifications', { replace: true })
    } catch (err) {
      setError(getErrorMessage(err, '注册失败，请稍后重试'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="brand-mark">N</span>
          <h1>创建账号</h1>
          <p>注册后即可管理自己的通知</p>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          <label className="field">
            <span>用户名</span>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="至少 3 个字符"
              autoComplete="username"
            />
          </label>
          <label className="field">
            <span>邮箱</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </label>
          <label className="field">
            <span>密码</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="至少 8 位，包含字母和数字"
              autoComplete="new-password"
            />
          </label>
          <label className="field">
            <span>确认密码</span>
            <input
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="再次输入密码"
              autoComplete="new-password"
            />
          </label>

          {error && <div className="alert error">{error}</div>}

          <button className="button primary block" type="submit" disabled={submitting}>
            {submitting ? '注册中…' : '注册并登录'}
          </button>
        </form>

        <p className="auth-switch">
          已有账号？<Link to="/login">返回登录</Link>
        </p>
      </div>
    </div>
  )
}
