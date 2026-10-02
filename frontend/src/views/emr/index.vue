<template>
  <section class="page" data-module="emr">
    <header class="page-head">
      <div>
        <h2>基站电磁环境备案档案</h2>
        <p class="page-desc">
          环评备案与辐射监测合成一份对得上的档案：监测点位按功率密度与监测日期登记，越线一律记不合格；
          备案文书沿 待提交 → 已受理 → 已备案 → 已失效 流转，退回只补缺失材料；
          限值换版后存量按新版重算现行符合性，留档锁定监测当时版本；备案结论是站点台账合规栏的唯一数据源。
        </p>
      </div>
    </header>

    <!-- 登录条：切换身份演示授权口径 -->
    <div class="login-bar">
      <template v-if="session.user">
        <span class="login-id">
          当前身份：<strong>{{ session.user.display_name }}</strong>（{{ session.user.role_label }}）
          <em v-if="!session.isEnvAdmin" class="perm-warn">· 无备案结论/审查/换版授权</em>
          <em v-else class="perm-ok">· 持环保归口全部授权</em>
        </span>
        <button class="btn ghost" type="button" @click="logout">退出登录</button>
      </template>
      <template v-else>
        <span class="login-id">未登录：只能查阅，写操作会被打回。可切换演示身份：</span>
        <button class="btn" type="button" @click="login('envadmin')">以环保归口管理员登录</button>
        <button class="btn" type="button" @click="login('ops')">以运维人员登录</button>
        <button class="btn" type="button" @click="login('viewer')">以只读访客登录</button>
      </template>
      <span v-if="authError" class="error-text">{{ authError }}</span>
    </div>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="item.cls">{{ item.value }}</strong>
      </article>
    </div>

    <div class="emr-layout">
      <!-- 左：备案文书列表 -->
      <div class="emr-col">
        <form class="filter-bar" @submit.prevent="reload">
          <label class="filter-item">
            <span>备案状态</span>
            <select v-model="statusFilter">
              <option value="">全部</option>
              <option v-for="s in statusOrder" :key="s" :value="s">{{ s }}</option>
            </select>
          </label>
          <input v-model="keyword" placeholder="按站点编号/名称/备案编号检索" />
          <button class="btn" type="submit">查询</button>
        </form>

        <table class="data-table">
          <thead>
            <tr>
              <th>备案编号</th><th>所属站点</th><th>文书状态</th>
              <th>现行符合性</th><th>备案结论</th><th>缺材料</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in filings"
              :key="String(row.id)"
              :class="{ 'row-active': selectedId === row.id }"
              style="cursor: pointer"
              @click="selectFiling(row.id)"
            >
              <td>{{ row.备案编号 }}</td>
              <td>{{ row.所属站点编号 }} {{ row.所属站点名称 }}</td>
              <td><span class="tag" :class="statusClass(row.status)">{{ row.status }}</span></td>
              <td><span class="tag" :class="verdictClass(row.现行符合性)">{{ row.现行符合性 }}</span></td>
              <td><span class="tag" :class="verdictClass(row.conclusion.备案结论)">{{ row.conclusion.备案结论 }}</span></td>
              <td>{{ row.缺失材料.length ? row.缺失材料.join('、') : '—' }}</td>
            </tr>
            <tr v-if="!filings.length">
              <td colspan="6" class="empty-state">暂无备案档案</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 右：档案详情 -->
      <div class="emr-col emr-detail" v-if="detail">
        <div class="detail-head">
          <h3>{{ detail.备案编号 }} · {{ detail.所属站点名称 }}</h3>
          <span class="tag" :class="statusClass(detail.status)">{{ detail.status }}</span>
        </div>
        <p v-if="detail.退回原因" class="return-reason">退回原因：{{ detail.退回原因 }}</p>

        <!-- 唯一结论 -->
        <div class="conclusion-box">
          <h4>备案结论（唯一事实源）</h4>
          <div class="conclusion-grid">
            <span>备案结论：<b :class="verdictClass(detail.conclusion.备案结论)">{{ detail.conclusion.备案结论 }}</b></span>
            <span>站点合规栏：<b :class="verdictClass(detail.conclusion.合规栏)">{{ detail.conclusion.合规栏 ?? detail.conclusion.备案结论 }}</b></span>
            <span>现行符合性：<b :class="verdictClass(detail.conclusion.现行符合性)">{{ detail.conclusion.现行符合性 }}</b>
              <em class="muted">（按 {{ detail.conclusion.现行依据版本 }} 重算）</em></span>
            <span>留档结论：<b :class="verdictClass(detail.conclusion.留档结论)">{{ detail.conclusion.留档结论 }}</b>
              <em class="muted">（锁定 {{ detail.conclusion.留档依据版本 }}）</em></span>
            <span v-if="detail.conclusion.更新时间">更新：{{ detail.conclusion.更新时间 }} · {{ detail.conclusion.更新人 }}</span>
            <span class="conclusion-note">{{ detail.conclusion.说明 }}</span>
          </div>
        </div>

        <!-- 材料清单 -->
        <div class="block">
          <h4>备案材料（退回只补待补交的几份）</h4>
          <ul class="material-list">
            <li v-for="mat in detail.材料" :key="mat.name">
              <span class="tag" :class="mat.state === '已提交' ? 'tag-pass' : 'tag-fail'">{{ mat.state }}</span>
              {{ mat.name }}
              <button
                v-if="mat.state !== '已提交'"
                class="link"
                type="button"
                @click="supplement(mat.name)"
              >补交这份</button>
            </li>
          </ul>
        </div>

        <!-- 监测点位 -->
        <div class="block">
          <h4>辐射监测点位（合格与否由服务端按监测当时限值裁定）</h4>
          <table class="data-table inner">
            <thead>
              <tr><th>点位</th><th>位置</th><th>天线轮次</th><th>功率密度 W/m²</th><th>监测日期</th><th>留档判定/版本</th><th>现行判定</th></tr>
            </thead>
            <tbody>
              <tr v-for="m in detail.监测点位" :key="m.监测点编号">
                <td>{{ m.监测点编号 }}</td>
                <td>{{ m.监测点位置 }}</td>
                <td>{{ m.天线轮次 }}</td>
                <td :class="Number(m.功率密度) > Number(detail.conclusion.限值) ? 'over-line' : ''">{{ m.功率密度 }}</td>
                <td>{{ m.监测日期 }}</td>
                <td><span class="tag" :class="verdictClass(m.监测结论)">{{ m.监测结论 }}</span> {{ m.依据版本 }}</td>
                <td><span class="tag" :class="verdictClass(m.现行判定)">{{ m.现行判定 }}</span></td>
              </tr>
            </tbody>
          </table>

          <details class="register-form">
            <summary>登记 / 复测一个监测点位</summary>
            <div class="form-grid">
              <input v-model="measureForm.监测点编号" placeholder="监测点编号（如 MP-03）" />
              <input v-model="measureForm.监测点位置" placeholder="监测点位置" />
              <input v-model="measureForm.天线轮次" placeholder="天线轮次（如 第3轮天线）" />
              <input v-model.number="measureForm.功率密度" placeholder="功率密度 W/m²（数字）" type="number" step="0.01" />
              <input v-model="measureForm.监测日期" placeholder="监测日期 YYYY-MM-DD" type="date" />
              <button class="btn primary" type="button" @click="registerMeasure">登记监测值</button>
            </div>
            <p class="muted">即使前端提交“合格”，功率密度越过监测当时限值的，服务端一律记为不合格。</p>
          </details>
        </div>

        <!-- 文书动作 -->
        <div class="block actions">
          <h4>文书流转</h4>
          <button v-if="detail.status === '待提交'" class="btn primary" type="button" @click="submitFiling">提交受理</button>
          <button v-if="detail.status === '已受理'" class="btn primary" type="button" @click="acceptFiling">受理通过·出具备案结论</button>
          <button v-if="detail.status === '已受理'" class="btn" type="button" @click="returnFiling">退回补正（监测报告）</button>
          <button v-if="detail.status === '已备案'" class="btn" type="button" @click="expireFiling">置为已失效</button>

          <details v-if="detail.status === '已备案'" class="amend-form">
            <summary>更正备案结论（仅环保归口管理员）</summary>
            <div class="form-grid">
              <select v-model="amendVerdict">
                <option value="合格">合格</option>
                <option value="不合格">不合格</option>
              </select>
              <input v-model="amendNote" placeholder="更正说明" />
              <button class="btn primary" type="button" @click="amendConclusion">提交更正</button>
            </div>
            <p class="muted">服务端会用最新监测数据复核：存在越线点位时，即使是管理员也无法改成合格。</p>
          </details>
        </div>

        <p v-if="actionMessage" class="error-text">{{ actionMessage }}</p>
      </div>
      <div v-else class="emr-col emr-detail placeholder-box">点击左侧档案查看详情</div>
    </div>

    <!-- 限值版本 + 同源校验 -->
    <div class="emr-bottom">
      <div class="block">
        <h4>限值版本（换版后存量站点按新版重算，留档不变）</h4>
        <table class="data-table inner">
          <thead><tr><th>版本编号</th><th>标准名称</th><th>功率密度限值 W/m²</th><th>生效日期</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="l in limits" :key="l.id">
              <td>{{ l.版本编号 }}</td><td>{{ l.标准名称 }}</td>
              <td>{{ l.功率密度限值 }}</td><td>{{ l.生效日期 }}</td>
              <td><span class="tag" :class="l.是否当前版本 ? 'tag-pass' : ''">{{ l.状态 }}</span></td>
            </tr>
          </tbody>
        </table>
        <details class="register-form">
          <summary>发布新版限值（仅环保归口管理员）</summary>
          <div class="form-grid">
            <input v-model="limitForm.版本编号" placeholder="版本编号（如 GB8702-2026）" />
            <input v-model="limitForm.标准名称" placeholder="标准名称" />
            <input v-model.number="limitForm.功率密度限值" type="number" step="0.01" placeholder="功率密度限值 W/m²" />
            <input v-model="limitForm.生效日期" type="date" />
            <button class="btn primary" type="button" @click="publishLimit">发布并重算存量</button>
          </div>
        </details>
      </div>

      <div class="block">
        <h4>跨入口同源校验（模拟站点台账/其他入口读取）</h4>
        <div class="form-grid">
          <input v-model="probeSite" placeholder="输入站点编号，如 SITE-0001" />
          <button class="btn" type="button" @click="probeConclusion">读取该站点备案结论</button>
        </div>
        <pre v-if="probeResult" class="probe-box">{{ probeResult }}</pre>
        <p class="muted">该入口 /api/emr/sites/编号/conclusion 与备案详情页取的是同一份 conclusion；刷新页面、退出再进来结果不变。</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { sendJson } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type MaterialItem = { name: string; state: string }

