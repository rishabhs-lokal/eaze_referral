// Values pulled verbatim from Eaze_design_handbook.md §1.1 — do not invent new hex values here.

export const colors = {
  primary: {
    50: '#FFF5EC',
    100: '#FFECDB',
    200: '#FFC998',
    500: '#FF9E44',
    800: '#552A02',
  },
  secondary: {
    50: '#FAF8FF',
    100: '#EAE0FF',
    200: '#C2A5FD',
    500: '#6F3DD5',
    800: '#130D21',
  },
  success: {
    50: '#F1FFF2',
    100: '#D2FFD4',
    200: '#74FF7B',
    500: '#33BF30',
    800: '#08620D',
  },
  error: {
    50: '#FFEAEB',
    100: '#FFD6D9',
    200: '#FF9499',
    500: '#D41A23',
    800: '#6E0005',
  },
  base: {
    black100: '#171A1D',
  },
} as const;

// White-on-dark opacity steps — this is the text/hierarchy system, not a grey palette.
export const white = {
  10: 'rgba(255,255,255,0.10)',
  20: 'rgba(255,255,255,0.20)',
  40: 'rgba(255,255,255,0.40)',
  50: 'rgba(255,255,255,0.50)',
  60: 'rgba(255,255,255,0.60)',
  70: 'rgba(255,255,255,0.70)',
  80: 'rgba(255,255,255,0.80)',
  100: 'rgba(255,255,255,1)',
} as const;

export const black = {
  75: 'rgba(0,0,0,0.75)',
} as const;

export const shadowColor = '#000000';
