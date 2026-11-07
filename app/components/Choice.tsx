/** A row of large options where exactly one is selected; selection is shown by fill and a check, not colour alone. */
import { SymbolView, SymbolViewProps } from 'expo-symbols';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { colors, radius, space, target } from '@/theme';

const checkmark = { ios: 'checkmark', android: 'check', web: 'check' } as SymbolViewProps['name'];

type Option<T extends string> = { value: T; label: string };

type Props<T extends string> = { label: string; options: Option<T>[]; value: T; onChange: (value: T) => void };

export function Choice<T extends string>({ label, options, value, onChange }: Props<T>) {
  return (
    <View style={styles.group} accessibilityRole="radiogroup" accessibilityLabel={label}>
      <AppText variant="label">{label}</AppText>
      <View style={styles.row}>
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <Pressable
              key={option.value}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              onPress={() => onChange(option.value)}
              style={({ pressed }) => [styles.option, selected && styles.selected, pressed && styles.pressed]}>
              {selected ? <SymbolView name={checkmark} tintColor={colors.accentText} size={18} /> : null}
              <AppText variant="label" tone={selected ? 'inverse' : 'default'}>
                {option.label}
              </AppText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  group: { gap: space.sm },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  option: { flexDirection: 'row', alignItems: 'center', gap: space.sm, minHeight: target.min, paddingHorizontal: space.lg, justifyContent: 'center', borderRadius: radius, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  selected: { backgroundColor: colors.accent, borderColor: colors.accent },
  pressed: { opacity: 0.7 },
});
