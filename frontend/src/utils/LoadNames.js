const CONCURRENCY = 2;
const RETRIES = 2;
const MAX_RETRY_DELAY = 5000;

function abortError() {
  return new DOMException('Loading canceled', 'AbortError');
}

function checkAbort(signal) {
  if (signal?.aborted) throw abortError();
}

function retryDelay(value) {
  if (typeof value !== 'string' || !value.trim()) return 1000;
  const delay = /^\d+$/.test(value.trim())
    ? Number(value) * 1000
    : Date.parse(value) - Date.now();
  return Number.isNaN(delay) ? 1000 : Math.min(MAX_RETRY_DELAY, Math.max(0, delay));
}

function waitForRetry(milliseconds, signal) {
  checkAbort(signal);
  return new Promise((resolve, reject) => {
    const cancel = () => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', cancel);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', cancel);
      resolve();
    }, milliseconds);
    signal?.addEventListener('abort', cancel, { once: true });
    if (signal?.aborted) cancel();
  });
}

/** Load registry roles without exceeding the hosted proxy's admission limit.
 * Successful entries survive individual failures and can be reused on retry.
 */
export async function loadNames(roles, {
  baseUrl = '/api',
  fetchImpl = globalThis.fetch,
  signal,
  existingNames = {},
  wait = waitForRetry,
} = {}) {
  checkAbort(signal);
  const namesCache = { ...existingNames };
  const pending = roles.filter(role => !Object.hasOwn(namesCache, role));
  const failed = new Set();
  let next = 0;

  async function worker() {
    while (next < pending.length) {
      checkAbort(signal);
      const role = pending[next++];
      try {
        for (let attempt = 0; attempt <= RETRIES; attempt += 1) {
          checkAbort(signal);
          const response = await fetchImpl(
            `${baseUrl.replace(/\/+$/, '')}/component/names?role=${encodeURIComponent(role)}`,
            { signal, credentials: 'same-origin' },
          );
          if (response.status === 503 && attempt < RETRIES) {
            await wait(retryDelay(response.headers?.get('Retry-After')), signal);
            continue;
          }
          if (!response.ok) throw new Error('Could not load available parts');
          const names = await response.json();
          if (!Array.isArray(names) || names.some(name => typeof name !== 'string')) {
            throw new Error('Could not load available parts');
          }
          checkAbort(signal);
          namesCache[role] = names;
          break;
        }
      } catch {
        checkAbort(signal);
        failed.add(role);
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, pending.length) }, worker));
  checkAbort(signal);
  return { namesCache, failedRoles: roles.filter(role => failed.has(role)) };
}
