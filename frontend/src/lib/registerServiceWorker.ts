/// <reference types="vite-plugin-pwa/client" />
/**
 * Service-worker registration that actually ships updates.
 *
 * The plugin's injected `registerSW.js` only registers `/sw.js`: a new
 * deploy's worker then installs and takes control (`skipWaiting` +
 * `clientsClaim`), but the open page keeps running the old bundle until a full
 * reload. An installed iOS home-screen app almost never gets one, since
 * switching back to it resumes the same page, so it could show an old
 * frontend for days.
 *
 * `registerSW` from `virtual:pwa-register` (in `autoUpdate` mode) reloads the
 * page once a new worker activates, and checking for a new worker whenever the
 * app returns to the foreground means a resumed app picks up a deploy without
 * being relaunched.
 */
import { registerSW } from 'virtual:pwa-register'

/**
 * Asks the browser to look for a new service worker each time the page becomes
 * visible again (an app resumed from the background, a tab switched back to).
 *
 * @param registration - The active service-worker registration.
 * @param doc - The document to watch (injectable for tests).
 */
export function checkForUpdatesOnResume(
  registration: ServiceWorkerRegistration,
  doc: Document = document,
): void {
  doc.addEventListener('visibilitychange', () => {
    if (doc.visibilityState === 'visible') {
      // Offline or a failed fetch: the next resume tries again.
      void registration.update().catch(() => {})
    }
  })
}

/**
 * Registers the service worker; production builds only (the dev server has
 * none). The page reloads itself when a newly deployed worker takes over.
 */
export function registerServiceWorker(): void {
  if (!import.meta.env.PROD) {
    return
  }
  registerSW({
    immediate: true,
    onRegisteredSW(_swUrl, registration) {
      if (registration) {
        checkForUpdatesOnResume(registration)
      }
    },
  })
}
