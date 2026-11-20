import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import Layout from './components/Layout'
import RequireAuth from './components/RequireAuth'
import LoginPage from './pages/LoginPage'
import NotificationDetailPage from './pages/NotificationDetailPage'
import NotificationsPage from './pages/NotificationsPage'
import RegisterPage from './pages/RegisterPage'
import SendPage from './pages/SendPage'
import TemplatesPage from './pages/TemplatesPage'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<Layout />}>
              <Route path="/notifications" element={<NotificationsPage />} />
              <Route path="/notifications/:id" element={<NotificationDetailPage />} />
              <Route path="/send" element={<SendPage />} />
              <Route path="/templates" element={<TemplatesPage />} />
            </Route>
          </Route>
          <Route path="/" element={<Navigate to="/notifications" replace />} />
          <Route path="*" element={<Navigate to="/notifications" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
