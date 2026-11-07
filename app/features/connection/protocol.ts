/** Message types exchanged with the speech server over /ws (spec section 12.1). */

export type Features = { calls: boolean; toolkit: boolean; partials: boolean };

export type ReadyMessage = {
  type: 'ready';
  speaker: string;
  model_version: string;
  voice_id: string;
  features: Features;
};

export type ErrorMessage = { type: 'error'; code: string; message: string };

/** Any message the server sends; each has a string `type`. */
export type ServerMessage = ReadyMessage | ErrorMessage | ({ type: string } & Record<string, unknown>);

/** Any JSON message the app sends. */
export type ClientMessage = { type: string } & Record<string, unknown>;

/** True when a parsed value looks like a server message. */
export function isServerMessage(value: unknown): value is ServerMessage {
  return typeof value === 'object' && value !== null && typeof (value as { type?: unknown }).type === 'string';
}
