/** Calls: his call code for app-to-app calls, joining someone's call, and phone contacts (on the phone only). */
import { router } from 'expo-router';
import { Phone, Trash2 } from 'lucide-react-native';
import { z } from 'zod';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { Screen } from '@/components/Screen';
import { CallCode } from '@/features/calls/CallCode';
import { cleanNumber, Contact, EMERGENCY_NOTE, isEmergencyNumber, loadContacts, loadOpeningLine, saveContacts, saveOpeningLine } from '@/features/calls/contacts';
import { api } from '@/features/connection/api';
import { useSettings } from '@/features/settings/SettingsProvider';
import { colors, fonts, radius, space, target } from '@/theme';

function Field({ label, value, onChangeText, onBlur, phone = false, multiline = false }: { label: string; value: string; onChangeText: (t: string) => void; onBlur?: () => void; phone?: boolean; multiline?: boolean }) {
  return (
    <View style={styles.field}>
      <AppText variant="caption" tone="muted">
        {label}
      </AppText>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChangeText}
        onBlur={onBlur}
        keyboardType={phone ? 'phone-pad' : 'default'}
        autoComplete={phone ? 'tel' : 'off'}
        multiline={multiline}
        style={[styles.input, multiline && styles.multiline]}
      />
    </View>
  );
}

function ContactRow({ contact, busy, error, onCall, onRemove }: { contact: Contact; busy: boolean; error: string | null; onCall: () => void; onRemove: () => void }) {
  return (
    <View style={styles.contact}>
      <View style={styles.row}>
        <Pressable accessibilityRole="button" accessibilityLabel={`Call ${contact.name}`} accessibilityState={{ busy }} disabled={busy} onPress={onCall} style={styles.rowMain}>
          <View style={styles.flex}>
            <AppText variant="label">{contact.name}</AppText>
            <AppText variant="caption" tone="muted">
              {contact.number}
            </AppText>
          </View>
          <View style={styles.call}>{busy ? <ActivityIndicator color={colors.accentText} /> : <Phone size={22} color={colors.accentText} fill={colors.accentText} />}</View>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel={`Remove ${contact.name}`} onPress={onRemove} hitSlop={4} style={styles.remove}>
          <Trash2 size={20} color={colors.muted} />
        </Pressable>
      </View>
      {error ? <ErrorNote message={error} /> : null}
    </View>
  );
}

const startedSchema = z.object({ call_id: z.string() });

/** Someone else's call code, typed in, opens their call page. */
function JoinCall() {
  const [code, setCode] = useState('');
  const digits = code.replace(/\D/g, '');
  return (
    <View style={styles.card}>
      <Field label="Join a call: their code" value={code} onChangeText={setCode} phone />
      <Button label="Join" onPress={() => router.push({ pathname: '/c/[code]', params: { code: digits } })} disabled={digits.length < 4} style={styles.add} />
    </View>
  );
}

export default function CallsScreen() {
  const { settings } = useSettings();
  const [calling, setCalling] = useState<{ id: string; error: string | null } | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [opening, setOpening] = useState('');
  const [name, setName] = useState('');
  const [number, setNumber] = useState('');
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    void loadContacts().then(setContacts);
    void loadOpeningLine().then(setOpening);
  }, []);

  const update = (next: Contact[]) => {
    setContacts(next);
    void saveContacts(next);
  };

  const add = () => {
    if (isEmergencyNumber(number)) return setNote(EMERGENCY_NOTE);
    const cleaned = cleanNumber(number);
    if (cleaned.replace('+', '').length < 6) return setNote('Enter the full phone number, with its country code.');
    update([...contacts, { id: `c${Date.now().toString(36)}`, name: name.trim() || cleaned, number: cleaned }]);
    setName('');
    setNumber('');
    setNote(null);
  };

  const call = async (contact: Contact) => {
    if (isEmergencyNumber(contact.number)) return setNote(EMERGENCY_NOTE);
    setCalling({ id: contact.id, error: null });
    try {
      const body = { number: contact.number, name: contact.name, opening_line: opening.trim() || undefined };
      const { call_id } = startedSchema.parse(await api<unknown>(settings, `/calls?speaker=${settings.dev.speaker}`, { method: 'POST', body: JSON.stringify(body) }));
      setCalling(null);
      router.push({ pathname: '/call', params: { callId: call_id, name: contact.name, kind: 'phone' } });
    } catch (e) {
      setCalling({ id: contact.id, error: e instanceof z.ZodError ? 'The server answered in a way the app could not read.' : (e as Error).message });
    }
  };

  return (
    <Screen>
      <CallCode />
      <JoinCall />
      <AppText variant="heading" accessibilityRole="header" style={styles.section}>
        Phone calls
      </AppText>
      {contacts.map((contact) => (
        <ContactRow
          key={contact.id}
          contact={contact}
          busy={calling?.id === contact.id && !calling.error}
          error={calling?.id === contact.id ? calling.error : null}
          onCall={() => void call(contact)}
          onRemove={() => update(contacts.filter((c) => c.id !== contact.id))}
        />
      ))}
      <View style={styles.card}>
        <AppText variant="label">Add a contact</AppText>
        <Field label="Name" value={name} onChangeText={setName} />
        <Field label="Phone number" value={number} onChangeText={setNumber} phone />
        {note ? <ErrorNote message={note} /> : null}
        <Button label="Add" kind="primary" onPress={add} disabled={!number.trim()} style={styles.add} />
      </View>
      <View style={styles.card}>
        <Field label="Opening line, said when they answer" value={opening} onChangeText={setOpening} onBlur={() => void saveOpeningLine(opening.trim())} multiline />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  section: { marginTop: space.sm },
  contact: { gap: space.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  rowMain: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: space.md, minHeight: target.min + 24, paddingLeft: space.lg, paddingRight: space.sm, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  call: { width: target.min + 4, height: target.min + 4, borderRadius: target.min, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.accent },
  remove: { width: target.min, height: target.min, alignItems: 'center', justifyContent: 'center' },
  card: { gap: space.md, padding: space.lg, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  field: { gap: space.xs },
  input: { minHeight: target.min, paddingHorizontal: space.md, borderRadius: 12, borderWidth: 1, borderColor: colors.border, fontFamily: fonts.regular, fontSize: 17, color: colors.text, backgroundColor: colors.background },
  multiline: { minHeight: 80, paddingVertical: space.sm, textAlignVertical: 'top' },
  add: { alignSelf: 'flex-start' },
});
