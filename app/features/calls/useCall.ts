/** A call he is in: follows its status, collects the other person's captions, hangs up. */
import { useCallback, useEffect, useState } from 'react';

import { api } from '@/features/connection/api';
import { useConnection } from '@/features/connection/ConnectionProvider';
import type { CallState } from '@/features/connection/protocol';
import { useSettings } from '@/features/settings/SettingsProvider';

/** `connecting` until the server's first status arrives. */
export type CallPhase = 'connecting' | CallState;

/** An app-to-app call (a guest on the call link) or a phone call through the server. */
export type CallKind = 'app' | 'phone';

export type CaptionLine = { id: string; who: 'them' | 'me'; text: string };

export function useCall(callId: string, kind: CallKind) {
  const { settings } = useSettings();
  const { socket } = useConnection();
  const [phase, setPhase] = useState<CallPhase>(kind === 'phone' ? 'dialling' : 'connecting');
  const [detail, setDetail] = useState<string | null>(null);
  const [connectedAt, setConnectedAt] = useState<number | null>(null);
  const [lines, setLines] = useState<CaptionLine[]>([]);

  const addLine = useCallback((who: CaptionLine['who'], text: string) => {
    setLines((previous) => [...previous, { id: `${Date.now()}-${previous.length}`, who, text }]);
  }, []);

  useEffect(
    () =>
      socket?.onMessage((message) => {
        if (message.type === 'call_status' && message.call_id === callId) {
          setPhase(message.state);
          setDetail(message.detail ?? null);
          if (message.state === 'connected') setConnectedAt((at) => at ?? Date.now());
        }
        if (message.type === 'partner_caption' && message.source !== 'room') addLine('them', message.text);
      }),
    [socket, callId, addLine],
  );

  const hangUp = useCallback(async () => {
    setPhase('ended');
    if (kind === 'app') {
      socket?.send({ type: 'hangup_call', call_id: callId });
      return;
    }
    await api(settings, `/calls/${encodeURIComponent(callId)}/hangup?speaker=${settings.dev.speaker}`, { method: 'POST' }).catch((e: Error) => setDetail(e.message));
  }, [kind, socket, callId, settings]);

  return { phase, detail, connectedAt, lines, addLine, hangUp };
}
