import React from 'react';
import { Pressable, StyleSheet, Text, GestureResponderEvent } from 'react-native';
import { colors, white, radius, type } from '../theme';

type Props = {
  label: string;
  onPress: (e: GestureResponderEvent) => void;
  // 'muted' matches the dimmed italic note beside the phone field — for a link that should be
  // reachable without competing with the primary action for attention.
  tone?: 'default' | 'error' | 'muted';
  centered?: boolean;
};

// Text button — Eaze_design_handbook.md §1.6 "A text button".
// No visible container at rest; lowest emphasis, for tertiary actions in a list of options.
export function TextButton({ label, onPress, tone = 'default', centered = false }: Props) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [styles.base, centered && styles.centered, pressed && styles.pressed]}
      hitSlop={8}
    >
      <Text
        style={[
          styles.label,
          tone === 'error' && styles.errorLabel,
          tone === 'muted' && styles.mutedLabel,
          centered && styles.centeredLabel,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    paddingVertical: 8,
    paddingHorizontal: 4,
    borderRadius: radius.button,
    alignSelf: 'flex-start',
  },
  centered: {
    alignSelf: 'stretch',
  },
  pressed: {
    backgroundColor: white[10],
  },
  label: {
    ...type.label2P,
    color: colors.primary[500],
  },
  mutedLabel: {
    color: white[50],
  },
  centeredLabel: {
    textAlign: 'center',
  },
  errorLabel: {
    color: colors.error[500],
  },
});
