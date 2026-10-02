import { defineStore } from 'pinia'

export const ROLES = ['值班管理员', '运维人员', '环保归口管理员'] as const
export type Role = (typeof ROLES)[number]
const ENV_ADMIN: Role = '环保归口管理员'
const ROLE_KEY = 'em-platform-role'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '通信基站运维管理平台',
    // 角色持久化：退出再进来、页面刷新，看到的都是同一份身份与同一份备案结论。
    role: (localStorage.getItem(ROLE_KEY) as Role) || '值班管理员',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    isEnvAdmin: (state) => state.role === ENV_ADMIN,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setRole(role: Role) {
      this.role = role
      this.operator = role
      localStorage.setItem(ROLE_KEY, role)
    },
  },
})
