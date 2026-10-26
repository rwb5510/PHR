const API = '/api'

export async function api(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers)
  const isForm = typeof FormData !== 'undefined' && init.body instanceof FormData
  if (!isForm && init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await fetch(API + path, {
    ...init,
    headers,
    credentials: 'include',
  })
  return res
}

export async function apiJson<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await api(path, init)
  if (res.status === 204) return {} as T
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = (data as { detail?: string }).detail || res.statusText
    throw new Error(String(detail))
  }
  return data as T
}
