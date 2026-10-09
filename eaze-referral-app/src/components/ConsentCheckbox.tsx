import React from 'react';
import { Pressable, StyleSheet, Text, View, Linking } from 'react-native';
import { colors, white, radius, type } from '../theme';

type Props = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  // May contain a single {{terms}} token, rendered as an inline tappable link.
  label: string;
  termsLabel: string;
  onPressTerms: () => void;
  showError?: boolean;
};

// A mandatory declaration, not a nicety: the referrer is handing Eaze someone else's phone
// number, and that person's permission is theirs to confirm explicitly. Inferring consent from
// a Save tap would not be consent at all, so nothing can be submitted until this is ticked.
//
// Built from a Pressable rather than a platform checkbox so it renders identically on web and
// in the app's WebView — React Native has no cross-platform checkbox primitive.
export function ConsentCheckbox({
  checked,
  onChange,
  label,
  termsLabel,
  onPressTerms,
  showError,
}: Props) {
  // The link has to sit inside the sentence that references it — a reader should not have to
  // hunt elsewhere for the document they are being asked to accept.
  const [before, after] = label.split('{{terms}}');

  return (
    <View style={styles.wrapper}>
      <Pressable
        onPress={() => onChange(!checked)}
        accessibilityRole="checkbox"
        accessibilityState={{ checked }}
        accessibilityLabel={label.replace('{{terms}}', termsLabel)}
        style={styles.row}
        hitSlop={6}
      >
        <View style={[styles.box, checked && styles.boxChecked, showError && styles.boxError]}>
          {checked ? <Text style={styles.tick}>✓</Text> : null}
        </View>
        <Text style={styles.label}>
          {before}
          <Text
            style={styles.link}
            onPress={onPressTerms}
            accessibilityRole="link"
          >
            {termsLabel}
          </Text>
          {after}
        </Text>
      </Pressable>
      {showError ? <Text style={styles.error}>Please confirm this to continue</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    gap: 6,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  box: {
    width: 20,
    height: 20,
    borderRadius: radius.input / 2,
    borderWidth: 1.5,
    borderColor: white[40],
    alignItems: 'center',
    justifyContent: 'center',
    // Nudged down so the box aligns with the first line of text rather than its ascender.
    marginTop: 1,
  },
  boxChecked: {
    backgroundColor: colors.primary[500],
    borderColor: colors.primary[500],
  },
  boxError: {
    borderColor: colors.error[500],
  },
  tick: {
    ...type.body4,
    color: white[100],
    lineHeight: 16,
  },
  label: {
    ...type.body4,
    // Bold at the note's size: this is a declaration the user is making, so it should read as
    // weightier than the note above without shouting at a larger size.
    fontWeight: '700',
    color: white[50],
    flex: 1,
  },
  link: {
    ...type.body4,
    fontWeight: '700',
    color: colors.primary[500],
    textDecorationLine: 'underline',
  },
  error: {
    ...type.body4,
    color: colors.error[500],
    marginLeft: 30,
  },
});
