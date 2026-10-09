import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { colors, white, radius, type, fontFamily } from '../theme';
import {
  isLikelyFakeIndianMobileLocal,
  isValidIndianMobileLocal,
  sanitizeLocalDigits,
} from '../state/phoneValidation';

type Props = {
  label: string;
  value: string; // local 10-digit part only, no +91
  onChangeValue: (local: string) => void;
  onValidityChange?: (valid: boolean) => void;
  showErrorWhenEmpty?: boolean; // set true after a submit attempt, to surface "required"
  required?: boolean; // only the first field is a hard requirement — see ReferralScreen
  rightAccessory?: React.ReactNode; // e.g. a "Remove" text button, inline with the label
  // Shown between the label and the input, so it is read before a number is typed rather than
  // discovered underneath one already entered. Only the first field passes it — repeating the
  // same caveat under every field would be noise.
  note?: string;
  // Locked until the referrer has consented. A disabled field alone would read as a bug, so
  // every touch on it reports WHY via onLockedPress rather than doing nothing.
  locked?: boolean;
  onLockedPress?: () => void;
  testID?: string;
};

// Input field with a fixed +91 prefix — Eaze_design_handbook.md §1.6 "An input field",
// prefix-chip variant. An empty *required* field or any malformed number shows the Error ramp;
// an empty *optional* field is fine left blank — it's just not submitted.
export function PhoneNumberField({
  label,
  value,
  onChangeValue,
  onValidityChange,
  showErrorWhenEmpty,
  required = false,
  rightAccessory,
  note,
  locked = false,
  onLockedPress,
  testID,
}: Props) {
  const [touched, setTouched] = useState(false);

  const isEmpty = value.length === 0;
  const isComplete = value.length === 10;
  const isFormatValid = isComplete && isValidIndianMobileLocal(value);
  const isFake = isFormatValid && isLikelyFakeIndianMobileLocal(value);
  const isCorrectFormat = isFormatValid && !isFake;
  // An optional field left untouched is not an error — nothing to submit, nothing wrong.
  const isValid = required ? isCorrectFormat : isEmpty || isCorrectFormat;
  // A locked field is never "wrong" — the referrer hasn't been allowed to fill it yet, so
  // flagging it as missing would blame them for the gate.
  const showError =
    !locked && (touched || showErrorWhenEmpty) && ((isEmpty && required) || (isComplete && !isCorrectFormat));

  React.useEffect(() => {
    onValidityChange?.(isValid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isValid]);

  return (
    <View style={styles.wrapper}>
      <View style={styles.labelRow}>
        <Text style={styles.label}>
          {label}
          {required && <Text style={styles.required}> *</Text>}
        </Text>
        {rightAccessory}
      </View>
      {note ? <Text style={styles.note}>{note}</Text> : null}
      {/* The Pressable is the whole point of the locked state: an inert greyed-out box tells the
          referrer nothing, so tapping it has to say why it's inert. With editable={false} the
          TextInput ignores the touch and it lands here instead. */}
      <Pressable
        onPress={locked ? onLockedPress : undefined}
        disabled={!locked}
        // On web a Pressable is focusable by default and draws a focus ring, which on a locked
        // field reads as "this input is active, type here" — the exact opposite of the state.
        // The checkbox immediately below is the real keyboard target, and it carries the same
        // error, so nothing is lost by taking this out of the tab order.
        focusable={false}
        style={[styles.inputRow, showError && styles.inputRowError, locked && styles.inputRowLocked]}
      >
        <View style={styles.prefix}>
          <Text style={styles.prefixText}>+91</Text>
        </View>
        <View style={styles.divider} />
        {/* readOnly is not disabled: the input still takes focus on click and draws a focus ring,
            which makes a locked field look live. Killing pointer events is what actually sends
            the touch past it to the Pressable above. */}
        <View style={styles.inputHost} pointerEvents={locked ? 'none' : 'auto'}>
        <TextInput
          testID={testID}
          value={value}
          onChangeText={(raw) => onChangeValue(sanitizeLocalDigits(raw))}
          onBlur={() => setTouched(true)}
          placeholder="9999999999"
          placeholderTextColor={white[40]}
          keyboardType="number-pad"
          maxLength={10}
          editable={!locked}
          style={styles.input}
          accessibilityLabel={label}
          accessibilityState={{ disabled: locked }}
          // Stops the browser/OS focusing a field that cannot be typed into.
          focusable={!locked}
        />
        </View>
      </Pressable>
      {showError && (
        <Text style={styles.errorText}>
          {isEmpty
            ? 'Phone number is required'
            : isFake
              ? "Enter your friend's real number, not a placeholder"
              : 'Enter a valid 10-digit Indian mobile number'}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    gap: 8,
  },
  labelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  label: {
    ...type.label2,
    color: white[80],
  },
  required: {
    color: colors.error[500],
  },
  note: {
    ...type.body4,
    fontFamily: fontFamily.bodyItalic,
    color: white[50],
    marginTop: -2,
  },
  inputRow: {
    height: 48,
    borderRadius: radius.input,
    backgroundColor: white[10],
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'transparent',
  },
  inputRowError: {
    borderColor: colors.error[500],
  },
  inputRowLocked: {
    // Visibly inert — dimmer fill than the normal white[10] so it does not look like a field
    // simply waiting for a tap.
    opacity: 0.45,
  },
  prefix: {
    paddingLeft: 16,
    paddingRight: 8,
  },
  prefixText: {
    ...type.label1,
    color: white[100],
  },
  divider: {
    width: 1,
    height: 24,
    backgroundColor: white[20],
  },
  inputHost: {
    flex: 1,
    height: '100%',
  },
  input: {
    flex: 1,
    height: '100%',
    paddingHorizontal: 12,
    ...type.label1,
    color: white[100],
  },
  errorText: {
    ...type.body3,
    color: colors.error[500],
  },
});
