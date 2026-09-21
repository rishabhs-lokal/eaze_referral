// Spacing, radius and elevation from Eaze_design_handbook.md §1.3-1.5.
import { Platform } from 'react-native';

export const spacing = {
  unit: 16,
  screenPadding: 16,
  buttonIconGap: 8,
} as const;

export const radius = {
  button: 12,
  input: 12,
  toast: 12,
} as const;

// The single approved shadow token — toasts/overlays only, never persistent surfaces
// (cards, buttons, list rows, inputs get their lift from fill + radius alone).
// RN Web deprecated the shadow* style props in favor of the CSS `boxShadow` shorthand;
// native (iOS/Android) still needs the shadow*/elevation props. Platform.select here so
// callers just spread one token either way.
export const shadowDefaultDown1 = Platform.select({
  web: { boxShadow: '0px 2px 4px rgba(0, 0, 0, 0.1)' },
  default: {
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 4, // Android shadow approximation
  },
}) as Record<string, unknown>;
