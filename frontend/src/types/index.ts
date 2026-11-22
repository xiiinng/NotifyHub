export type UserRole = 'employee' | 'it_support'

export interface User {
  id: number
  username: string
  email: string
  role: UserRole
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
  user_id: number
  sender_id: number | null
  template_id: number | null
  title: string
  content: string
  status: NotificationStatus
  retry_count: number
  error_message: string | null
  read_at: string | null
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

export interface UserDirectoryEntry {
  id: number
  username: string
  email: string
  role: UserRole
}

export type TicketCategory =
  | 'hardware'
  | 'network'
  | 'software'
  | 'account'
  | 'other'

export type TicketPriority = 'low' | 'medium' | 'high' | 'urgent'

export type TicketStatus = 'pending' | 'in_progress' | 'resolved' | 'closed'

export interface Ticket {
  id: number
  ticket_no: string
  creator: UserDirectoryEntry
  assignee: UserDirectoryEntry | null
  title: string
  description: string
  category: TicketCategory
  priority: TicketPriority
  status: TicketStatus
  due_at: string | null
  is_overdue: boolean
  sla_remaining_seconds: number | null
  created_at: string
  updated_at: string
  resolved_at: string | null
  closed_at: string | null
}

export interface TicketPage {
  items: Ticket[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface TicketHistory {
  id: number
  ticket_id: number
  actor_id: number | null
  actor: UserDirectoryEntry | null
  action: string
  old_value: string | null
  new_value: string | null
  created_at: string
}

export interface TicketComment {
  id: number
  ticket_id: number
  author_id: number | null
  author: UserDirectoryEntry | null
  content: string
  created_at: string
}

export interface AssigneeStat {
  assignee_id: number
  username: string
  total: number
  open: number
}

export interface TicketStats {
  total: number
  pending: number
  in_progress: number
  resolved: number
  closed: number
  overdue: number
  unassigned: number
  priorities: Record<TicketPriority, number>
  assignees: AssigneeStat[]
}

export interface TicketPayload {
  title: string
  description: string
  category: TicketCategory
  priority: TicketPriority
}

export interface TicketUpdatePayload {
  title?: string
  description?: string
  category?: TicketCategory
  priority?: TicketPriority
  due_at?: string
}
