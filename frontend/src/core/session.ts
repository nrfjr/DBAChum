export const SESSION_EXPIRED_MESSAGE = 'Session expired. Please log in again.'
export const SESSION_EXPIRED_EVENT = 'dbachum:session-expired'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
const nativeFetch = window.fetch.bind(window)
let interceptorInstalled = false
let activityTrackingEnabled = false
let lastActivityPingAt = 0
let lastExpiredEventAt = 0

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.toString()
  return input.url
}

function isApiRequest(url: string): boolean {
  if (!API_BASE_URL) return url.includes('/api/')
  return url.startsWith(API_BASE_URL) || url.includes(`${API_BASE_URL}/`)
}

function isAuthProbe(url: string): boolean {
  return url.includes('/auth/login')
    || url.includes('/auth/me')
    || url.includes('/auth/logout')
}

function announceSessionExpired() {
  const now = Date.now()
  if (now - lastExpiredEventAt < 1500) return
  lastExpiredEventAt = now
  window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT))
}

export function installSessionFetchInterceptor() {
  if (interceptorInstalled) return
  interceptorInstalled = true

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const authenticatedAtStart = activityTrackingEnabled
    const response = await nativeFetch(input, init)
    const url = requestUrl(input)
    if (
      authenticatedAtStart
      && response.status === 401
      && isApiRequest(url)
      && !isAuthProbe(url)
    ) {
      announceSessionExpired()
    }
    return response
  }
}

async function pingActivity() {
  if (!activityTrackingEnabled) return
  const now = Date.now()
  if (now - lastActivityPingAt < 60_000) return
  lastActivityPingAt = now

  try {
    await window.fetch(`${API_BASE_URL}/auth/activity`, {
      method: 'POST',
      credentials: 'include',
    })
  } catch {
    // Ordinary connectivity failures do not imply that the session expired.
  }
}

function onUserActivity() {
  void pingActivity()
}

export function setSessionActivityTracking(enabled: boolean) {
  if (activityTrackingEnabled === enabled) return
  activityTrackingEnabled = enabled
  if (enabled) {
    lastActivityPingAt = Date.now()
    window.addEventListener('pointerdown', onUserActivity, { passive: true })
    window.addEventListener('keydown', onUserActivity, { passive: true })
    window.addEventListener('input', onUserActivity, { passive: true })
    window.addEventListener('scroll', onUserActivity, { passive: true, capture: true })
    window.addEventListener('touchstart', onUserActivity, { passive: true })
  } else {
    window.removeEventListener('pointerdown', onUserActivity)
    window.removeEventListener('keydown', onUserActivity)
    window.removeEventListener('input', onUserActivity)
    window.removeEventListener('scroll', onUserActivity, true)
    window.removeEventListener('touchstart', onUserActivity)
  }
}
