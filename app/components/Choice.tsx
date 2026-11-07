/** A row of large options where exactly one is selected; selection is shown by fill and a check, not colour alone. */
import { Check } from 'lucide-react-native';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { colors, pill, space, target } from '@/theme';

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
              {selected ? <Check size={18} color={colors.inkText} strokeWidth={2.5} /> : null}
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
  group: { gap: space.md },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  option: { flexDirection: 'row', alignItems: 'center', gap: space.sm, minHeight: target.min, paddingHorizontal: space.lg, justifyContent: 'center', borderRadius: pill, backgroundColor: colors.tint },
  selected: { backgroundColor: colors.ink },
  pressed: { opacity: 0.75 },
});
