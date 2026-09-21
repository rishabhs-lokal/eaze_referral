import React from 'react';
import { Pressable, StyleSheet, Text, GestureResponderEvent } from 'react-native';
import { colors, white, radius, type } from '../theme';

type Props = {
  label: string;
  onPress: (e: GestureResponderEvent) => void;
  tone?: 'default' | 'error';
};

// Text button — Eaze_design_handbook.md §1.6 "A text button".
// No visible container at rest; lowest emphasis, for tertiary actions in a list of options.
export function TextButton({ label, onPress, tone = 'default' }: Props) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [styles.base, pressed && styles.pressed]}
      hitSlop={8}
    >
      <Text style={[styles.label, tone === 'error' && styles.errorLabel]}>{label}</Text>
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
  pressed: {
    backgroundColor: white[10],
  },
  label: {
    ...type.label2P,
    color: colors.primary[500],
  },
  errorLabel: {
    color: colors.error[500],
  },
});
