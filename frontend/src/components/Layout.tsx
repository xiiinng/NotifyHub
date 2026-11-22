import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { getUnreadCountApi } from '../api/notifications'
import { useAuth } from '../auth/AuthContext'

interface NavItem {
  to: string
  label: string
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [unread, setUnread] = useState(0)

  const refreshUnread = useCallback(() => {
    if (!user) {
      setUnread(0)
      return
    }
    void getUnreadCountApi()
      .then(setUnread)
      .catch(() => setUnread(0))
  }, [user])

  useEffect(() => {
    refreshUnread()
  }, [refreshUnread, location.pathname])

  useEffect(() => {
    const handler = () => refreshUnread()
    window.addEventListener('notifyhub:unread-changed', handler)
    const timer = window.setInterval(refreshUnread, 30_000)
    return () => {
      window.removeEventListener('notifyhub:unread-changed', handler)
      window.clearInterval(timer)
    }
  }, [refreshUnread])

  const navItems: NavItem[] = [
    { to: '/tickets', label: '工单' },
    ...(user?.role === 'it_support'
      ? [{ to: '/support/tickets', label: '支持工作台' }]
      : []),
    { to: '/dashboard', label: '统计' },
    { to: '/notifications', label: '通知历史' },
    { to: '/send', label: '发送通知' },
    { to: '/templates', label: '通知模板' },
  ]

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">N</span>
          <span>NotifyHub</span>
        </div>
        <nav className="nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
            >
              <span>{item.label}</span>
              {item.to === '/notifications' && unread > 0 && (
                <span className="nav-badge" aria-label={`${unread} 条未读通知`}>
                  {unread}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-meta">
            <strong>{user?.username}</strong>
            <span>{user?.email}</span>
            <small className="role-label">
              {user?.role === 'it_support' ? 'IT 支持' : '员工'}
            </small>
          </div>
          <button className="button ghost" type="button" onClick={handleLogout}>
            退出登录
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
