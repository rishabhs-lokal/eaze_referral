import React from 'react';
import { Pressable, StyleSheet, Text, ActivityIndicator, GestureResponderEvent } from 'react-native';
import { colors, white, radius, spacing, type } from '../theme';

type Props = {
  label: string;
  onPress: (e: GestureResponderEvent) => void;
  disabled?: boolean;
  loading?: boolean;
};

// Filled button — Eaze_design_handbook.md §1.6 "A filled button".
// One of these per screen at most: it's the single high-emphasis CTA.
export function PrimaryButton({ label, onPress, disabled, loading }: Props) {
  const isDisabled = disabled || loading;
  return (
    <Pressable
      onPress={onPress}
      disabled={isDisabled}
      accessibilityRole="button"
      accessibilityState={{ disabled: isDisabled }}
      style={({ pressed }) => [
        styles.base,
        isDisabled && styles.disabled,
        pressed && !isDisabled && styles.pressed,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={white[100]} />
      ) : (
        <Text style={styles.label}>{label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    height: 48,
    borderRadius: radius.button,
    backgroundColor: colors.primary[500],
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.unit,
  },
  pressed: {
    backgroundColor: colors.primary[800],
  },
  disabled: {
    backgroundColor: white[10],
  },
  label: {
    ...type.label1P,
    color: white[100],
  },
});
