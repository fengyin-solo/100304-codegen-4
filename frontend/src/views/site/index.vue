<template>
  <section class="page" data-module="site">
    <header class="page-head">
      <div>
        <h2>基站台账管理</h2>
        <p class="page-desc">维护基站，围绕基站编号、基站名称、基站类型、所属区县做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记基站</button>
        <button class="btn" type="button" @click="exportRows">导出基站台账清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>电磁合规栏</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td>
            <span class="compliance-tag" :class="complianceClass(String(row['电磁合规栏']))">{{ row['电磁合规栏'] ?? '待备案' }}</span>
            <div class="compliance-sub">{{ row['备案状态'] }}<template v-if="row['备案编号']"> · {{ row['备案编号'] }}</template></div>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无基站台账数据，可先登记基站</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条基站台账记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/site'
const columns = ["基站编号", "基站名称", "基站类型", "所属区县", "经纬度坐标", "铁塔高度", "入网日期", "基站状态"]
const actions = ["登记退服", "申请退网", "拆站完成"]
const statuses = ["运行中", "退服中", "已退网", "已拆除"]
const stats = [{"label": "运行基站", "value": 0}, {"label": "退服基站", "value": 0}, {"label": "退网站点", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function resetFilters() {
  filters.value = {}
  void reload()
}

function complianceClass(value: string) {
  if (value === '合格') return 'cp-pass'
  if (value === '不合格') return 'cp-fail'
  if (value === '已失效') return 'cp-expired'
  return 'cp-pending'
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '基站登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('基站台账动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '基站台账操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('基站列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '基站台账列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.compliance-tag { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; border: 1px solid var(--border); background: #f1f5f9; }
.cp-pass { background: #dcfce7; border-color: #86efac; color: #15803d; }
.cp-fail { background: #fee2e2; border-color: #fca5a5; color: #b91c1c; }
.cp-expired { background: #e2e8f0; color: #475569; }
.cp-pending { background: #fef9c3; border-color: #fde047; color: #a16207; }
.compliance-sub { font-size: 11px; color: #94a3b8; margin-top: 2px; }
</style>
