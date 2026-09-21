import React from 'react';
import { StyleSheet } from 'react-native';
import Svg, { Defs, RadialGradient, Rect, Stop } from 'react-native-svg';
import { colors } from '../theme';

// Matches a real background treatment from the shipped Eaze app (warm blob top-left, cool blob
// top-right, both dissolving into the base dark fill) — an intentional exception to the design
// handbook's "no gradient mesh" rule, per the handbook's own note that a shipped screen overrides
// the file's guidance. Two overlapping radial gradients over the flat base color; both fade to
// fully transparent well above the fold so cards/text lower on the screen sit on plain #171A1D.
export function GradientBackground() {
  return (
    <Svg
      style={[StyleSheet.absoluteFill, { pointerEvents: 'none' }]}
      width="100%"
      height="100%"
      preserveAspectRatio="none"
    >
      <Defs>
        <RadialGradient id="warmBlob" cx="8%" cy="-6%" r="62%" gradientUnits="objectBoundingBox">
          <Stop offset="0%" stopColor="#A8703F" stopOpacity={0.95} />
          <Stop offset="45%" stopColor="#6B4340" stopOpacity={0.5} />
          <Stop offset="100%" stopColor={colors.base.black100} stopOpacity={0} />
        </RadialGradient>
        <RadialGradient id="coolBlob" cx="92%" cy="-10%" r="58%" gradientUnits="objectBoundingBox">
          <Stop offset="0%" stopColor="#4E2F68" stopOpacity={0.9} />
          <Stop offset="50%" stopColor="#2E2044" stopOpacity={0.45} />
          <Stop offset="100%" stopColor={colors.base.black100} stopOpacity={0} />
        </RadialGradient>
      </Defs>
      <Rect x="0" y="0" width="100%" height="100%" fill={colors.base.black100} />
      <Rect x="0" y="0" width="100%" height="100%" fill="url(#coolBlob)" />
      <Rect x="0" y="0" width="100%" height="100%" fill="url(#warmBlob)" />
    </Svg>
  );
}
