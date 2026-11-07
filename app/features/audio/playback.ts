/** Plays his voice (spec 8.9): MP3 clips from the server through expo-audio, or the phone's voice when offline. */
import { createAudioPlayer, setAudioModeAsync, type AudioPlayer, type AudioStatus } from 'expo-audio';
import { File, Paths } from 'expo-file-system';
import * as Speech from 'expo-speech';
import { Platform } from 'react-native';

import { base64ToBytes } from './pcm';

// A clip that has not started after this long has failed.
const START_TIMEOUT_MS = 4_000;

let player: AudioPlayer | null = null;
let playerReady: Promise<AudioPlayer> | null = null;
let playing = false;
// Recent clip URLs on web; the oldest is released once a few newer ones exist, so Replay still works.
const webClipUrls: string[] = [];
let clipCounter = 0;
const listeners = new Set<(isPlaying: boolean) => void>();

/** True while a voice is playing; capture drops frames then (half duplex). */
export function isVoicePlaying(): boolean {
  return playing;
}

/** Subscribes to playing / stopped changes; returns the unsubscribe function. */
export function onVoicePlaying(listener: (isPlaying: boolean) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function setPlaying(next: boolean): void {
  if (next === playing) return;
  playing = next;
  listeners.forEach((listener) => listener(next));
}

/** Lets another player (the streamed voice) take part in half duplex: capture pauses while it plays. */
export const markVoicePlaying = setPlaying;

/** The one shared player, created once (concurrent callers share the same creation). */
function getPlayer(): Promise<AudioPlayer> {
  playerReady ??= (async () => {
    // Keep the session able to record, and route to the loudspeaker rather than the earpiece.
    await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true, shouldRouteThroughEarpiece: false, interruptionMode: 'duckOthers' }).catch(() => undefined);
    player = createAudioPlayer(null);
    player.addListener('playbackStatusUpdate', (status: AudioStatus) => {
      if (status.didJustFinish) setPlaying(false);
    });
    return player;
  })();
  return playerReady;
}

/** Creates the player ahead of the first tap, so a stored phrase starts in well under 0.3 s. */
export function prepareVoice(): void {
  void getPlayer();
}

/** A tenth of a second of silence as a WAV blob URL, used to unlock web audio inside a tap. */
function silentWavUrl(): string {
  const samples = 800;
  const view = new DataView(new ArrayBuffer(44 + samples * 2));
  const text = (offset: number, value: string) => [...value].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  text(0, 'RIFF');
  view.setUint32(4, 36 + samples * 2, true);
  text(8, 'WAVEfmt ');
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, 8000, true); // sample rate
  view.setUint32(28, 16000, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  text(36, 'data');
  view.setUint32(40, samples * 2, true);
  return URL.createObjectURL(new Blob([view.buffer], { type: 'audio/wav' }));
}

/** Browsers (iOS Safari above all) only play sound a tap started; call this inside the tap so later clips can play. */
export function unlockVoice(): void {
  if (Platform.OS !== 'web' || !player) return;
  player.replace({ uri: silentWavUrl() });
  player.play();
}

/** Turns a base64 MP3 into something the player can open: a blob URL on web, a cache file on the phone. */
export async function mp3Uri(base64: string): Promise<string> {
  if (Platform.OS === 'web') {
    const bytes = base64ToBytes(base64);
    const url = URL.createObjectURL(new Blob([bytes.buffer as ArrayBuffer], { type: 'audio/mpeg' }));
    webClipUrls.push(url);
    if (webClipUrls.length > 4) URL.revokeObjectURL(webClipUrls.shift()!);
    return url;
  }
  // Rotate between a few files so a replay never reads a file being rewritten.
  clipCounter = (clipCounter + 1) % 4;
  const file = new File(Paths.cache, `voice-${clipCounter}.mp3`);
  file.create({ overwrite: true });
  await file.write(base64, { encoding: 'base64' });
  return file.uri;
}

/** Plays an MP3 at `uri`; resolves when sound has started, rejects with a plain message if it cannot. */
export async function playUri(uri: string): Promise<void> {
  stopVoice();
  const audio = await getPlayer();
  audio.replace({ uri });
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      subscription.remove();
      reject(new Error("The voice didn't play. Tap Replay to try again."));
    }, START_TIMEOUT_MS);
    const subscription = audio.addListener('playbackStatusUpdate', (status: AudioStatus) => {
      if (!status.playing) return;
      clearTimeout(timer);
      subscription.remove();
      resolve();
    });
    setPlaying(true);
    audio.play();
  }).catch((error: Error) => {
    setPlaying(false);
    throw error;
  });
}

/** Speaks text with the phone's own voice (offline typing); resolves when it starts. */
export function speakWithPhoneVoice(text: string): Promise<void> {
  stopVoice();
  return new Promise((resolve) => {
    setPlaying(true);
    Speech.speak(text, {
      onStart: () => resolve(),
      onDone: () => setPlaying(false),
      onStopped: () => setPlaying(false),
      onError: () => {
        setPlaying(false);
        resolve();
      },
    });
    // Some browsers never fire onStart; treat the call itself as the start.
    if (Platform.OS === 'web') resolve();
  });
}

/** Stops whatever voice is playing. */
export function stopVoice(): void {
  player?.pause();
  void Speech.stop();
  setPlaying(false);
}
