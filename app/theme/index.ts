/** The app's visual system: warm cream, white cards, one deep maroon accent, Geist. */

/** Colours, all AA on the backgrounds they are used on. Meaning never rests on colour alone. */
export const colors = {
  background: '#F8F2EC',
  surface: '#FFFFFF',
  tint: '#EFD8CF',
  working: '#F5DCCB',
  border: '#E2CFC4',
  text: '#1E1A18',
  muted: '#5E514B',
  // Only on the background or white (4.65:1 on cream).
  faint: '#7A6A62',
  accent: '#7E1414',
  accentText: '#FFFFFF',
  // Only for answering and starting a call, as on the phone's own call screen.
  go: '#1E7B3C',
  ink: '#1E1A18',
  inkText: '#FFFFFF',
} as const;

export const fonts = {
  regular: 'Geist_400Regular',
  medium: 'Geist_500Medium',
  semibold: 'Geist_600SemiBold',
} as const;

/** Spacing steps in points, on a 4-point grid. */
export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 } as const;

/** Corner radii: cards and buttons, and fully round pills. */
export const radius = 20;
export const pill = 999;

/** Minimum touch target sizes in points: every control, the secondary round buttons, and the Talk button. */
export const target = { min: 48, round: 72, talk: 120 } as const;

/** On wide screens the app sits in a phone-width column so it reads well on a laptop. */
export const maxContentWidth = 520;

/** The three text sizes he can choose; the multiplier scales every size in the app. */
export const textScales = { large: 1, xl: 1.2, huge: 1.45 } as const;
export type TextSize = keyof typeof textScales;
