/** HTTP calls to the speech server's routes, with plain-language errors (spec 12.2). */
import type { Settings } from '@/features/settings/SettingsProvider';

const TIMEOUT_MS = 15_000;

export class ApiError extends Error {}

/** Calls one server route with the app token and returns its JSON body. */
export async function api<T>(settings: Settings, path: string, init: RequestInit = {}): Promise<T> {
  const { serverUrl, token } = settings.dev;
  if (!serverUrl || !token) throw new ApiError('The server is not set. Add it in the developer panel.');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${serverUrl}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { Authorization: `Bearer ${token}`, ...(init.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
    });
  } catch {
    throw new ApiError('Could not reach the speech server. Check the connection and try again.');
  } finally {
    clearTimeout(timer);
  }
  if (response.status === 401) throw new ApiError('The app token is wrong. Check the developer panel.');
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(body?.detail ?? `The server could not do that (status ${response.status}). Try again.`);
  }
  return (await response.json()) as T;
}
