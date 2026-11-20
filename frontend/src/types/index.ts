export interface User {
  id: number
  username: string
  email: string
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface Template {
  id: number
  name: string
  title: string
  content: string
  created_at: string
}

export interface TemplatePayload {
  name: string
  title: string
  content: string
}

export type NotificationStatus = 'pending' | 'processing' | 'success' | 'failed'

export interface Notification {
  id: number
  template_id: number | null
  title: string
  content: string
  status: NotificationStatus
  retry_count: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface NotificationPage {
  items: Notification[]
  total: number
  page: number
  page_size: number
  pages: number
}
