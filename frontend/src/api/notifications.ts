import type { Notification, NotificationPage, NotificationStatus } from '../types'
import { api } from './client'

export interface NotificationQuery {
  page?: number
  page_size?: number
  status?: NotificationStatus | ''
  unread_only?: boolean
}

export interface CreateNotificationPayload {
  template_id?: number
  title?: string
  content?: string
  recipient_user_id?: number
}

export async function createNotificationApi(
  payload: CreateNotificationPayload,
): Promise<Notification> {
  const { data } = await api.post<Notification>('/notifications', payload)
  return data
}

export async function listNotificationsApi(
  query: NotificationQuery = {},
): Promise<NotificationPage> {
  const { data } = await api.get<NotificationPage>('/notifications', {
    params: {
      page: query.page ?? 1,
      page_size: query.page_size ?? 10,
      ...(query.status ? { status: query.status } : {}),
      ...(query.unread_only ? { unread_only: true } : {}),
    },
  })
  return data
}

export async function getNotificationApi(id: number): Promise<Notification> {
  const { data } = await api.get<Notification>(`/notifications/${id}`)
  return data
}

export async function getUnreadCountApi(): Promise<number> {
  const { data } = await api.get<{ unread_count: number }>(
    '/notifications/unread-count',
  )
  return data.unread_count
}

export async function markNotificationReadApi(id: number): Promise<Notification> {
  const { data } = await api.patch<Notification>(`/notifications/${id}/read`)
  return data
}

export async function markAllNotificationsReadApi(): Promise<number> {
  const { data } = await api.post<{ updated: number }>('/notifications/read-all')
  return data.updated
}

export function isActiveStatus(status: NotificationStatus): boolean {
  return status === 'pending' || status === 'processing'
}
