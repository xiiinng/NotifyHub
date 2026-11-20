import type { Template, TemplatePayload } from '../types'
import { api } from './client'

export async function listTemplatesApi(): Promise<Template[]> {
  const { data } = await api.get<Template[]>('/templates')
  return data
}

export async function createTemplateApi(payload: TemplatePayload): Promise<Template> {
  const { data } = await api.post<Template>('/templates', payload)
  return data
}

export async function updateTemplateApi(
  id: number,
  payload: Partial<TemplatePayload>,
): Promise<Template> {
  const { data } = await api.put<Template>(`/templates/${id}`, payload)
  return data
}

export async function deleteTemplateApi(id: number): Promise<void> {
  await api.delete(`/templates/${id}`)
}
