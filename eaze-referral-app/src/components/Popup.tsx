import React from 'react';
import { Modal, Pressable, StyleSheet, Text, View, GestureResponderEvent } from 'react-native';
import { black, colors, spacing, type, white } from '../theme';

type Props = {
  visible: boolean;
  onClose: () => void;
  eyebrow: string;
  title: string;
  bullets?: string[];
  primaryLabel: string;
  onPrimary: () => void;
  secondaryLabel?: string;
  onSecondary?: () => void;
};

// Centered dialog popup — matches eaze-level-up's `.sbg`/`.info-modal` language (the
// established popup formatting in this project's sibling app): black-75 scrim, dark
// 20px-radius card with a white-20 border, uppercase eyebrow + bold title, dot-bulleted
// list, and a pill-shaped primary-500 CTA. Tapping the scrim (not the card) dismisses it,
// same as eaze-level-up's info modal.
export function Popup({
  visible,
  onClose,
  eyebrow,
  title,
  bullets,
  primaryLabel,
  onPrimary,
  secondaryLabel,
  onSecondary,
}: Props) {
  const stopPropagation = (e: GestureResponderEvent) => e.stopPropagation();

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.scrim} onPress={onClose} accessibilityRole="none">
        <Pressable style={styles.card} onPress={stopPropagation}>
          <Pressable
            onPress={onClose}
            accessibilityRole="button"
            accessibilityLabel="Close"
            style={styles.closeButton}
            hitSlop={8}
          >
            <Text style={styles.closeText}>✕</Text>
          </Pressable>

          <Text style={styles.eyebrow}>{eyebrow}</Text>
          <Text style={styles.title}>{title}</Text>

          {bullets && bullets.length > 0 && (
            <View style={styles.list}>
              {bullets.map((bullet, i) => (
                <View key={i} style={styles.listRow}>
                  <View style={styles.dot} />
                  <Text style={styles.listText}>{bullet}</Text>
                </View>
              ))}
            </View>
          )}

          <Pressable
            onPress={onPrimary}
            accessibilityRole="button"
            style={({ pressed }) => [styles.cta, pressed && styles.ctaPressed]}
          >
            <Text style={styles.ctaLabel}>{primaryLabel}</Text>
          </Pressable>

          {secondaryLabel && onSecondary && (
            <Pressable onPress={onSecondary} accessibilityRole="button" style={styles.secondary} hitSlop={8}>
              <Text style={styles.secondaryLabel}>{secondaryLabel}</Text>
            </Pressable>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: {
    flex: 1,
    backgroundColor: black[75],
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.screenPadding,
  },
  card: {
    width: '100%',
    maxWidth: 340,
    backgroundColor: colors.base.black100,
    borderWidth: 1,
    borderColor: white[20],
    borderRadius: 20,
    paddingTop: 28,
    paddingHorizontal: 24,
    paddingBottom: 24,
    alignItems: 'center',
  },
  closeButton: {
    position: 'absolute',
    top: 14,
    right: 14,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: white[10],
    alignItems: 'center',
    justifyContent: 'center',
  },
  closeText: {
    ...type.label3,
    color: white[60],
  },
  eyebrow: {
    ...type.label4P,
    letterSpacing: 0.4,
    textTransform: 'uppercase',
    color: white[60],
    textAlign: 'center',
  },
  title: {
    ...type.title3,
    color: white[100],
    textAlign: 'center',
    marginTop: 4,
  },
  list: {
    width: '100%',
    marginTop: 16,
    gap: 10,
  },
  listRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.primary[500],
    marginTop: 7,
  },
  listText: {
    ...type.body2,
    color: white[80],
    flex: 1,
  },
  cta: {
    marginTop: 18,
    paddingVertical: 10,
    paddingHorizontal: 22,
    borderRadius: 999,
    backgroundColor: colors.primary[500],
    alignItems: 'center',
    justifyContent: 'center',
  },
  ctaPressed: {
    backgroundColor: colors.primary[800],
  },
  ctaLabel: {
    ...type.label2P,
    color: white[100],
  },
  secondary: {
    marginTop: 10,
    paddingVertical: 6,
    paddingHorizontal: 4,
  },
  secondaryLabel: {
    ...type.label3P,
    color: white[60],
  },
});
