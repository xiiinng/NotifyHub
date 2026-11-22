import type {
  Ticket,
  TicketCategory,
  TicketComment,
  TicketHistory,
  TicketPage,
  TicketPayload,
  TicketPriority,
  TicketStats,
  TicketStatus,
  TicketUpdatePayload,
  UserDirectoryEntry,
} from '../types'
import { api } from './client'

export interface TicketQuery {
  page?: number
  page_size?: number
  status?: TicketStatus | ''
  priority?: TicketPriority | ''
  category?: TicketCategory | ''
  assignee_id?: number | ''
  q?: string
}

export async function listTicketsApi(query: TicketQuery = {}): Promise<TicketPage> {
  const { data } = await api.get<TicketPage>('/tickets', {
    params: {
      page: query.page ?? 1,
      page_size: query.page_size ?? 10,
      ...(query.status ? { status: query.status } : {}),
      ...(query.priority ? { priority: query.priority } : {}),
      ...(query.category ? { category: query.category } : {}),
      ...(query.assignee_id ? { assignee_id: query.assignee_id } : {}),
      ...(query.q?.trim() ? { q: query.q.trim() } : {}),
    },
  })
  return data
}

export async function getTicketApi(id: number): Promise<Ticket> {
  const { data } = await api.get<Ticket>(`/tickets/${id}`)
  return data
}

export async function createTicketApi(payload: TicketPayload): Promise<Ticket> {
  const { data } = await api.post<Ticket>('/tickets', payload)
  return data
}

export async function updateTicketApi(
  id: number,
  payload: TicketUpdatePayload,
): Promise<Ticket> {
  const { data } = await api.patch<Ticket>(`/tickets/${id}`, payload)
  return data
}

export async function deleteTicketApi(id: number): Promise<void> {
  await api.delete(`/tickets/${id}`)
}

export async function assignTicketApi(id: number, assigneeId: number): Promise<Ticket> {
  const { data } = await api.post<Ticket>(`/tickets/${id}/assign`, {
    assignee_id: assigneeId,
  })
  return data
}

export async function updateTicketStatusApi(
  id: number,
  status: TicketStatus,
): Promise<Ticket> {
  const { data } = await api.patch<Ticket>(`/tickets/${id}/status`, { status })
  return data
}

export async function listTicketHistoryApi(id: number): Promise<TicketHistory[]> {
  const { data } = await api.get<TicketHistory[]>(`/tickets/${id}/history`)
  return data
}

export async function listTicketCommentsApi(id: number): Promise<TicketComment[]> {
  const { data } = await api.get<TicketComment[]>(`/tickets/${id}/comments`)
  return data
}

export async function addTicketCommentApi(
  id: number,
  content: string,
): Promise<TicketComment> {
  const { data } = await api.post<TicketComment>(`/tickets/${id}/comments`, {
    content,
  })
  return data
}

export async function getTicketStatsApi(): Promise<TicketStats> {
  const { data } = await api.get<TicketStats>('/tickets/stats')
  return data
}

export async function listTicketAssigneesApi(): Promise<UserDirectoryEntry[]> {
  const { data } = await api.get<UserDirectoryEntry[]>('/tickets/assignees')
  return data
}

export async function notifyTicketCreatorApi(
  id: number,
  title: string,
  content: string,
): Promise<void> {
  await api.post(`/tickets/${id}/notify`, { title, content })
}
