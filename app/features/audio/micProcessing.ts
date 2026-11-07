/** Which browser voice processing the microphone gets on web (echo cancellation, noise suppression, gain control). */
import { Platform } from 'react-native';

/**
 * `raw`: all off, for his own speech in Talk and Teach. Browser noise suppression smears the consonant cues his
 * personal model relies on, and both must hear the same sound. `call`: all on, for a family member on the call page,
 * whose speakers play his voice back into their microphone.
 */
export type MicProcessing = 'raw' | 'call';

const flags: Record<MicProcessing, MediaTrackConstraints> = {
  raw: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
  call: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
};

/**
 * Runs `start` with the browser's microphone request rewritten to `processing`.
 * @siteed/audio-studio 3.2.1 always asks for all three on web and has no option to change it, so for the length of
 * one start its getUserMedia call is wrapped and the flags replaced. Native platforms are left untouched.
 */
export async function withMicProcessing<T>(processing: MicProcessing, start: () => Promise<T>): Promise<T> {
  const devices = Platform.OS === 'web' && typeof navigator !== 'undefined' ? navigator.mediaDevices : undefined;
  if (!devices?.getUserMedia) return start();
  const original = devices.getUserMedia;
  devices.getUserMedia = (constraints?: MediaStreamConstraints) => {
    const audio = constraints?.audio;
    const merged = audio ? { ...constraints, audio: { ...(typeof audio === 'object' ? audio : {}), ...flags[processing] } } : constraints;
    return original.call(devices, merged);
  };
  try {
    return await start();
  } finally {
    devices.getUserMedia = original;
  }
}
