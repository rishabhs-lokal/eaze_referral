import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';
import { colors, radius, shadowDefaultDown1, type } from '../theme';

export type ToastTone = 'success' | 'error';

type Props = {
  tone: ToastTone;
  message: string;
};

// Toast — Eaze_design_handbook.md §1.6 "A toast".
// Fixed 328px width, light-fill surface (the one place a light fill appears on this dark UI),
// with the single system drop shadow — toasts are the approved place for it.
export function Toast({ tone, message }: Props) {
  const isSuccess = tone === 'success';
  const surface = isSuccess ? colors.success[50] : colors.error[50];
  const iconCircle = isSuccess ? colors.success[500] : colors.error[500];
  const textColor = isSuccess ? colors.success[800] : colors.error[800];

  return (
    <View style={[styles.base, { backgroundColor: surface }]} accessibilityRole="alert">
      <View style={[styles.iconCircle, { backgroundColor: iconCircle }]}>
        {isSuccess ? (
          <Svg width={12} height={12} viewBox="0 0 24 24" fill="none">
            <Path d="M5 13l4 4L19 7" stroke="#FFFFFF" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />
          </Svg>
        ) : (
          <Svg width={12} height={12} viewBox="0 0 24 24" fill="none">
            <Circle cx={12} cy={12} r={11} fill="none" />
            <Path d="M12 7v6" stroke="#FFFFFF" strokeWidth={3} strokeLinecap="round" />
            <Circle cx={12} cy={17} r={1.5} fill="#FFFFFF" />
          </Svg>
        )}
      </View>
      <Text style={[styles.message, { color: textColor }]} numberOfLines={2}>
        {message}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    width: 328,
    maxWidth: '100%',
    minHeight: 40,
    borderRadius: radius.toast,
    flexDirection: 'row',
    alignItems: 'center',
    paddingTop: 8,
    paddingRight: 16,
    paddingBottom: 8,
    paddingLeft: 12,
    gap: 12,
    ...shadowDefaultDown1,
  },
  iconCircle: {
    width: 20,
    height: 20,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  message: {
    ...type.body2,
    flexShrink: 1,
  },
});
