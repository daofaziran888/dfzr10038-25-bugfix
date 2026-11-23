import { request } from './client'
import { moduleMeta } from '@/data/modules'
import type {
  ActionResult,
  DispatchItem,
  EntryRow,
  FlowEffect,
  OverviewResult,
  PageResult,
} from '@/data/types'

export { moduleMeta }

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
  values: Record<string, string> = {},
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action, values }),
  })
  return await response.json()
}

export async function fetchDispatchList(): Promise<DispatchItem[]> {
  const response = await request('/api/sample_strata/dispatch-list')
  if (!response.ok) throw new Error('派发清单读取失败')
  const payload = (await response.json()) as { items: DispatchItem[] }
  return payload.items
}

export async function fetchFlowTrace(key: string, id: number): Promise<FlowEffect[]> {
  const response = await request(`/api/${key}/${id}/flow-trace`)
  if (!response.ok) throw new Error('联动轨迹读取失败')
  const payload = (await response.json()) as { effects: FlowEffect[] }
  return payload.effects
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}
