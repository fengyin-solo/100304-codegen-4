<template>
  <section class="page" data-module="emfiling">
    <header class="page-head">
      <div>
        <h2>基站电磁环境备案</h2>
        <p class="page-desc">
          监测点位按功率密度与监测日期登记，越线点位一律记不合格；备案文书沿
          待提交 → 已受理 → 已备案 → 已失效 流转，退回补交只补缺份材料；换版重算存量、留档按监测当时版本。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记备案</button>
        <button class="btn" type="button" @click="reload">刷新档案</button>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">现行限值</span>
        <strong class="stat-value">{{ currentLimit ? currentLimit['功率密度限值'] : '—' }} W/m²</strong>
        <span class="stat-sub">{{ currentLimit?.['标准号'] }}</span>
      </article>
      <article v-for="s in statusStats" :key="s.label" class="stat-card">
        <span class="stat-label">{{ s.label }}</span>
        <strong class="stat-value">{{ s.value }}</strong>
      </article>
    </div>

    <p v-if="message" class="notice" :class="messageOk ? 'ok' : 'error-text'">{{ message }}</p>

    <div class="em-grid">
      <!-- 左：备案档案列表 -->
      <div class="em-col">
        <form class="filter-bar" @submit.prevent="reload">
          <label class="filter-item">
            <span>备案/站点编号</span>
            <input v-model="keyword" placeholder="按编号检索" />
          </label>
          <label class="filter-item">
            <span>文书状态</span>
            <select v-model="statusFilter">
              <option value="">全部</option>
              <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
            </select>
          </label>
          <button class="btn" type="submit">查询</button>
        </form>

        <table class="data-table">
          <thead>
            <tr>
              <th>备案编号</th><th>站点编号</th><th>状态</th><th>备案结论</th>
              <th>越线点位</th><th>缺交材料</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="String(row.id)"
              :class="{ active: selected?.id === row.id }"
              style="cursor: pointer"
              @click="selectFiling(row)"
            >
              <td>{{ row['备案编号'] }}</td>
              <td>{{ row['站点编号'] }}</td>
              <td>{{ row.status }}</td>
              <td>{{ row['备案结论'] ?? '—' }}</td>
              <td :class="row['越线点位数'] ? 'error-text' : ''">{{ row['越线点位数'] }}</td>
              <td>{{ (row['缺交材料'] || []).join('、') || '—' }}</td>
            </tr>
            <tr v-if="!rows.length">
              <td colspan="6" class="empty-state">暂无备案档案</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 右：单份备案的档案明细 -->
      <div class="em-col detail-col">
        <template v-if="selected">
          <h3>{{ selected['备案编号'] }} · {{ selected['站点名称'] }}</h3>
          <p class="detail-meta">
            状态：{{ selected.status }} ｜ 结论：{{ selected['备案结论'] ?? '尚未签发' }}
            <br />
            现行限值重算：{{ selected['全部点位现行合格'] ? '全部点位合格' : '存在点位越线 ' + selected['现行限值判定'] + ' W/m²' }}
          </p>

          <div class="action-bar">
            <button class="btn" type="button" :disabled="selected.status !== '待提交'" @click="submitFiling">提交受理</button>
            <button class="btn" type="button" :disabled="selected.status !== '已受理'" @click="returnFiling">退回补正</button>
            <button
              class="btn primary"
              type="button"
              :disabled="selected.status !== '已受理'"
              @click="decide('备案合格')"
            >签发合格</button>
            <button
              class="btn danger"
              type="button"
              :disabled="selected.status !== '已受理'"
              @click="decide('备案不合格')"
            >签发不合格</button>
            <button class="btn" type="button" :disabled="['已失效'].includes(selected.status)" @click="expireFiling">置为失效</button>
          </div>
          <p class="role-hint">当前角色：<strong>{{ session.role }}</strong>；备案结论签发仅限环保归口管理员，越权会被打回并写明缺的授权项。</p>

          <h4>材料清单（退回补交只收缺的几份，已交的不再重复交）</h4>
          <table class="data-table mini">
            <thead><tr><th>材料名称</th><th>状态</th><th>提交时间</th><th></th></tr></thead>
            <tbody>
              <tr v-for="m in selected['材料']" :key="String(m.id)">
                <td>{{ m['材料名称'] }}</td>
                <td :class="m.status === '已提交' ? 'ok-text' : 'error-text'">{{ m.status }}</td>
                <td>{{ m['提交时间'] ?? '—' }}</td>
                <td>
                  <button
                    class="link"
                    type="button"
                    :disabled="m.status === '已提交' || selected.status !== '待提交'"
                    @click="supplement(m['材料名称'])"
                  >补交</button>
                </td>
              </tr>
            </tbody>
          </table>

          <h4>监测点位（功率密度 W/m²，留档按监测当时限值，现行列按新版重算）</h4>
          <table class="data-table mini">
            <thead><tr><th>点位编号</th><th>功率密度</th><th>监测日期</th><th>留档结论（{{ '按当时版' }}）</th><th>现行限值结论</th></tr></thead>
            <tbody>
              <tr v-for="p in selectedPoints" :key="String(p.id)">
                <td>{{ p['监测点位编号'] }}</td>
                <td>{{ p['功率密度'] }}</td>
                <td>{{ p['监测日期'] }}</td>
                <td>
                  {{ p['留档结论'] }}
                  <span class="muted">（{{ p['判定限值标准号'] }} ≤{{ p['判定限值'] }}）</span>
                </td>
                <td :class="p['现行限值结论'] === '不合格' ? 'error-text' : 'ok-text'">{{ p['现行限值结论'] }}</td>
              </tr>
              <tr v-if="!selectedPoints.length"><td colspan="5" class="empty-state">暂无监测点位</td></tr>
            </tbody>
          </table>

          <form class="inline-form" @submit.prevent="registerPoint">
            <h4>登记监测点位</h4>
            <input v-model="pointForm['监测点位编号']" placeholder="点位编号，如 P-0001-C" required />
            <input v-model="pointForm['功率密度']" placeholder="功率密度 W/m²" required />
            <input v-model="pointForm['监测日期']" placeholder="监测日期 YYYY-MM-DD" required />
            <button class="btn primary" type="submit">登记</button>
          </form>
          <p class="muted">提示：登记时功率密度超过当日现行限值的，结论一律为「不合格」，不提供人工改成合格的入口。</p>

          <h4>另一入口核验：站点台账合规栏与备案结论同源</h4>
          <button class="btn" type="button" @click="verifyCompliance">读取站点 {{ selected['站点编号'] }} 的备案结论</button>
          <pre v-if="complianceCheck" class="verify-box">{{ complianceCheck }}</pre>
        </template>
        <p v-else class="empty-state">从左侧选择一份备案查看档案明细</p>
      </div>
    </div>

    <!-- 限值换版 -->
    <section class="version-panel">
      <h3>限值版本管理</h3>
      <table class="data-table mini">
        <thead><tr><th>标准号</th><th>功率密度限值 W/m²</th><th>生效日期</th><th>版本说明</th><th>是否现行</th></tr></thead>
        <tbody>
          <tr v-for="v in versions" :key="String(v.id)">
            <td>{{ v['标准号'] }}</td><td>{{ v['功率密度限值'] }}</td><td>{{ v['生效日期'] }}</td>
            <td>{{ v['版本说明'] }}</td><td>{{ v.current ? '现行版' : '历史留档版' }}</td>
          </tr>
        </tbody>
      </table>
      <form class="inline-form" @submit.prevent="publishVersion">
        <input v-model="versionForm['标准号']" placeholder="新标准号，如 GB 8702-2026" required />
        <input v-model="versionForm['功率密度限值']" placeholder="功率密度限值 W/m²" required />
        <input v-model="versionForm['生效日期']" placeholder="生效日期 YYYY-MM-DD" required />
        <button class="btn primary" type="button" @click="publishVersion">发布新版并重算存量</button>
      </form>
      <p class="muted">换版后：存量站点点位按新版重算「现行限值结论」，已备案档案越线的会同步为不合格；每条监测记录的留档结论仍按监测当时那一版，不改写。</p>
    </section>

    <!-- 建档弹层 -->
    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <form class="modal-card" @submit.prevent="createFiling">
        <h3>登记基站电磁环境备案</h3>
        <input v-model="createForm['备案编号']" placeholder="备案编号，如 EMF-2026-0010" required />
        <input v-model="createForm['站点编号']" placeholder="站点编号（对应基站台账）" required />
        <input v-model="createForm['站点名称']" placeholder="站点名称" required />
        <div class="action-bar">
          <button class="btn primary" type="submit">建立档案</button>
          <button class="btn" type="button" @click="creating = false">取消</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()

