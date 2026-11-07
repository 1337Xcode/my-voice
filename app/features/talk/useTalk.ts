/** One talk turn, end to end, from the app's side. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { AccessibilityInfo } from 'react-native';

import { useCapture } from '@/features/audio/useCapture';
import { mp3Uri, onVoicePlaying, playUri, speakWithPhoneVoice, stopVoice } from '@/features/audio/playback';
import { requestTypedAudio } from '@/features/audio/serverVoice';
import { playChunk } from '@/features/experiments/realtime/streamPlayer';
import { useConnection } from '@/features/connection/ConnectionProvider';
import type { Candidate, ResultMessage, ServerMessage, SettingChange } from '@/features/connection/protocol';
import { usePhrases, type Phrase } from '@/features/phrases/PhrasesProvider';
import { useSettings } from '@/features/settings/SettingsProvider';
import { buzz } from './haptics';
import { appendTurn, loadTurns, type SpokenTurn } from './history';

/** Where the spoken sentence's sound stands. `remote` means it plays into a phone call, not here. */
export type VoiceState = 'confirm' | 'waiting' | 'playing' | 'done' | 'failed' | 'remote';

export type TalkState =
  | { kind: 'idle' }
  | { kind: 'listening'; turnId: string; partial: string }
  | { kind: 'thinking'; turnId: string; slow: boolean }
  | { kind: 'pick'; turnId: string; candidates: Candidate[]; rejected: boolean }
  | { kind: 'again'; turnId: string; guess: Candidate | null; afterReject?: boolean }
  | { kind: 'speaking'; turnId: string | null; text: string; voice: VoiceState; voiceError: string | null; others: Candidate[] }
  | { kind: 'proposal'; turnId: string; changes: SettingChange[]; heard: string | null }
  | { kind: 'ignored' }
  | { kind: 'error'; turnId: string | null; message: string };

export type TalkMode = 'talk' | 'call';

// "Taking a moment" appears after 3 s of thinking; past 25 s the turn has failed.
const SLOW_AFTER_MS = 3_000;
const GIVE_UP_AFTER_MS = 25_000;
// The turn audio for a spoken result should arrive within this long.
const VOICE_TIMEOUT_MS = 12_000;
// Brief notes ("Didn't catch any speech", "Learned") stay this long.
const NOTE_MS = 2_000;

