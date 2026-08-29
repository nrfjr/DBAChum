import { defineStore } from 'pinia'

export type SshConnectionState = 'connected' | 'untrusted'

export interface SshConnectionTest {
  state: SshConnectionState
  checked_at: string
  target: string
  port: number
  username: string
  latency_ms: number | null
  fingerprint: string
  trusted_fingerprint: string | null
  message: string
}

export interface ServerMemorySnapshot {
  total_bytes: number | null
  used_bytes: number | null
  available_bytes: number | null
  used_percent: number | null
  swap_total_bytes: number | null
  swap_used_bytes: number | null
  swap_used_percent: number | null
}

export interface ServerFilesystemSnapshot {
  filesystem: string
  mount_point: string
  total_bytes: number
  used_bytes: number
  available_bytes: number
  used_percent: number
}

export interface ServerProcessSnapshot {
  pid: number
  user: string | null
  cpu_percent: number | null
  memory_percent: number | null
  elapsed: string | null
  command: string
}

export interface ServerServiceSnapshot {
  manager: string
  state: string
  failed_services: string[]
  note: string | null
}

export interface ServerHealthSnapshot {
  checked_at: string
  target: string
  port: number
  ssh_latency_ms: number | null
  remote_hostname: string | null
  os_name: string | null
  kernel_release: string | null
  uptime_seconds: number | null
  load_1: number | null
  load_5: number | null
  load_15: number | null
  cpu_used_percent: number | null
  cpu_measurement: string | null
  memory: ServerMemorySnapshot
  filesystems: ServerFilesystemSnapshot[]
  top_processes: ServerProcessSnapshot[]
  services: ServerServiceSnapshot
  warnings: string[]
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.error?.message ?? `Request failed with status ${response.status}`)
  }

  return response.json()
}

export const useServerMonitoringStore = defineStore('server-monitoring', {
  state: () => ({
    healthByServer: {} as Record<string, ServerHealthSnapshot>,
    sshTestByServer: {} as Record<string, SshConnectionTest>,
    healthLoadingByServer: {} as Record<string, boolean>,
    testLoadingByServer: {} as Record<string, boolean>,
    errorByServer: {} as Record<string, string | null>,
  }),

  actions: {
    async testSsh(serverId: string) {
      this.testLoadingByServer[serverId] = true
      this.errorByServer[serverId] = null
      try {
        const result = await apiRequest<SshConnectionTest>(`/servers/${serverId}/ssh/test`, {
          method: 'POST',
        })
        this.sshTestByServer[serverId] = result
        return result
      } catch (error) {
        this.errorByServer[serverId] = error instanceof Error ? error.message : 'Unable to test SSH connection.'
        throw error
      } finally {
        this.testLoadingByServer[serverId] = false
      }
    },

    async trustHostKey(serverId: string, fingerprint: string) {
      this.testLoadingByServer[serverId] = true
      this.errorByServer[serverId] = null
      try {
        const result = await apiRequest<SshConnectionTest>(`/servers/${serverId}/ssh/trust`, {
          method: 'POST',
          body: JSON.stringify({ fingerprint }),
        })
        this.sshTestByServer[serverId] = result
        return result
      } catch (error) {
        this.errorByServer[serverId] = error instanceof Error ? error.message : 'Unable to trust SSH host key.'
        throw error
      } finally {
        this.testLoadingByServer[serverId] = false
      }
    },

    async loadHealth(serverId: string) {
      this.healthLoadingByServer[serverId] = true
      this.errorByServer[serverId] = null
      try {
        const result = await apiRequest<ServerHealthSnapshot>(`/servers/${serverId}/health`)
        this.healthByServer[serverId] = result
        return result
      } catch (error) {
        this.errorByServer[serverId] = error instanceof Error ? error.message : 'Unable to load host metrics.'
        throw error
      } finally {
        this.healthLoadingByServer[serverId] = false
      }
    },

    clearError(serverId: string) {
      this.errorByServer[serverId] = null
    },
  },
})
