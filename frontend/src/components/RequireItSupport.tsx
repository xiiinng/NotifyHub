import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function RequireItSupport() {
  const { user, loading } = useAuth()

  if (loading) {
    return <div className="page-loading">正在加载权限…</div>
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  if (user.role !== 'it_support') {
    return (
      <div className="page">
        <div className="alert error">无权限访问 IT 支持页面</div>
      </div>
    )
  }
  return <Outlet />
}
