import { defineStore } from 'pinia'

export type SessionUser = {
  login_name: string
  display_name: string
  role: string
  role_label: string
  permissions: string[]
}

const TOKEN_KEY = 'emr-session-token'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '未登录',
    shiftLabel: '白班 08:00-20:00',
    scope: '通信基站运维管理平台',
    token: localStorage.getItem(TOKEN_KEY) ?? '',
    user: null as SessionUser | null,
  }),
  getters: {
    canOperate: (state) => state.user !== null,
    isEnvAdmin: (state) => state.user?.role === 'env_admin',
  },
  actions: {
    setSession(token: string, user: SessionUser) {
      this.token = token
      this.user = user
      this.operator = user.display_name
      // 登录态落地：页面刷新、退出页面再进来，读到的都是同一个身份与同一条备案结论。
      localStorage.setItem(TOKEN_KEY, token)
    },
    clearSession() {
      this.token = ''
      this.user = null
      this.operator = '未登录'
      localStorage.removeItem(TOKEN_KEY)
    },
    hasPerm(permission: string): boolean {
      return this.user?.permissions.includes(permission) ?? false
    },
  },
})
