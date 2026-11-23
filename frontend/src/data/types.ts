/** 纯前端数据层的公共类型：与全栈版后端返回的结构保持一致，换回后端时页面不用改。 */

export type ValidationDetail = {
  校验状态?: string
  可派发?: boolean
  派发已接受?: boolean
  有效样本数量?: number | null
  样本数量原值?: string | number
}

export type EntryRow = {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  当前校验明细?: ValidationDetail
  原策略编号?: string
  有效样本数量?: number | null
  校验原因?: string
  派发已接受?: boolean
  [field: string]: unknown
}

export type DispatchItem = {
  策略编号: string
  原策略编号: string
  有效样本数量: number | null
  校验状态: string
  派发已接受: boolean
  原因: string
}

export type FlowEffect = {
  name: string
  module: string
  entry_id: number
  description: string
  timestamp: string
}

export type ModuleMeta = {
  key: string
  name: string
  entity: string
  desc: string
  fields: string[]
  statuses: string[]
  actions: string[]
  actionTargets: Record<string, string>
  metrics: string[]
}

export type PageResult = {
  items: EntryRow[]
  total: number
  page: number
  size: number
}

export type ActionResult = {
  ok: boolean
  message: string
}

export type OverviewResult = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}
