/** The app's visual system: muted warm greys, Geist, one restrained accent (spec 11.10). */
import { Platform } from 'react-native';

export const colors = {
  background: '#F6F5F2',
  surface: '#FFFFFF',
  sunken: '#EDEBE6',
  border: '#DEDAD3',
  text: '#1D1B18',
  muted: '#625D55',
  faint: '#8E887F',
  accent: '#2F6A58',
  accentText: '#FFFFFF',
  danger: '#A3361F',
  warning: '#8A5A00',
} as const;

export const fonts = {
  regular: 'Geist_400Regular',
  medium: 'Geist_500Medium',
  semibold: 'Geist_600SemiBold',
} as const;

/** Spacing steps in points, on a 4-point grid. */
export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

export const radius = 12;

/** Minimum touch target sizes in points: every control, and the primary buttons. */
export const target = { min: 48, primary: 72 } as const;

/** The three text sizes he can choose; the multiplier scales every size in the app. */
export const textScales = { large: 1, xl: 1.25, huge: 1.6 } as const;
export type TextSize = keyof typeof textScales;

export const shadow = Platform.select({
  ios: { shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 8, shadowOffset: { width: 0, height: 2 } },
  default: { elevation: 2 },
});
