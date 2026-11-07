/** Asks the server for his voice and waits for the `audio` message that answers. */
import type { SpeechSocket } from '@/features/connection/SpeechSocket';
import type { AudioMessage, ClientMessage } from '@/features/connection/protocol';

// ElevenLabs Flash answers in well under a second; past this the voice is not coming.
const AUDIO_TIMEOUT_MS = 12_000;

/** Sends `request` and resolves with the first `audio` message `matches` accepts; rejects on an error or timeout. */
export function requestAudio(socket: SpeechSocket, request: ClientMessage, matches: (audio: AudioMessage) => boolean): Promise<AudioMessage> {
  return new Promise((resolve, reject) => {
    const finish = (outcome: () => void) => {
      clearTimeout(timer);
      unsubscribe();
      outcome();
    };
    const timer = setTimeout(() => finish(() => reject(new Error("The voice didn't come through. Tap Replay to try again."))), AUDIO_TIMEOUT_MS);
    const unsubscribe = socket.onMessage((message) => {
      if (message.type === 'audio' && matches(message)) finish(() => resolve(message));
      if (message.type === 'error') finish(() => reject(new Error(message.message)));
    });
    if (!socket.send(request)) finish(() => reject(new Error('No connection to the speech server.')));
  });
}

/** One saved phrase in his voice (`say_phrase`). */
export function requestPhraseAudio(socket: SpeechSocket, phraseId: string): Promise<AudioMessage> {
  return requestAudio(socket, { type: 'say_phrase', phrase_id: phraseId }, (audio) => audio.phrase_id === phraseId);
}

/** A typed sentence in his voice (`type_and_speak`); its clip carries no phrase id. */
export function requestTypedAudio(socket: SpeechSocket, text: string): Promise<AudioMessage> {
  return requestAudio(socket, { type: 'type_and_speak', text }, (audio) => !audio.phrase_id);
}
