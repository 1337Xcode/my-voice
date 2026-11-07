/** His experiment choices (EXP-SPEC), stored apart from the core settings and all off by default. */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSyncExternalStore } from 'react';

export type ExperimentChoices = {
  /** R1: voice plays as it is generated instead of after the whole clip. */
  streamedVoice: boolean;
  /** Section 8: "Use my camera for lip reading". */
  lipsCamera: boolean;
  /** Section 8: "Keep my lip video for learning" (mouth crops only). */
  keepLipVideo: boolean;
  /** Section 5.3: on the lips screen, turns start and end by themselves. */
  lipsHandsFree: boolean;
};

const STORAGE_KEY = 'experiments.v1';
const defaults: ExperimentChoices = { streamedVoice: false, lipsCamera: false, keepLipVideo: false, lipsHandsFree: false };

let choices: ExperimentChoices = defaults;
let loaded = false;
const listeners = new Set<() => void>();

void AsyncStorage.getItem(STORAGE_KEY)
  .then((raw) => {
    if (raw) choices = { ...defaults, ...(JSON.parse(raw) as Partial<ExperimentChoices>) };
  })
  .catch(() => undefined)
  .finally(() => {
    loaded = true;
    listeners.forEach((listener) => listener());
  });

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The current choices (defaults until storage has been read). */
export function experimentChoices(): ExperimentChoices {
  return choices;
}

/** True once the stored choices have been read. */
export function experimentsLoaded(): boolean {
  return loaded;
}

/** Changes some choices and saves them. */
export function updateExperiments(change: Partial<ExperimentChoices>): void {
  choices = { ...choices, ...change };
  AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(choices)).catch(() => undefined);
  listeners.forEach((listener) => listener());
}

/** The choices, re-rendering when they change. */
export function useExperimentChoices(): ExperimentChoices {
  return useSyncExternalStore(subscribe, experimentChoices, experimentChoices);
}