type Material = { id: number; 材料名称: string; status: string; 提交时间: string | null }
type Point = Record<string, string | number | null>
type Filing = Record<string, any>

const statuses = ['待提交', '已受理', '已备案', '已失效']
const rows = ref<Filing[]>([])
const versions = ref<Filing[]>([])
const selected = ref<Filing | null>(null)
const selectedPoints = ref<Point[]>([])
const keyword = ref('')
const statusFilter = ref('')
const message = ref('')
const messageOk = ref(true)
const creating = ref(false)
const complianceCheck = ref('')

const createForm = reactive<Record<string, string>>({})
const pointForm = reactive<Record<string, string>>({})
const versionForm = reactive<Record<string, string>>({})

const currentLimit = computed(() => versions.value.find((v) => v.current) || versions.value[versions.value.length - 1])

const statusStats = computed(() =>
  statuses.map((label) => ({ label, value: rows.value.filter((r) => r.status === label).length })),
)

function flash(text: string, ok = true) {
  message.value = text
  messageOk.value = ok
}

async function callAction(path: string, values: Record<string, unknown> = {}) {
  const res = await request(path, {
    method: 'POST',
    body: JSON.stringify({ values: { ...values, role: session.role } }),
  })
  return res.json() as Promise<{ ok: boolean; message: string; entry?: any; missing_permission?: string | null }>
}

