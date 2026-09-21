import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { white, radius, spacing, type } from '../theme';
import { OutlinedButton } from './OutlinedButton';

type Props = {
  label: string;
  message: string;
  copyButtonLabel: string;
  onCopy: () => void;
};

// Persistent surface: fill + radius only, no shadow (design handbook §1.5/§2).
export function CopyableMessageCard({ label, message, copyButtonLabel, onCopy }: Props) {
  return (
    <View style={styles.card}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.message}>{message}</Text>
      <OutlinedButton label={copyButtonLabel} onPress={onCopy} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: white[10],
    borderRadius: radius.input,
    padding: spacing.unit,
    gap: 12,
  },
  label: {
    ...type.title4,
    color: white[60],
  },
  message: {
    ...type.body1,
    color: white[100],
  },
});
