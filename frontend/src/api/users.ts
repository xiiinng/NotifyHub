import type { UserDirectoryEntry } from '../types'
import { api } from './client'

export async function listUserDirectoryApi(
  query = '',
): Promise<UserDirectoryEntry[]> {
  const { data } = await api.get<UserDirectoryEntry[]>('/users/directory', {
    params: query.trim() ? { q: query.trim() } : {},
  })
  return data
}
