/** A family member's side of an app-to-app call: their own socket to `/call/ws`, their microphone, his sentences and voice. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { z } from 'zod';

import { mp3Uri, playUri, stopVoice, unlockVoice } from '@/features/audio/playback';
import { useCapture } from '@/features/audio/useCapture';
import { playChunk, resumeStreamAudio } from '@/features/experiments/realtime/streamPlayer';
import { useSettings } from '@/features/settings/SettingsProvider';

const guestMessage = z.discriminatedUnion('type', [
  z.object({ type: z.literal('call_status'), call_id: z.string().nullable().optional(), state: z.enum(['dialling', 'ringing', 'connected', 'ended', 'failed']), detail: z.string().nullable().optional() }),
  z.object({ type: z.literal('peer_state'), state: z.enum(['listening', 'thinking', 'choosing', 'idle']) }),
  z.object({ type: z.literal('sentence'), text: z.string() }),
  z.object({ type: z.literal('audio'), format: z.string(), data: z.string() }),
  // Streamed voice (EXP R1): his sentence arrives in pieces while it is being made.
  z.object({ type: z.literal('audio_chunk'), sentence: z.number(), seq: z.number(), sample_rate: z.number(), data: z.string(), final: z.boolean() }),
  z.object({ type: z.literal('error'), message: z.string(), code: z.string().optional() }),
]);

export type GuestPhase = 'ready' | 'connecting' | 'dialling' | 'ringing' | 'connected' | 'ended' | 'failed';
export type PeerState = 'listening' | 'thinking' | 'choosing' | 'idle';

// The server closes with this code when the call code is unknown or expired.
const UNKNOWN_CODE_CLOSE = 4404;

export function useGuestCall(code: string) {
  const { settings } = useSettings();
  const capture = useCapture();
  const { start: startCapture, stop: stopCapture } = capture;
  const [phase, setPhase] = useState<GuestPhase>('ready');
  const [detail, setDetail] = useState<string | null>(null);
  const [peer, setPeer] = useState<PeerState>('idle');
  const [sentences, setSentences] = useState<string[]>([]);
  const [connectedAt, setConnectedAt] = useState<number | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const callId = useRef<string | null>(null);

  const finish = useCallback(
    (next: 'ended' | 'failed', reason: string | null) => {
      void stopCapture();
      stopVoice();
      ws.current?.close();
      ws.current = null;
      setPeer('idle');
      setPhase(next);
      setDetail(reason);
    },
    [stopCapture],
  );

  const receive = useCallback(
    (raw: unknown) => {
      if (typeof raw !== 'string') return;
      let json: unknown;
      try {
        json = JSON.parse(raw);
      } catch {
        return;
      }
      const parsed = guestMessage.safeParse(json);
      if (!parsed.success) return;
      const message = parsed.data;
      if (message.type === 'call_status') {
        if (message.call_id) callId.current = message.call_id;
        if (message.state === 'ended' || message.state === 'failed') return finish(message.state, message.detail ?? null);
        setPhase(message.state);
        if (message.state === 'connected') setConnectedAt((at) => at ?? Date.now());
      } else if (message.type === 'peer_state') setPeer(message.state);
      else if (message.type === 'sentence') {
        setPeer('idle');
        setSentences((previous) => [...previous, message.text]);
      }
      else if (message.type === 'audio') void mp3Uri(message.data).then(playUri).catch(() => undefined);
      else if (message.type === 'audio_chunk') playChunk(`sentence-${message.sentence}`, message.data, message.sample_rate, message.final);
      else if (message.type === 'error') setDetail(message.message);
    },
    [finish],
  );

  /** Starts the call. Must run inside the tap: it unlocks sound and asks for the microphone. */
  const call = useCallback(
    async (name: string) => {
      const serverUrl = settings.dev.serverUrl;
      if (!serverUrl) return finish('failed', 'This page has no server address.');
      unlockVoice();
      resumeStreamAudio();
      setPhase('connecting');
      setDetail(null);
      setSentences([]);
      setConnectedAt(null);
      const socket = new WebSocket(`${serverUrl.replace(/^http/, 'ws')}/call/ws?code=${encodeURIComponent(code)}`);
      socket.binaryType = 'arraybuffer';
      ws.current = socket;
      socket.onopen = () => socket.send(JSON.stringify({ type: 'join', name: name.trim() || undefined }));
      socket.onmessage = (event) => receive(event.data);
      socket.onclose = (event) => {
        if (ws.current !== socket) return;
        finish(event.code === UNKNOWN_CODE_CLOSE ? 'failed' : 'ended', event.code === UNKNOWN_CODE_CLOSE ? 'That call code is not in use. Check it and try again.' : null);
      };
      try {
        await startCapture((frame) => socket.readyState === WebSocket.OPEN && socket.send(frame), null, 'call');
      } catch (error) {
        finish('failed', (error as Error).message);
      }
    },
    [settings.dev.serverUrl, code, finish, receive, startCapture],
  );

  const hangUp = useCallback(() => {
    const socket = ws.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'hangup_call', call_id: callId.current }));
    finish('ended', null);
  }, [finish]);

  // Leaving the page ends the call.
  useEffect(() => () => ws.current?.close(), []);

  return { phase, detail, peer, sentences, connectedAt, levels: capture.levels, call, hangUp };
}