async function reload() {
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  const [filingsRes, versionsRes] = await Promise.all([
    request(`/api/emfiling/filings?${query.toString()}`),
    request('/api/emfiling/versions'),
  ])
  if (!filingsRes.ok || !versionsRes.ok) {
    flash('档案读取失败，请确认后端服务已启动', false)
    return
  }
  const filingPayload = await filingsRes.json()
  rows.value = filingPayload.items ?? []
  const versionPayload = await versionsRes.json()
  versions.value = versionPayload.items ?? []
  if (selected.value) {
    const keep = rows.value.find((r) => String(r.id) === String(selected.value!.id))
    if (keep) await selectFiling(keep)
    else selected.value = null
  }
}

async function selectFiling(row: Filing) {
  complianceCheck.value = ''
  const detailRes = await request(`/api/emfiling/filings/${row.id}`)
  selected.value = detailRes.ok ? await detailRes.json() : row
  const pointsRes = await request(`/api/emfiling/points?filing_id=${row.id}`)
  selectedPoints.value = pointsRes.ok ? (await pointsRes.json()).items ?? [] : []
}

function openCreate() {
  Object.keys(createForm).forEach((k) => delete createForm[k])
  creating.value = true
}

async function createFiling() {
  const r = await callAction('/api/emfiling/filings', { ...createForm })
  flash(r.message, r.ok)
  if (r.ok) {
    creating.value = false
    await reload()
    if (r.entry) await selectFiling(r.entry)
  }
}

async function submitFiling() {
  const r = await callAction(`/api/emfiling/filings/${selected.value!.id}/submit`)
  flash(r.message, r.ok)
  await reload()
}

async function returnFiling() {
  const reason = window.prompt('退回原因（会标在需要补正的材料备注上）', '材料需补正')
  if (reason === null) return
  const r = await callAction(`/api/emfiling/filings/${selected.value!.id}/return`, { 退回原因: reason })
  flash(r.message, r.ok)
  await reload()
}

