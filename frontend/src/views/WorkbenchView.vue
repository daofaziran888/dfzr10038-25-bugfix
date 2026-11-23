<template>
  <section class="page" :data-module="meta.key">
    <header class="page-head">
      <div>
        <h2>{{ meta.name }}</h2>
        <p class="page-desc">{{ meta.desc }}</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">
          登记{{ meta.entity }}
        </button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">
          导出{{ meta.name }}清单
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="status-legend">
      <span v-for="item in statusSummary" :key="item.status" class="legend-item">
        {{ item.status }}：{{ item.count }}
      </span>
      <template v-if="isSample">
        <span class="legend-item">可派发：{{ dispatchableCount }}</span>
        <span class="legend-item">待补录：{{ pendingRefillCount }}</span>
      </template>
    </p>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in meta.fields" :key="column">{{ column }}</th>
          <th v-if="isSample">校验状态</th>
          <th v-if="isSample">派发已接受</th>
          <th v-if="isSample">原因</th>
          <th v-if="isLabelTask">原策略编号</th>
          <th v-if="isLabelTask">有效样本数量</th>
          <th>当前状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :data-testid="`row-${row.id}`" :data-status="String(row.status)">
          <td v-for="column in meta.fields" :key="column">{{ row[column] ?? '—' }}</td>
          <td v-if="isSample" :data-testid="`validation-${row.id}`">
            {{ row.当前校验明细?.校验状态 ?? '—' }}
          </td>
          <td v-if="isSample">{{ row.派发已接受 ? '已接受' : '未接受' }}</td>
          <td v-if="isSample" class="reason-cell">{{ row.校验原因 ?? '—' }}</td>
          <td v-if="isLabelTask">{{ row.原策略编号 ?? '—' }}</td>
          <td v-if="isLabelTask">{{ row.有效样本数量 ?? '—' }}</td>
          <td>{{ row.status }}</td>
          <td class="row-actions">
            <button
              v-for="action in rowActions(row)"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button
              v-if="isSample"
              class="link"
              type="button"
              :data-testid="`trace-${row.id}`"
              @click="showTrace(row)"
            >
              查看联动轨迹
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="meta.fields.length + 2" class="empty-state">
            暂无{{ meta.name }}数据，可先登记{{ meta.entity }}
          </td>
        </tr>
      </tbody>
    </table>

    <section v-if="isSample" class="panel" data-testid="dispatch-list">
      <h3>派发清单（仅可派发的有效范围）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>策略编号</th>
            <th>有效样本数量</th>
            <th>校验状态</th>
            <th>派发已接受</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in dispatchList" :key="String(item.策略编号)">
            <td>{{ item.原策略编号 }}</td>
            <td>{{ item.有效样本数量 }}</td>
            <td>{{ item.校验状态 }}</td>
            <td>{{ item.派发已接受 ? '已接受' : '待确认' }}</td>
            <td class="reason-cell">{{ item.原因 }}</td>
          </tr>
          <tr v-if="!dispatchList.length">
            <td colspan="5" class="empty-state">暂无可用派发范围，等待补录样本数量并再次确认</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="isSample && traceEffects.length" class="panel" data-testid="flow-trace">
      <h3>联动轨迹：{{ traceTitle }}</h3>
      <ul class="trace-list">
        <li v-for="(item, index) in traceEffects" :key="index">
          <strong>{{ item.name }}</strong>（{{ item.module }}）：{{ item.description }}
        </li>
      </ul>
    </section>

    <div v-if="sampleModal" class="modal-backdrop" data-testid="sample-modal">
      <form class="modal" @submit.prevent="submitSampleAction">
        <h3>{{ sampleModal.title }}</h3>
        <p class="page-desc">{{ sampleModal.hint }}</p>
        <label class="create-field">
          <span>样本数量</span>
          <input
            v-model="sampleModal.value"
            data-testid="sample-count-input"
            placeholder="留空表示数量未核实"
          />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="sampleModal = null">取消</button>
          <button class="btn primary" data-testid="submit-sample-action" type="submit">
            提交
          </button>
        </div>
      </form>
    </div>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记{{ meta.entity }}</h3>
        <label v-for="field in meta.fields" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input
            v-model="createValues[field]"
            :data-testid="`create-${field}`"
            :required="!(isSample && field === '样本数量')"
            :placeholder="isSample && field === '样本数量' ? '可留空，之后再补录' : ''"
          />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ meta.name }}记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  createEntry,
  downloadEntries,
  fetchDispatchList,
  fetchFlowTrace,
  listEntries,
  moduleMeta,
  runAction as applyAction,
} from '@/api/backend-service'
import type { DispatchItem, FlowEffect, EntryRow } from '@/data/types'

