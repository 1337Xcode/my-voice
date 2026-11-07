// Tests for the toolkit key mapping. Run from app/: node --test features/toolkit/profileMapping.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { choicesFromPrefs, clampSpeechRate, percentFromTextSize, prefsFromToolkit, scopedWrites, sharedWrites, textSizeFromPercent } from './profileMapping.ts';

test('font scale percent maps to the nearest app text size', () => {
  assert.equal(textSizeFromPercent(100), 'large');
  assert.equal(textSizeFromPercent(109), 'large');
  assert.equal(textSizeFromPercent(110), 'xl');
  assert.equal(textSizeFromPercent(125), 'xl');
  assert.equal(textSizeFromPercent(150), 'huge');
  assert.equal(textSizeFromPercent(200), 'huge');
  assert.equal(percentFromTextSize('xl'), 120);
});

test('speech rate is limited to what the voice supports', () => {
  assert.equal(clampSpeechRate(0.5), 0.7);
  assert.equal(clampSpeechRate(2), 1.2);
  assert.equal(clampSpeechRate(0.93), 0.95);
});

test('needs alone (the skill example profile) give text size, contrast, motion, rate, captions and targets', () => {
  const profile = {
    supportAreas: ['vision'],
    fields: {
      needs: [
        { dimension: 'textSize', value: 1.5, strength: 'preference' },
        { dimension: 'contrast', value: 'yellow-black', strength: 'preference' },
        { dimension: 'reduceMotion', value: true, strength: 'floor' },
        { dimension: 'readAloudRate', value: 0.8, strength: 'hint' },
        { dimension: 'captions', value: true, strength: 'preference' },
      ],
      largeTargets: true,
    },
  };
  assert.deepEqual(prefsFromToolkit(profile, null), { textSize: 'huge', highContrast: true, reduceMotion: true, speechRate: 0.8, largeTargets: true, captions: true });
});

test('effective settings win over the needs they derive from', () => {
  const profile = { fields: { needs: [{ dimension: 'textSize', value: 1.5 }, { dimension: 'contrast', value: true }] } };
  const effective = { settings: { fontScale: 120, contrastMode: 'none', motionReducer: false, speechRate: 1.1, bigTargets: false, showCaptions: false } };
  assert.deepEqual(prefsFromToolkit(profile, effective), { textSize: 'xl', highContrast: false, reduceMotion: false, speechRate: 1.1, largeTargets: false, captions: false });
});

test('the app scope gives check-first and the voice', () => {
  const effective = { settings: { askBeforeSpeaking: true, voiceId: 'voice-a' } };
  assert.deepEqual(prefsFromToolkit(null, effective), { beforeSpeaking: 'check', voiceId: 'voice-a' });
});

test('an empty or malformed profile says nothing', () => {
  assert.deepEqual(prefsFromToolkit(null, null), {});
  assert.deepEqual(prefsFromToolkit({ fields: { needs: 'x' } }, { settings: { fontScale: 'big' } }), {});
});

test('the profile overrides only the choices it speaks about', () => {
  const mine = { textSize: 'large', highContrast: false, reduceMotion: false, speechRate: 1, beforeSpeaking: 'speak', voiceId: 'a' };
  assert.deepEqual(choicesFromPrefs({ textSize: 'huge', reduceMotion: true }, mine), { ...mine, textSize: 'huge', reduceMotion: true });
  assert.deepEqual(choicesFromPrefs({}, mine), mine);
});

test('write-back sends only what changed, as shared and app-scoped keys', () => {
  const before = { textSize: 'large', highContrast: false, reduceMotion: false, speechRate: 1, beforeSpeaking: 'speak', voiceId: 'a' };
  assert.deepEqual(sharedWrites(before, { ...before, textSize: 'huge' }), [['fontScale', 145]]);
  assert.deepEqual(sharedWrites(before, { ...before, highContrast: true, reduceMotion: true, speechRate: 0.9 }), [
    ['contrastMode', 'light'],
    ['motionReducer', true],
    ['speechRate', 0.9],
  ]);
  assert.deepEqual(sharedWrites(before, before), []);
  assert.deepEqual(scopedWrites(before, { ...before, beforeSpeaking: 'check' }), { askBeforeSpeaking: true });
  assert.deepEqual(scopedWrites(before, { ...before, voiceId: 'b' }), { voiceId: 'b' });
  assert.equal(scopedWrites(before, before), null);
});
