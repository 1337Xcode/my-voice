/** The one-line toolkit sync status under Settings (spec 11.7); renders nothing when the toolkit is not configured. */
import { AppText } from '@/components/AppText';
import { useToolkit } from './ToolkitSync';

/** "Accessibility profile: synced at 14:05", or what went wrong. */
export function ToolkitStatus() {
  const { status, syncedAt, message } = useToolkit();
  if (status === 'off') return null;
  const time = syncedAt ? new Date(syncedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : null;
  const line = status === 'connecting' ? 'connecting' : status === 'error' ? (message ?? 'not synced') : `synced at ${time}${message ? ` · ${message}` : ''}`;
  return (
    <AppText variant="caption" tone="muted" accessibilityLiveRegion="polite" testID="toolkit-status">
      Accessibility profile: {line}
    </AppText>
  );
}
