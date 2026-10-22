// Homelab fork: service-worker registration that reloads onto a new deploy.
import { afterEach, describe, expect, it, vi } from 'vitest'

import { checkForUpdatesOnResume, registerServiceWorker } from '@/lib/registerServiceWorker'

const registerSW = vi.hoisted(() => vi.fn())
vi.mock('virtual:pwa-register', () => ({ registerSW }))

afterEach(() => {
  vi.unstubAllEnvs()
  registerSW.mockReset()
})

function fakeRegistration() {
  return { update: vi.fn(() => Promise.resolve()) } as unknown as ServiceWorkerRegistration & {
    update: ReturnType<typeof vi.fn>
  }
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

describe('registerServiceWorker (homelab fork)', () => {
  it('registers immediately in a production build and watches for resumes', () => {
    vi.stubEnv('PROD', true)
    registerServiceWorker()
    expect(registerSW).toHaveBeenCalledOnce()
    const options = registerSW.mock.calls[0]?.[0]
    expect(options.immediate).toBe(true)

    const registration = fakeRegistration()
    options.onRegisteredSW('/sw.js', registration)
    setVisibility('visible')
    expect(registration.update).toHaveBeenCalledOnce()
  })

  it('does nothing on the dev server', () => {
    vi.stubEnv('PROD', false)
    registerServiceWorker()
    expect(registerSW).not.toHaveBeenCalled()
  })
})

describe('checkForUpdatesOnResume (homelab fork)', () => {
  it('checks for a new worker only when the page becomes visible', () => {
    const registration = fakeRegistration()
    checkForUpdatesOnResume(registration)
    setVisibility('hidden')
    expect(registration.update).not.toHaveBeenCalled()
    setVisibility('visible')
    expect(registration.update).toHaveBeenCalledOnce()
  })

  it('swallows a failed check (offline)', async () => {
    const registration = fakeRegistration()
    registration.update.mockReturnValueOnce(Promise.reject(new Error('offline')))
    checkForUpdatesOnResume(registration)
    setVisibility('visible')
    await Promise.resolve()
    expect(registration.update).toHaveBeenCalledOnce()
  })
})