async function supplement(name: string) {
  const r = await callAction(`/api/emfiling/filings/${selected.value!.id}/materials`, { 材料名称: name })
  flash(r.message, r.ok)
  await reload()
}

async function registerPoint() {
  const r = await callAction('/api/emfiling/points', { filing_id: selected.value!.id, ...pointForm })
  flash(r.message, r.ok)
  if (r.ok) {
    pointForm['监测点位编号'] = ''
    pointForm['功率密度'] = ''
    pointForm['监测日期'] = ''
  }
  await reload()
}

async function decide(conclusion: string) {
  const r = await callAction(`/api/emfiling/filings/${selected.value!.id}/decision`, { 备案结论: conclusion })
  if (!r.ok && r.missing_permission) {
    flash(`${r.message}（缺少授权项：${r.missing_permission}）`, false)
  } else {
    flash(r.message, r.ok)
  }
  await reload()
}

async function expireFiling() {
  const r = await callAction(`/api/emfiling/filings/${selected.value!.id}/expire`)
  flash(r.message, r.ok)
  await reload()
}

async function publishVersion() {
  const r = await callAction('/api/emfiling/versions', { ...versionForm })
  if (!r.ok && r.missing_permission) {
    flash(`${r.message}（缺少授权项：${r.missing_permission}）`, false)
  } else {
    flash(r.message, r.ok)
  }
  versionForm['标准号'] = ''
  versionForm['功率密度限值'] = ''
  versionForm['生效日期'] = ''
  await reload()
}

async function verifyCompliance() {
  // 另一个入口：直接按站点编号查，台账合规栏与这里取的是后端同一个函数的同一份结果。
  const res = await request(`/api/emfiling/site-compliance?site_no=${encodeURIComponent(selected.value!['站点编号'])}`)
  const data = await res.json()
  const siteRes = await request(`/api/site?keyword=${encodeURIComponent(selected.value!['站点编号'])}`)
  const siteRows = siteRes.ok ? (await siteRes.json()).items ?? [] : []
  const siteRow = siteRows.find((s: Filing) => s['基站编号'] === selected.value!['站点编号'])
  complianceCheck.value = JSON.stringify(
    {
      另一入口读到的: data,
      站点台账合规栏: siteRow ? { 备案合规栏: siteRow['备案合规栏'], 备案结论: siteRow['备案结论'] } : '台账无此站点',
      两端一致: siteRow ? siteRow['备案合规栏'] === data['合规栏'] && siteRow['备案结论'] === data['备案结论'] : null,
    },
    null,
    2,
  )
}

onMounted(reload)
</script>

<style scoped>
.em-grid {
  display: grid;
  grid-template-columns: minmax(420px, 1fr) minmax(480px, 1.1fr);
  gap: 16px;
  align-items: start;
}
.em-col {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
}
.detail-col .action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 8px 0;
}
tr.active td {
  background: #eff6ff;
}
.mini {
  font-size: 12px;
}
.mini th, .mini td {
  padding: 4px 8px;
}
.muted {
  color: #6b7280;
  font-size: 12px;
}
.ok-text {
  color: #15803d;
}
.notice.ok {
  color: #15803d;
}
.stat-sub {
  display: block;
  font-size: 12px;
  color: #6b7280;
}
.role-hint {
  font-size: 12px;
  color: #374151;
  background: #f9fafb;
  border-left: 3px solid #9ca3af;
  padding: 6px 8px;
}
.inline-form {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0;
}
.inline-form input {
  flex: 1 1 140px;
  min-width: 120px;
}
.btn.danger {
  color: #b91c1c;
  border-color: #fca5a5;
}
.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.verify-box {
  background: #0f172a;
  color: #d1fae5;
  padding: 10px;
  border-radius: 6px;
  font-size: 12px;
  overflow-x: auto;
}
.version-panel {
  margin-top: 18px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  width: 380px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.detail-meta {
  font-size: 13px;
  color: #374151;
}
</style>