const props = defineProps<{ moduleKey: string }>()
const meta = moduleMeta(props.moduleKey)
const rows = ref<EntryRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = meta.fields.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})
const dispatchList = ref<DispatchItem[]>([])
const traceEffects = ref<FlowEffect[]>([])
const traceTitle = ref('')
const sampleModal = ref<{
  id: number
  action: string
  title: string
  hint: string
  value: string
} | null>(null)
const isSample = computed(() => meta.key === 'sample_strata')
const isLabelTask = computed(() => meta.key === 'label_task')
const SAMPLE_ACTIONS = ['确认出样', '补录样本数量']
const stats = computed(() => [
  { label: meta.metrics[0], value: total.value },
  { label: meta.metrics[1], value: rows.value.filter((row) => row.status === meta.statuses[1]).length },
  {
    label: meta.metrics[2],
    value: rows.value.filter((row) => row.status === meta.statuses[meta.statuses.length - 1]).length,
  },
])
const statusSummary = computed(() =>
  meta.statuses.map((status) => ({
    status,
    count: rows.value.filter((row) => String(row.status) === status).length,
  })),
)
// 区分“采样已完成但数量未核实”和“实际可以交给标注”两个阶段。
const dispatchableCount = computed(
  () => rows.value.filter((row) => row.status === '已出样' && row.当前校验明细?.可派发).length,
)
const pendingRefillCount = computed(
  () =>
    rows.value.filter(
      (row) => row.status === '已出样' && !row.当前校验明细?.可派发,
    ).length,
)

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  errorMessage.value = ''
  try {
    await downloadEntries(meta.key, filters.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(meta.fields.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const result = await createEntry(meta.key, createValues.value)
    if (!result.ok) throw new Error(result.message)
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

function rowActions(row: EntryRow): string[] {
  if (!isSample.value) return meta.actions
  // 数量待补录时先补录，再确认出样；已派发的策略不再显示补录入口。
  return meta.actions.filter((action) => {
    if (action === '补录样本数量') return !row.派发已接受
    return true
  })
}

async function runAction(action: string, row: EntryRow) {
  errorMessage.value = ''
  if (isSample.value && SAMPLE_ACTIONS.includes(action)) {
    const current = row.样本数量
    sampleModal.value = {
      id: Number(row.id),
      action,
      title: `${action} · ${row.策略编号 ?? ''}`,
      hint:
        action === '补录样本数量'
          ? '补录只更新数量，不会自动派发；仍需值班员再次确认出样。'
          : '确认出样后，只有合法的正整数样本量才会进入派发清单。',
      // 数量为待补录状态时留空，避免把历史无效值再次提交。
      value:
        action === '补录样本数量' || row.当前校验明细?.可派发
          ? current === undefined || current === null
            ? ''
            : String(current)
          : '',
    }
    return
  }
  await submitAction(Number(row.id), action, {})
}

async function submitSampleAction() {
  if (!sampleModal.value) return
  const { id, action, value } = sampleModal.value
  sampleModal.value = null
  await submitAction(id, action, { 样本数量: value })
}

async function submitAction(id: number, action: string, values: Record<string, string>) {
  errorMessage.value = ''
  try {
    const result = await applyAction(meta.key, id, action, values)
    if (!result.ok) throw new Error(result.message)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
    await reload()
  }
}

async function showTrace(row: EntryRow) {
  traceTitle.value = String(row.策略编号 ?? '')
  traceEffects.value = await fetchFlowTrace(meta.key, Number(row.id))
}

async function reload() {
  errorMessage.value = ''
  try {
    const payload = await listEntries(meta.key, filters.value)
    rows.value = payload.items
    total.value = payload.total
    if (isSample.value) {
      dispatchList.value = await fetchDispatchList()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '业务列表读取失败'
  }
}

onMounted(reload)
</script>
