/** His call code and link (`POST /calls/link`): family open the link, or type the code, to call him from any browser. */
import { Check, Share2 } from 'lucide-react-native';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Platform, Share, StyleSheet, View } from 'react-native';
import { z } from 'zod';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { ErrorNote } from '@/components/ErrorNote';
import { api } from '@/features/connection/api';
import { useSettings } from '@/features/settings/SettingsProvider';
import { colors, fonts, radius, space } from '@/theme';

const linkSchema = z.object({ code: z.string(), url_path: z.string() });

/** Where the web app lives: this page's own address on web, or the configured address in the phone app. */
function webOrigin(): string | null {
  if (Platform.OS === 'web' && typeof window !== 'undefined') return window.location.origin;
  return process.env.EXPO_PUBLIC_WEB_URL?.replace(/\/$/, '') || null;
}

/** Shares the link with the system sheet, or copies it where sharing is not available. */
async function shareLink(code: string, url: string | null): Promise<'shared' | 'copied'> {
  const message = url ? `Call me on My Voice: ${url}` : `Call me on My Voice with the code ${code}.`;
  if (Platform.OS === 'web' && !navigator.share) {
    await navigator.clipboard.writeText(url ?? message);
    return 'copied';
  }
  await Share.share(url && Platform.OS === 'ios' ? { message: 'Call me on My Voice', url } : { message });
  return 'shared';
}

export function CallCode() {
  const { settings, loaded } = useSettings();
  const [link, setLink] = useState<{ code: string; url: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api<unknown>(settings, `/calls/link?speaker=${settings.dev.speaker}`, { method: 'POST' })
      .then((body) => {
        const { code, url_path } = linkSchema.parse(body);
        const origin = webOrigin();
        setLink({ code, url: origin ? `${origin}${url_path}` : null });
      })
      .catch((e: Error) => setError(e instanceof z.ZodError ? 'The call link from the server was not readable.' : e.message));
  }, [settings]);

  useEffect(() => {
    if (loaded) load();
    // One link per visit; the server address and token are all that change it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, settings.dev.serverUrl, settings.dev.token, settings.dev.speaker]);

  const share = async () => {
    if (!link) return;
    try {
      if ((await shareLink(link.code, link.url)) === 'copied') {
        setCopied(true);
        setTimeout(() => setCopied(false), 2_000);
      }
    } catch {
      // Closing the share sheet without sharing is not an error.
    }
  };

  if (error) return <ErrorNote message={error} onRetry={load} />;
  return (
    <View style={styles.card}>
      <AppText variant="caption" tone="muted">
        Your call code
      </AppText>
      {link ? (
        <AppText variant="title" size={44} style={styles.code} accessibilityLabel={`Your call code: ${link.code.split('').join(' ')}`} selectable>
          {link.code}
        </AppText>
      ) : (
        <ActivityIndicator color={colors.muted} style={styles.loading} />
      )}
      <Button label={copied ? 'Link copied' : 'Share link'} icon={copied ? Check : Share2} kind="primary" onPress={() => void share()} disabled={!link} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: { alignItems: 'center', gap: space.md, padding: space.xl, borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  code: { fontFamily: fonts.semibold, letterSpacing: 6, fontVariant: ['tabular-nums'] },
  loading: { height: 53 },
});
