/** The last 50 things he said, kept on the phone for the conversation strip. */
import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'turns.v1';
const KEEP = 50;

export type SpokenTurn = {
  id: string;
  text: string;
  /** How the sentence was produced. */
  via: 'speech' | 'pick' | 'typed' | 'phrase';
  /** Milliseconds since the epoch. */
  at: number;
};

/** Reads the stored turns, newest last. */
export async function loadTurns(): Promise<SpokenTurn[]> {
  const raw = await AsyncStorage.getItem(KEY).catch(() => null);
  return raw ? (JSON.parse(raw) as SpokenTurn[]) : [];
}

/** Appends a turn and returns the kept list, newest last. */
export async function appendTurn(turns: SpokenTurn[], turn: SpokenTurn): Promise<SpokenTurn[]> {
  const next = [...turns.filter((t) => t.id !== turn.id), turn].slice(-KEEP);
  await AsyncStorage.setItem(KEY, JSON.stringify(next)).catch(() => undefined);
  return next;
}
