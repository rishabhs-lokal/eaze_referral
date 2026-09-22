import React from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, fontFamily, radius, spacing, type, white } from '../theme';

type Props = {
  label: string;
  message: string;
  copyButtonLabel: string;
  onCopy: () => void;
};

// Deliberate, disclosed exception to the design handbook's "no drop shadow on persistent
// surfaces" rule (§1.5/§2, same rule Toast.tsx cites) — this card is meant to read as a
// message bubble sitting on top of the screen, not a flat panel, so it gets real elevation.
const cardElevation = Platform.select({
  web: { boxShadow: '0px 12px 28px rgba(0,0,0,0.35), 0px 3px 8px rgba(0,0,0,0.22)' },
  default: {
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.32,
    shadowRadius: 18,
    elevation: 14,
  },
}) as Record<string, unknown>;

// White "chat bubble" card — deliberately breaks from the app's dark-surface convention so
// the invite message itself reads like a WhatsApp message the user is about to send: white
// fill, black text, a squared-off bottom-left corner suggesting a bubble tail, and real
// elevation (see cardElevation above) instead of the usual fill+radius-only lift.
export function CopyableMessageCard({ label, message, copyButtonLabel, onCopy }: Props) {
  return (
    <View style={[styles.card, cardElevation]}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.message}>{message}</Text>
      <Pressable
        onPress={onCopy}
        accessibilityRole="button"
        style={({ pressed }) => [styles.copyButton, pressed && styles.copyButtonPressed]}
      >
        <Text style={styles.copyButtonLabel}>{copyButtonLabel}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    borderBottomRightRadius: 18,
    borderBottomLeftRadius: 4, // bubble "tail" corner
    padding: spacing.unit,
    gap: 12,
  },
  label: {
    ...type.title4,
    color: 'rgba(23,26,29,0.55)', // black100 at reduced opacity — the light-surface mirror of white[60]
  },
  message: {
    ...type.body1,
    fontFamily: fontFamily.bodyBoldItalic,
    color: colors.base.black100,
  },
  copyButton: {
    height: 48,
    borderRadius: radius.button,
    backgroundColor: colors.primary[500],
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.unit,
  },
  copyButtonPressed: {
    backgroundColor: colors.primary[800],
  },
  copyButtonLabel: {
    ...type.label1P,
    color: white[100],
  },
});
