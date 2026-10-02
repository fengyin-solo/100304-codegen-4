/** 统一请求封装：拼后端地址、自动带登录 token、把越权/校验原因抛给页面。 */
import { useSessionStore } from '@/stores/session'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const session = useSessionStore()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (session.token) {
    headers.Authorization = `Bearer ${session.token}`
  }
  return fetch(url, {
    headers,
    ...init,
  }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

/** 发请求并把后端的业务/权限错误原文带出来（403 时 detail 写明缺哪项授权）。 */
export async function sendJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, init)
  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }
  if (!response.ok) {
    const detail =
      (payload as { detail?: string } | null)?.detail ?? `接口返回 ${response.status}，操作未生效`
    throw new ApiError(response.status, detail)
  }
  return payload as T
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}