/** A short unique id for a turn. */
function newTurnId(): string {
  return `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

/** The candidate the server chose, else its first. */
function chosenOf(result: ResultMessage): Candidate | null {
  return result.candidates.find((c) => c.id === result.chosen_id) ?? result.candidates[0] ?? null;
}

/** Drops candidates whose words repeat an earlier one (ignoring case and punctuation), so options always differ. */
function distinct(candidates: Candidate[]): Candidate[] {
  const seen = new Set<string>();
  return candidates.filter((c) => {
    const key = c.text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** The turn's timing marks, for `client_timing`: from the end of speech to text shown and to sound. */
type Timing = { turnId: string; endAt: number; textAt: number | null; sent: boolean };

export function useTalk(mode: TalkMode = 'talk') {
  const { socket, status } = useConnection();
  const { settings } = useSettings();
  const phrases = usePhrases();
  const capture = useCapture();
  const { start: startCapture, stop: stopCapture } = capture;
  const [state, setStateRaw] = useState<TalkState>({ kind: 'idle' });
  const [learned, setLearned] = useState(false);
  const [turns, setTurns] = useState<SpokenTurn[]>([]);
  const stateRef = useRef(state);
  const timing = useRef<Timing | null>(null);
  const lastClip = useRef<string | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const online = status === 'ready' && socket !== null;
  const turnsRef = useRef(turns);
  turnsRef.current = turns;

  const setState = useCallback((next: TalkState) => {
    stateRef.current = next;
    setStateRaw(next);
  }, []);

  const later = useCallback((ms: number, run: () => void) => {
    timers.current.push(setTimeout(run, ms));
  }, []);

  const clearTimers = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }, []);

  useEffect(() => {
    void loadTurns().then(setTurns);
    return clearTimers;
  }, [clearTimers]);

  const remember = useCallback((text: string, via: SpokenTurn['via'], id = newTurnId()) => {
    void appendTurn(turnsRef.current, { id, text, via, at: Date.now() }).then(setTurns);
  }, []);

  const fail = useCallback(
    (message: string, turnId: string | null = null) => {
      clearTimers();
      void stopCapture();
      buzz('error');
      setState({ kind: 'error', turnId, message });
    },
    [clearTimers, setState, stopCapture],
  );

  /** Reports the turn's latency once its sound has started. */
  const reportTiming = useCallback(
    (turnId: string | null) => {
      const t = timing.current;
      if (!t || t.sent || t.turnId !== turnId || !socket) return;
      t.sent = true;
      const now = Date.now();
      socket.send({ type: 'client_timing', turn_id: turnId, ms_end_to_text: (t.textAt ?? now) - t.endAt, ms_end_to_audio: now - t.endAt });
    },
    [socket],
  );

  /** Shows a sentence facing the listener and announces it to VoiceOver. */
  const showSentence = useCallback(
    (text: string, turnId: string | null, voice: VoiceState, others: Candidate[] = []) => {
      clearTimers();
      setState({ kind: 'speaking', turnId, text, voice, voiceError: null, others });
      AccessibilityInfo.announceForAccessibility(text);
      if (voice === 'waiting')
        later(VOICE_TIMEOUT_MS, () => {
          const s = stateRef.current;
          if (s.kind === 'speaking' && s.voice === 'waiting') setState({ ...s, voice: 'failed', voiceError: "The voice didn't come through. Tap Replay to try again." });
        });
    },
    [clearTimers, later, setState],
  );

  /** Plays a clip for the sentence on screen and keeps it for Replay. */
  const playClip = useCallback(
    async (uri: string, turnId: string | null) => {
      lastClip.current = uri;
      try {
        await playUri(uri);
        reportTiming(turnId);
        const s = stateRef.current;
        if (s.kind === 'speaking') setState({ ...s, voice: 'playing', voiceError: null });
      } catch (error) {
        const s = stateRef.current;
        if (s.kind === 'speaking') setState({ ...s, voice: 'failed', voiceError: (error as Error).message });
      }
    },
    [reportTiming, setState],
  );

  // When playback ends, the sentence stays on screen with its sound marked done.
  useEffect(
    () =>
      onVoicePlaying((isPlaying) => {
        const s = stateRef.current;
        if (!isPlaying && s.kind === 'speaking' && s.voice === 'playing') setState({ ...s, voice: 'done' });
      }),
    [setState],
  );

  const actOnResult = useCallback(
    (result: ResultMessage) => {
      clearTimers();
      void stopCapture();
      if (timing.current?.turnId === result.turn_id) timing.current.textAt = Date.now();
      buzz('result');
      const top = chosenOf(result);
      if (result.action === 'speak' && top) {
        const voice: VoiceState = mode === 'call' ? 'remote' : settings.beforeSpeaking === 'check' ? 'confirm' : 'waiting';
        showSentence(top.text, result.turn_id, voice, distinct([top, ...result.candidates]).slice(1));
        if (voice !== 'confirm') remember(top.text, 'speech', result.turn_id);
      } else if (result.action === 'pick' && result.candidates.length) {
        setState({ kind: 'pick', turnId: result.turn_id, candidates: distinct(result.candidates).slice(0, 3), rejected: false });
      } else {
        setState({ kind: 'again', turnId: result.turn_id, guess: top });
      }
    },
    [clearTimers, mode, remember, setState, settings.beforeSpeaking, showSentence, stopCapture],
  );

  /** Moves from Listening to Thinking: the microphone stops and the clock for this turn starts. */
  const toThinking = useCallback(
    (turnId: string) => {
      timing.current = { turnId, endAt: Date.now(), textAt: null, sent: false };
      setState({ kind: 'thinking', turnId, slow: false });
      later(SLOW_AFTER_MS, () => {
        const s = stateRef.current;
        if (s.kind === 'thinking' && s.turnId === turnId) setState({ ...s, slow: true });
      });
      later(GIVE_UP_AFTER_MS, () => {
        const s = stateRef.current;
        if (s.kind === 'thinking' && s.turnId === turnId) fail('That took too long. Say it again, or type it.', turnId);
      });
    },
    [fail, later, setState],
  );

  const onServerMessage = useCallback(
    (message: ServerMessage) => {
      const s = stateRef.current;
      const turnId = 'turnId' in s ? s.turnId : null;
      if (message.type === 'endpoint' && s.kind === 'listening' && message.turn_id === turnId) {
        void stopCapture();
        toThinking(message.turn_id);
      } else if (message.type === 'partial' && s.kind === 'listening' && message.turn_id === turnId) {
        setState({ ...s, partial: message.text });
      } else if (message.type === 'ignored' && message.turn_id === turnId) {
        clearTimers();
        void stopCapture();
        setState({ kind: 'ignored' });
        later(NOTE_MS, () => stateRef.current.kind === 'ignored' && setState({ kind: 'idle' }));
      } else if (message.type === 'settings_proposal' && message.turn_id === turnId && (s.kind === 'listening' || s.kind === 'thinking')) {
        clearTimers();
        void stopCapture();
        buzz('result');
        setState({ kind: 'proposal', turnId: message.turn_id, changes: message.changes, heard: message.heard ?? null });
      } else if (message.type === 'result' && message.turn_id === turnId && (s.kind === 'listening' || s.kind === 'thinking' || (s.kind === 'pick' && s.rejected) || s.kind === 'again')) {
        // After "That's wrong" the server may send a fresh set of options for the same turn.
        actOnResult(message);
      } else if (message.type === 'audio' && s.kind === 'speaking' && s.voice === 'waiting' && message.turn_id && message.turn_id === s.turnId) {
        void mp3Uri(message.data).then((uri) => playClip(uri, s.turnId));
      } else if (message.type === 'audio_chunk' && s.kind === 'speaking' && (s.voice === 'waiting' || s.voice === 'playing') && message.turn_id === s.turnId) {
        // Streamed voice (EXP R1, only when he switched it on): sound starts with the first chunk.
        playChunk(message.turn_id, message.data, message.sample_rate, message.final, () => {
          reportTiming(message.turn_id);
          const now = stateRef.current;
          if (now.kind === 'speaking' && now.turnId === message.turn_id) setState({ ...now, voice: 'playing', voiceError: null });
        });
      } else if (message.type === 'learned') {
        buzz('learned');
        setLearned(true);
        setTimeout(() => setLearned(false), NOTE_MS);
      } else if (message.type === 'error' && (s.kind === 'listening' || s.kind === 'thinking')) {
        fail(message.message, turnId);
      } else if (message.type === 'error' && s.kind === 'speaking' && s.voice === 'waiting') {
        setState({ ...s, voice: 'failed', voiceError: message.message });
      }
    },
    [actOnResult, clearTimers, fail, later, playClip, reportTiming, setState, stopCapture, toThinking],
  );

  useEffect(() => socket?.onMessage(onServerMessage), [socket, onServerMessage]);

  // A turn cut off by a lost connection says so and offers typing.
  useEffect(() => {
    const s = stateRef.current;
    if (status !== 'ready' && (s.kind === 'listening' || s.kind === 'thinking')) fail('Connection dropped. Say it again, or type it.', s.turnId);
  }, [status, fail]);

  /** Starts a turn; `tell` turns are a spoken settings request ("make the text bigger"). */
  const talk = useCallback(async (purpose: 'talk' | 'tell' = 'talk') => {
    if (!socket || !online) return;
    stopVoice();
    clearTimers();
    const turnId = newTurnId();
    socket.send({ type: 'start_turn', turn_id: turnId, mode: mode === 'call' ? 'call' : purpose });
    setState({ kind: 'listening', turnId, partial: '' });
    buzz('listen');
    try {
      await startCapture((frame) => socket.sendAudio(frame), settings.micDeviceId);
    } catch (error) {
      socket.send({ type: 'cancel_turn', turn_id: turnId });
      fail((error as Error).message);
    }
  }, [clearTimers, fail, mode, online, setState, settings.micDeviceId, socket, startCapture]);

  const done = useCallback(async () => {
    const s = stateRef.current;
    if (s.kind !== 'listening' || !socket) return;
    toThinking(s.turnId);
    // Stop first so the last partial frame goes out before end_turn.
    await stopCapture();
    socket.send({ type: 'end_turn', turn_id: s.turnId });
  }, [socket, startCapture, stopCapture, toThinking]);

  const cancel = useCallback(async () => {
    const s = stateRef.current;
    clearTimers();
    await stopCapture();
    if ('turnId' in s && s.turnId && (s.kind === 'listening' || s.kind === 'thinking')) socket?.send({ type: 'cancel_turn', turn_id: s.turnId });
    setState({ kind: 'idle' });
  }, [clearTimers, setState, socket, startCapture, stopCapture]);

  /** He tapped one of the options (or the greyed guess): speak it. */
  const choose = useCallback(
    (candidate: Candidate) => {
      const s = stateRef.current;
      if (!('turnId' in s) || !s.turnId || !socket) return;
      socket.send({ type: 'choose', turn_id: s.turnId, candidate_id: candidate.id, via: 'pick' });
      const others = s.kind === 'pick' ? s.candidates.filter((c) => c.id !== candidate.id) : [];
      showSentence(candidate.text, s.turnId, mode === 'call' ? 'remote' : 'waiting', others);
      remember(candidate.text, 'pick', s.turnId);
    },
    [mode, remember, showSentence, socket],
  );

  /** He typed a sentence: inside a turn it is his correction; otherwise a new sentence. Offline, the phone speaks it. */
  const type = useCallback(
    async (text: string) => {
      const s = stateRef.current;
      const turnId = 'turnId' in s ? s.turnId : null;
      if (online && socket && mode === 'call' && !(turnId && s.kind !== 'speaking')) {
        // On a call the server speaks into the call; nothing plays here.
        socket.send({ type: 'type_and_speak', text });
        showSentence(text, null, 'remote');
      } else if (online && socket && turnId && s.kind !== 'speaking') {
        socket.send({ type: 'choose', turn_id: turnId, text, via: 'typed' });
        showSentence(text, turnId, mode === 'call' ? 'remote' : 'waiting');
      } else if (online && socket) {
        showSentence(text, null, mode === 'call' ? 'remote' : 'waiting');
        await requestTypedAudio(socket, text)
          .then((audio) => mp3Uri(audio.data))
          .then((uri) => playClip(uri, null))
          .catch((error: Error) => {
            const now = stateRef.current;
            if (now.kind === 'speaking') setState({ ...now, voice: 'failed', voiceError: error.message });
          });
      } else {
        showSentence(text, null, 'playing');
        lastClip.current = null;
        await speakWithPhoneVoice(text);
      }
      remember(text, 'typed', turnId ?? undefined);
    },
    [mode, online, playClip, remember, setState, showSentence, socket],
  );

  /** "That's wrong": tell the server, then offer the other options. */
  const reject = useCallback(() => {
    const s = stateRef.current;
    if (s.kind !== 'speaking' || !s.turnId) return;
    stopVoice();
    socket?.send({ type: 'reject', turn_id: s.turnId });
    if (s.others.length) setState({ kind: 'pick', turnId: s.turnId, candidates: s.others.slice(0, 3), rejected: true });
    else setState({ kind: 'again', turnId: s.turnId, guess: null, afterReject: true });
  }, [setState, socket]);

  /** "Speak it" on a check-first sentence. */
  const confirm = useCallback(() => {
    const s = stateRef.current;
    if (s.kind !== 'speaking' || s.voice !== 'confirm' || !s.turnId || !socket) return;
    socket.send({ type: 'confirm', turn_id: s.turnId });
    showSentence(s.text, s.turnId, 'waiting', s.others);
    remember(s.text, 'speech', s.turnId);
  }, [remember, showSentence, socket]);

  /** Plays the sentence again: the kept clip, or asks the server again if the clip never came. */
  const replay = useCallback(async () => {
    const s = stateRef.current;
    if (s.kind !== 'speaking') return;
    if (lastClip.current && s.voice !== 'failed') return playClip(lastClip.current, null);
    if (online && socket) {
      setState({ ...s, voice: 'waiting', voiceError: null });
      return requestTypedAudio(socket, s.text)
        .then((audio) => mp3Uri(audio.data))
        .then((uri) => playClip(uri, null))
        .catch((error: Error) => setState({ ...s, voice: 'failed', voiceError: error.message }));
    }
    await speakWithPhoneVoice(s.text);
  }, [online, playClip, setState, socket]);

  /** One tap on a saved phrase: show it facing the listener and play it. */
  const sayPhrase = useCallback(
    async (phrase: Phrase) => {
      if (mode === 'call' && socket && online) {
        // The server plays it into the call.
        socket.send(phrase.pinned && phrase.id.startsWith('local-') ? { type: 'type_and_speak', text: phrase.text } : { type: 'say_phrase', phrase_id: phrase.id });
        showSentence(phrase.text, null, 'remote');
        remember(phrase.text, 'phrase');
        return;
      }
      lastClip.current = null;
      showSentence(phrase.text, null, mode === 'call' ? 'remote' : 'waiting');
      remember(phrase.text, 'phrase');
      try {
        lastClip.current = await phrases.say(phrase);
        const s = stateRef.current;
        if (s.kind === 'speaking' && s.text === phrase.text && s.voice !== 'remote') setState({ ...s, voice: 'playing' });
      } catch (error) {
        const s = stateRef.current;
        if (s.kind === 'speaking') setState({ ...s, voice: 'failed', voiceError: (error as Error).message });
      }
    },
    [mode, online, phrases, remember, setState, showSentence, socket],
  );

  const dismiss = useCallback(() => {
    stopVoice();
    clearTimers();
    setState({ kind: 'idle' });
  }, [clearTimers, setState]);

  return { state, learned, turns, online, status, levels: capture.levels, noisy: capture.noisy, talk, done, cancel, choose, type, reject, confirm, replay, sayPhrase, dismiss };
}

export type Talk = ReturnType<typeof useTalk>;
