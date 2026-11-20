import type { Notification, NotificationPage, NotificationStatus } from '../types'
import { api } from './client'

export interface NotificationQuery {
  page?: number
  page_size?: number
  status?: NotificationStatus | ''
}

export interface CreateNotificationPayload {
  template_id?: number
  title?: string
  content?: string
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
    },
  })
  return data
}

export async function getNotificationApi(id: number): Promise<Notification> {
  const { data } = await api.get<Notification>(`/notifications/${id}`)
  return data
}

export function isActiveStatus(status: NotificationStatus): boolean {
  return status === 'pending' || status === 'processing'
}
