import React from 'react';
import { Pressable, StyleSheet, Text, GestureResponderEvent } from 'react-native';
import { white, radius, spacing, type } from '../theme';

type Props = {
  label: string;
  onPress: (e: GestureResponderEvent) => void;
  disabled?: boolean;
};

// Outlined button — Eaze_design_handbook.md §1.6 "An outlined button".
// Medium emphasis, pairs alongside a filled button — never used alone as a primary action.
export function OutlinedButton({ label, onPress, disabled }: Props) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      style={({ pressed }) => [styles.base, pressed && !disabled && styles.pressed]}
    >
      <Text style={styles.label}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    height: 48,
    borderRadius: radius.button,
    borderWidth: 1,
    borderColor: white[40],
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.unit,
  },
  pressed: {
    backgroundColor: white[10],
  },
  label: {
    ...type.label1P,
    color: white[100],
  },
});
