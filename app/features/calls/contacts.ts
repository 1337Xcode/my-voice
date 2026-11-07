/** His call contacts and opening line, stored on the phone only (spec 11.6, 16). */
import AsyncStorage from '@react-native-async-storage/async-storage';

const CONTACTS_KEY = 'contacts.v1';
const OPENING_KEY = 'openingLine.v1';

export type Contact = { id: string; name: string; number: string };

/** The numbers that must be called directly (spec 11.6). */
const EMERGENCY_NUMBERS = new Set(['999', '112', '911']);

export const EMERGENCY_NOTE = 'Call emergency numbers directly, or use emergencySMS.';

/** True for an emergency number, however it is written (spaces, dashes, a leading +). */
export function isEmergencyNumber(number: string): boolean {
  return EMERGENCY_NUMBERS.has(number.replace(/[^\d]/g, ''));
}

/** A number in a form the phone network accepts: digits with an optional leading +. */
export function cleanNumber(number: string): string {
  const trimmed = number.trim();
  return (trimmed.startsWith('+') ? '+' : '') + trimmed.replace(/[^\d]/g, '');
}

/** The contact a fresh phone starts with, so the first call is one tap; he can rename or delete it. */
export const PRESET_CONTACTS: Contact[] = [{ id: 'preset-1', name: 'Friend', number: '+447942733883' }];

export async function loadContacts(): Promise<Contact[]> {
  const raw = await AsyncStorage.getItem(CONTACTS_KEY).catch(() => null);
  return raw ? (JSON.parse(raw) as Contact[]) : PRESET_CONTACTS;
}

export async function saveContacts(contacts: Contact[]): Promise<void> {
  await AsyncStorage.setItem(CONTACTS_KEY, JSON.stringify(contacts));
}

export async function loadOpeningLine(): Promise<string> {
  return (await AsyncStorage.getItem(OPENING_KEY).catch(() => null)) ?? '';
}

export async function saveOpeningLine(line: string): Promise<void> {
  await AsyncStorage.setItem(OPENING_KEY, line);
}
