/** His phrases' voice clips kept on the device, so one tap plays in under 0.3 s, offline too. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Directory, File, Paths } from 'expo-file-system';
import { Platform } from 'react-native';

import { api } from '@/features/connection/api';
import type { Settings } from '@/features/settings/SettingsProvider';

const INDEX_KEY = 'phraseAudio.v1';
// Browser Cache Storage bucket that holds the clips on web.
const WEB_CACHE = 'phrase-audio-v1';
/** The format the app plays. */
export const APP_FORMAT = 'mp3_44100_128';

/** File names already on the device. */
let stored: Set<string> | null = null;
/** Ready-to-play URIs, so a tap does no I/O. */
const playable = new Map<string, string>();

async function index(): Promise<Set<string>> {
  if (stored) return stored;
  const raw = await AsyncStorage.getItem(INDEX_KEY).catch(() => null);
  stored = new Set(raw ? (JSON.parse(raw) as string[]) : []);
  return stored;
}

async function remember(fileName: string): Promise<void> {
  const files = await index();
  files.add(fileName);
  await AsyncStorage.setItem(INDEX_KEY, JSON.stringify([...files]));
}

/** Where a clip lives on the phone; the server's relative path is flattened into one file name. */
function phoneFile(fileName: string): File {
  return new File(Paths.document, 'phrases', fileName.replace(/[\/]/g, '_'));
}

/** The URI to play a stored clip from, or null when it is not on the device. */
export async function storedClipUri(fileName: string): Promise<string | null> {
  const ready = playable.get(fileName);
  if (ready) return ready;
  if (!(await index()).has(fileName)) return null;
  let uri: string | null = null;
  if (Platform.OS === 'web') {
    const response = await (await caches.open(WEB_CACHE)).match(fileName);
    if (response) uri = URL.createObjectURL(await response.blob());
  } else {
    const file = phoneFile(fileName);
    if (file.exists) uri = file.uri;
  }
  if (uri) playable.set(fileName, uri);
  return uri;
}

/** Downloads one clip from `GET /tts/{file}` and keeps it. */
async function download(settings: Settings, fileName: string): Promise<void> {
  const path = fileName.split('/').map(encodeURIComponent).join('/');
  const bytes = await api<ArrayBuffer>(settings, `/tts/${path}?speaker=${settings.dev.speaker}`, {}, 'bytes');
  if (Platform.OS === 'web') {
    const cache = await caches.open(WEB_CACHE);
    await cache.put(fileName, new Response(bytes, { headers: { 'Content-Type': 'audio/mpeg' } }));
  } else {
    new Directory(Paths.document, 'phrases').create({ intermediates: true, idempotent: true });
    const file = phoneFile(fileName);
    file.create({ overwrite: true });
    await file.write(new Uint8Array(bytes));
  }
  await remember(fileName);
}

/** Fetches every clip not yet on the device, one at a time; returns how many failed. */
export async function downloadMissing(settings: Settings, fileNames: string[]): Promise<number> {
  const have = await index();
  let failed = 0;
  for (const fileName of fileNames) {
    if (have.has(fileName)) continue;
    await download(settings, fileName).catch(() => {
      failed += 1;
    });
  }
  return failed;
}
