// Type tokens from Eaze_design_handbook.md §1.2.
//
// Deviation from the handbook, disclosed: the handbook specifies "Fraunces 144pt SuperSoft"
// (the `opsz=144, SOFT=100` instance of the Fraunces variable font). No prebuilt static font
// file for that exact optical-size/softness instance is published via Google Fonts' static
// cuts, and React Native cannot apply CSS-style `font-variation-settings` to reach a variable
// axis at runtime the way a web stylesheet can. We substitute the nearest published static cut,
// `Fraunces_600SemiBold`, for all Headline tokens. Swap in the real "144pt SuperSoft" font file
// here the moment it's available from the design team, everything downstream reads from this
// one map.
export const fontFamily = {
  headline: 'Fraunces_600SemiBold',
  bodyRegular: 'PlusJakartaSans_400Regular',
  bodyBold: 'PlusJakartaSans_700Bold',
} as const;

type TypeToken = {
  fontFamily: string;
  fontSize: number;
  lineHeight: number;
};

export const type: Record<string, TypeToken> = {
  headline1: { fontFamily: fontFamily.headline, fontSize: 32, lineHeight: 36 },
  headline2: { fontFamily: fontFamily.headline, fontSize: 28, lineHeight: 32 },
  headline3: { fontFamily: fontFamily.headline, fontSize: 24, lineHeight: 30 },

  title1: { fontFamily: fontFamily.bodyBold, fontSize: 20, lineHeight: 28 },
  title2: { fontFamily: fontFamily.bodyBold, fontSize: 18, lineHeight: 24 },
  title3: { fontFamily: fontFamily.bodyBold, fontSize: 16, lineHeight: 20 },
  title4: { fontFamily: fontFamily.bodyBold, fontSize: 14, lineHeight: 18 },

  label1: { fontFamily: fontFamily.bodyRegular, fontSize: 16, lineHeight: 24 },
  label1P: { fontFamily: fontFamily.bodyBold, fontSize: 16, lineHeight: 24 },
  label2: { fontFamily: fontFamily.bodyRegular, fontSize: 14, lineHeight: 20 },
  label2P: { fontFamily: fontFamily.bodyBold, fontSize: 14, lineHeight: 20 },
  label3: { fontFamily: fontFamily.bodyRegular, fontSize: 12, lineHeight: 16 },
  label3P: { fontFamily: fontFamily.bodyBold, fontSize: 12, lineHeight: 16 },
  label4: { fontFamily: fontFamily.bodyRegular, fontSize: 11, lineHeight: 16 },
  label4P: { fontFamily: fontFamily.bodyBold, fontSize: 11, lineHeight: 16 },

  body1: { fontFamily: fontFamily.bodyRegular, fontSize: 16, lineHeight: 24 },
  body2: { fontFamily: fontFamily.bodyRegular, fontSize: 14, lineHeight: 20 },
  body3: { fontFamily: fontFamily.bodyRegular, fontSize: 12, lineHeight: 16 },
  body4: { fontFamily: fontFamily.bodyRegular, fontSize: 11, lineHeight: 16 },
};
