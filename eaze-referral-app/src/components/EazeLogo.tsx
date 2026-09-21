import React from 'react';
import { Image, StyleSheet } from 'react-native';

// The real Eaze mark — a white spiral on a transparent background, so it reads cleanly on both
// the flat dark base and the warm/cool gradient areas of the screen.
export function EazeLogo() {
  return (
    <Image
      source={require('../../assets/eaze-symbol.png')}
      style={styles.mark}
      accessibilityLabel="Eaze"
      accessibilityRole="image"
      resizeMode="contain"
    />
  );
}

const styles = StyleSheet.create({
  mark: {
    width: 32,
    height: 32,
  },
});