type Filing = {
  id: number
  备案编号: string
  所属站点编号: string
  所属站点名称: string
  status: string
  材料: MaterialItem[]
  缺失材料: string[]
  退回原因: string
  监测点位: Array<Record<string, string | number>>
  现行符合性: string
  现行依据版本: string
  conclusion: Record<string, string | number>
}

const ENDPOINT = '/api/emr'
const session = useSessionStore()
const statusOrder = ['待提交', '已受理', '已备案', '已失效']

const filings = ref<Filing[]>([])
const limits = ref<Array<Record<string, string | number>>>([])
const selectedId = ref<number | null>(null)
const detail = ref<Filing | null>(null)
const statusFilter = ref('')
const keyword = ref('')
const actionMessage = ref('')
const authError = ref('')
const probeSite = ref('SITE-0001')
const probeResult = ref('')

const measureForm = reactive({ 监测点编号: '', 监测点位置: '', 天线轮次: '', 功率密度: '' as number | '', 监测日期: '' })
const limitForm = reactive({ 版本编号: '', 标准名称: '', 功率密度限值: '' as number | '', 生效日期: '' })
const amendVerdict = ref('合格')
const amendNote = ref('')

const stats = computed(() => [
  { label: '档案总数', value: filings.value.length, cls: '' },
  { label: '待提交/补正', value: filings.value.filter((f) => f.status === '待提交').length, cls: 'stat-warn' },
  { label: '已备案', value: filings.value.filter((f) => f.status === '已备案').length, cls: 'stat-ok' },
  { label: '现行越线站点', value: filings.value.filter((f) => f.现行符合性 === '不合格').length, cls: 'stat-bad' },
])

