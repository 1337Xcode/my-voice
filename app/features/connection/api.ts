/** HTTP calls to the speech server's routes, with timeouts, retries and plain-language errors. */
import type { Settings } from '@/features/settings/SettingsProvider';

const TIMEOUT_MS = 15_000;
// 429 and 5xx are retried twice, after these pauses.
const RETRY_DELAYS_MS = [500, 1_500];

export class ApiError extends Error {}

type Body = 'json' | 'bytes';

/** Makes one request with the app token and a timeout; network failures become an ApiError. */
async function request(settings: Settings, path: string, init: RequestInit): Promise<Response> {
  const { serverUrl, token } = settings.dev;
  if (!serverUrl || !token) throw new ApiError('The server is not set. Add it in the developer panel.');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await fetch(`${serverUrl}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { Authorization: `Bearer ${token}`, ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
    });
  } catch {
    throw new ApiError('Could not reach the speech server. Check the connection and try again.');
  } finally {
    clearTimeout(timer);
  }
}

/** Calls one server route and returns its JSON body (or raw bytes for audio files). */
export async function api<T>(settings: Settings, path: string, init: RequestInit = {}, body: Body = 'json'): Promise<T> {
  let response = await request(settings, path, init);
  for (const delay of RETRY_DELAYS_MS) {
    if (response.status !== 429 && response.status < 500) break;
    await new Promise((resolve) => setTimeout(resolve, delay));
    response = await request(settings, path, init);
  }
  if (response.status === 401 || response.status === 403) throw new ApiError('The app token is wrong. Check the developer panel.');
  if (response.status === 404) throw new ApiError("The speech server can't do this yet. Try again after it is updated.");
  if (!response.ok) {
    const detail = ((await response.json().catch(() => null)) as { detail?: unknown } | null)?.detail;
    throw new ApiError(typeof detail === 'string' ? detail : `The server could not do that (status ${response.status}). Try again.`);
  }
  if (body === 'bytes') return (await response.arrayBuffer()) as T;
  return (await response.json()) as T;
}
