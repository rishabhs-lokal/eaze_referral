import React, { useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';
import { colors, white, radius, type } from '../theme';
import { isValidIndianMobileLocal, sanitizeLocalDigits } from '../state/phoneValidation';

type Props = {
  label: string;
  value: string; // local 10-digit part only, no +91
  onChangeValue: (local: string) => void;
  onValidityChange?: (valid: boolean) => void;
  showErrorWhenEmpty?: boolean; // set true after a submit attempt, to surface "required"
  rightAccessory?: React.ReactNode; // e.g. a "Remove" text button, inline with the label
  testID?: string;
};

// Input field with a fixed +91 prefix — Eaze_design_handbook.md §1.6 "An input field",
// prefix-chip variant. Mandatory: an empty or malformed number shows the Error ramp.
export function PhoneNumberField({
  label,
  value,
  onChangeValue,
  onValidityChange,
  showErrorWhenEmpty,
  rightAccessory,
  testID,
}: Props) {
  const [touched, setTouched] = useState(false);

  const isEmpty = value.length === 0;
  const isComplete = value.length === 10;
  const isValid = isComplete && isValidIndianMobileLocal(value);
  const showError = (touched || showErrorWhenEmpty) && (isEmpty || (isComplete && !isValid));

  React.useEffect(() => {
    onValidityChange?.(isValid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isValid]);

  return (
    <View style={styles.wrapper}>
      <View style={styles.labelRow}>
        <Text style={styles.label}>{label}</Text>
        {rightAccessory}
      </View>
      <View style={[styles.inputRow, showError && styles.inputRowError]}>
        <View style={styles.prefix}>
          <Text style={styles.prefixText}>+91</Text>
        </View>
        <View style={styles.divider} />
        <TextInput
          testID={testID}
          value={value}
          onChangeText={(raw) => onChangeValue(sanitizeLocalDigits(raw))}
          onBlur={() => setTouched(true)}
          placeholder="9999999999"
          placeholderTextColor={white[40]}
          keyboardType="number-pad"
          maxLength={10}
          style={styles.input}
          accessibilityLabel={label}
        />
      </View>
      {showError && (
        <Text style={styles.errorText}>
          {isEmpty ? 'Phone number is required' : 'Enter a valid 10-digit Indian mobile number'}
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