function statusClass(status: string) {
  return { 待提交: 'tag-warn', 已受理: 'tag-info', 已备案: 'tag-pass', 已失效: 'tag-gray' }[status] ?? ''
}
function verdictClass(verdict: unknown) {
  if (verdict === '合格') return 'tag-pass'
  if (verdict === '不合格') return 'tag-fail'
  if (verdict === '已失效') return 'tag-gray'
  return 'tag-warn'
}

async function login(name: string) {
  authError.value = ''
  try {
    const payload = await sendJson<{ ok: boolean; message: string; token: string; user: Parameters<typeof session.setSession>[1] }>(
      '/api/auth/login',
      { method: 'POST', body: JSON.stringify({ login_name: name }) },
    )
    if (!payload.ok) {
      authError.value = payload.message
      return
    }
    session.setSession(payload.token, payload.user)
    await restoreSession()
  } catch (error) {
    authError.value = error instanceof Error ? error.message : '登录失败'
  }
}

async function restoreSession() {
  if (!session.token) return
  try {
    const payload = await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${session.token}` } }).then((r) => r.json())
    if (payload.ok) {
      session.user = payload.user
      session.operator = payload.user.display_name
    } else {
      session.clearSession()
    }
  } catch {
    // 后端不可用时保留本地态，读接口仍可演示
  }
}

function logout() {
  sendJson('/api/auth/logout', { method: 'POST' }).catch(() => undefined)
  session.clearSession()
}

async function reload() {
  actionMessage.value = ''
  try {
    const params = new URLSearchParams()
    if (statusFilter.value) params.set('status', statusFilter.value)
    if (keyword.value) params.set('keyword', keyword.value)
    const payload = await sendJson<{ items: Filing[] }>(`${ENDPOINT}/filings?${params.toString()}`)
    filings.value = (payload.items ?? []).map(normalizeFiling)
    if (selectedId.value) {
      const fresh = filings.value.find((f) => f.id === selectedId.value)
      if (fresh) detail.value = fresh
    }
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '备案列表读取失败'
  }
}

async function reloadLimits() {
  try {
    const payload = await sendJson<{ items: Array<Record<string, string | number>> }>(`${ENDPOINT}/limits`)
    limits.value = payload.items ?? []
  } catch {
    limits.value = []
  }
}

function normalizeFiling(row: Filing): Filing {
  // 后端材料是字典，前端转成有序数组，保证待补交项排在一起。
  const rawMaterials = row.材料 as unknown
  let materials: MaterialItem[]
  if (Array.isArray(rawMaterials)) {
    materials = rawMaterials as MaterialItem[]
  } else {
    materials = Object.entries(rawMaterials as Record<string, string>).map(([name, state]) => ({ name, state }))
  }
  return { ...row, 材料: materials }
}

async function selectFiling(id: number) {
  selectedId.value = id
  actionMessage.value = ''
  try {
    detail.value = normalizeFiling(await sendJson<Filing>(`${ENDPOINT}/filings/${id}`))
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '档案详情读取失败'
  }
}

async function act(path: string, body: Record<string, unknown> = {}) {
  actionMessage.value = ''
  try {
    const payload = await sendJson<{ ok: boolean; message: string; entry: Filing }>(path, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    if (!payload.ok) {
      actionMessage.value = payload.message
      return null
    }
    actionMessage.value = payload.message
    await reload()
    if (payload.entry) detail.value = normalizeFiling(payload.entry)
    return payload
  } catch (error) {
    // 401/403：把后端写明的授权缺口直接展示
    actionMessage.value = error instanceof Error ? error.message : '操作失败'
    return null
  }
}

function submitFiling() {
  if (!detail.value) return
  void act(`${ENDPOINT}/filings/${detail.value.id}/submit`)
}
function acceptFiling() {
  if (!detail.value) return
  void act(`${ENDPOINT}/filings/${detail.value.id}/accept`)
}
function expireFiling() {
  if (!detail.value) return
  void act(`${ENDPOINT}/filings/${detail.value.id}/expire`)
}
function returnFiling() {
  if (!detail.value) return
  void act(`${ENDPOINT}/filings/${detail.value.id}/return`, {
    reason: '电磁环境监测报告缺监测仪器检定信息，退回补正',
    missing_materials: ['电磁环境监测报告'],
  })
}
function supplement(name: string) {
  if (!detail.value) return
  void act(`${ENDPOINT}/filings/${detail.value.id}/supplement`, { materials: [name] })
}

async function registerMeasure() {
  if (!detail.value) return
  const payload = await act(`${ENDPOINT}/measures`, {
    values: { 所属站点编号: detail.value.所属站点编号, ...measureForm },
  })
  if (payload) {
    measureForm.监测点编号 = ''
    measureForm.监测点位置 = ''
    measureForm.功率密度 = ''
  }
}

async function publishLimit() {
  const payload = await act(`${ENDPOINT}/limits/publish`, { values: { ...limitForm } })
  if (payload) {
    await reloadLimits()
    limitForm.版本编号 = ''
    limitForm.标准名称 = ''
    limitForm.功率密度限值 = ''
  }
}

function amendConclusion() {
  if (!detail.value) return
  void act(`${ENDPOINT}/filings/${detail.value.id}/conclusion`, {
    values: { verdict: amendVerdict.value, note: amendNote.value },
  })
}

async function probeConclusion() {
  try {
    const payload = await sendJson<Record<string, unknown>>(`${ENDPOINT}/sites/${probeSite.value.trim()}/conclusion`)
    probeResult.value = JSON.stringify(payload, null, 2)
  } catch (error) {
    probeResult.value = error instanceof Error ? error.message : '读取失败'
  }
}

onMounted(async () => {
  await restoreSession()
  await Promise.all([reload(), reloadLimits()])
})
</script>

<style scoped>
.login-bar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding: 10px 12px; margin-bottom: 12px; border: 1px solid var(--border); border-radius: 6px; background: #f8fafc;
}
.login-id { font-size: 13px; color: #475569; }
.perm-warn { color: #b91c1c; font-style: normal; }
.perm-ok { color: #15803d; font-style: normal; }

.emr-layout { display: grid; grid-template-columns: minmax(360px, 1fr) minmax(420px, 1.1fr); gap: 14px; align-items: start; }
.emr-bottom { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
.emr-col { border: 1px solid var(--border); border-radius: 8px; padding: 10px; background: #fff; }
.emr-detail { position: sticky; top: 10px; max-height: 82vh; overflow: auto; }
.placeholder-box { display: flex; align-items: center; justify-content: center; color: #94a3b8; min-height: 200px; }
.row-active { outline: 2px solid var(--brand); outline-offset: -2px; }

.detail-head { display: flex; align-items: center; justify-content: space-between; }
.return-reason { color: #b91c1c; font-size: 13px; margin: 6px 0; }
.block { margin-top: 12px; }
.block h4 { margin: 0 0 6px; font-size: 14px; }
.muted { color: #94a3b8; font-size: 12px; font-style: normal; }
.over-line { color: #b91c1c; font-weight: 700; }

.tag { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; border: 1px solid var(--border); background: #f1f5f9; }
.tag-pass { background: #dcfce7; border-color: #86efac; color: #15803d; }
.tag-fail { background: #fee2e2; border-color: #fca5a5; color: #b91c1c; }
.tag-warn { background: #fef9c3; border-color: #fde047; color: #a16207; }
.tag-info { background: #dbeafe; border-color: #93c5fd; color: #1d4ed8; }
.tag-gray { background: #e2e8f0; color: #475569; }
.stat-ok { color: #15803d; }
.stat-bad { color: #b91c1c; }
.stat-warn { color: #a16207; }

.conclusion-box { border: 1px solid #c7d2fe; background: #eef2ff; border-radius: 8px; padding: 10px; }
.conclusion-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px; font-size: 13px; }
.conclusion-note { grid-column: 1 / -1; color: #475569; }
.material-list { list-style: none; padding: 0; margin: 0; font-size: 13px; display: grid; gap: 4px; }
.data-table.inner { font-size: 12px; }
.data-table.inner th, .data-table.inner td { padding: 5px 6px; }
.form-grid { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.form-grid input, .form-grid select { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; min-width: 150px; }
.register-form, .amend-form { margin-top: 8px; }
.actions .form-grid { margin-top: 6px; }
.probe-box { background: #0f172a; color: #d1fae5; padding: 8px; border-radius: 6px; font-size: 12px; overflow: auto; max-height: 260px; }
</style>
