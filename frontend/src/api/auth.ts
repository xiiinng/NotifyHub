import type { TokenResponse, User } from '../types'
import { api } from './client'

export interface RegisterPayload {
  username: string
  email: string
  password: string
}

export async function loginApi(email: string, password: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/auth/login', { email, password })
  return data
}

export async function registerApi(payload: RegisterPayload): Promise<User> {
  const { data } = await api.post<User>('/auth/register', payload)
  return data
}

export async function meApi(): Promise<User> {
  const { data } = await api.get<User>('/auth/me')
  return data
}
