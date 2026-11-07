/** The toolkit's HTTP service (API-NOTES §5): Librarian calls and the profile event stream. */
import { fetch as expoFetch } from 'expo/fetch';
import { Platform } from 'react-native';

const URL_BASE = (process.env.EXPO_PUBLIC_TOOLKIT_URL ?? '').replace(/\/$/, '');
const TOKEN = process.env.EXPO_PUBLIC_TOOLKIT_TOKEN ?? '';
const TIMEOUT_MS = 10_000;
// 429 and 5xx are retried twice, after these pauses.
const RETRY_DELAYS_MS = [500, 1_500];

/** True when the toolkit is set up; with no URL every toolkit feature stays hidden. */
export const toolkitConfigured = URL_BASE.length > 0;

async function post(method: string, args: unknown[]): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await fetch(`${URL_BASE}/v1/librarian/${method}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ args }),
      signal: controller.signal,
    });
  } catch {
    throw new Error('Could not reach the accessibility profile.');
  } finally {
    clearTimeout(timer);
  }
}

/** Calls one Librarian method with positional `args`; resolves with its `result`. */
export async function librarian<T>(method: string, args: unknown[] = []): Promise<T> {
  if (!TOKEN) throw new Error('EXPO_PUBLIC_TOOLKIT_TOKEN is not set, so the accessibility profile cannot be read.');
  let response = await post(method, args);
  for (const delay of RETRY_DELAYS_MS) {
    if (response.status !== 429 && response.status < 500) break;
    await new Promise((resolve) => setTimeout(resolve, delay));
    response = await post(method, args);
  }
  if (response.status === 401 || response.status === 403) throw new Error('The accessibility profile token is wrong (EXPO_PUBLIC_TOOLKIT_TOKEN).');
  const body = (await response.json().catch(() => null)) as { ok?: boolean; result?: T; error?: unknown } | null;
  if (!response.ok || !body?.ok) throw new Error(`The accessibility profile refused ${method}: ${String(body?.error ?? response.status)}.`);
  return body.result as T;
}

/**
 * Calls `onProfile` for every `profile` event on `GET /v1/profile/events` (the first arrives on connect).
 * The stream is read with fetch because EventSource cannot send the bearer token; it reconnects after drops.
 * Returns a function that stops listening.
 */
export function watchProfile(onProfile: () => void, onError: (message: string) => void): () => void {
  let stopped = false;
  let controller: AbortController | null = null;
  const send = (Platform.OS === 'web' ? fetch : expoFetch) as typeof fetch;

  const listen = async () => {
    while (!stopped) {
      controller = new AbortController();
      try {
        const response = await send(`${URL_BASE}/v1/profile/events`, { headers: { Authorization: `Bearer ${TOKEN}`, Accept: 'text/event-stream' }, signal: controller.signal });
        if (!response.ok || !response.body) throw new Error(`status ${response.status}`);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          // Events end with a blank line; a `profile` event means the profile changed.
          const events = buffer.split('\n\n');
          buffer = events.pop() ?? '';
          if (events.some((event) => /^event: profile$/m.test(event))) onProfile();
        }
      } catch (error) {
        if (stopped) return;
        onError(`Live profile updates paused (${(error as Error).message}); retrying.`);
      }
      // The server asks clients to wait 3 s before reconnecting.
      await new Promise((resolve) => setTimeout(resolve, 3_000));
    }
  };

  void listen();
  return () => {
    stopped = true;
    controller?.abort();
  };
}
