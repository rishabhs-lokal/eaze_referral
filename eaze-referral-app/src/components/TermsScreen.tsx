import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { white, spacing, type } from '../theme';
import { GradientBackground } from './GradientBackground';
import { referralCopy, termsSections } from '../content/referral';

type Props = {
  onBack: () => void;
};

// Matches eaze-level-up's #terms screen: same full-page gradient as the rest of the app, a
// back-arrow + centered title top bar, and sections (numbered title + body) inside a single
// card using that app's own card-fill tone (primary-500 at low opacity) rather than this app's
// usual neutral white-10 surface — the one deliberate borrow from that screen's visual language.
const CARD_FILL = 'rgba(255,158,68,0.14)'; // eaze-level-up's --card-fill

export function TermsScreen({ onBack }: Props) {
  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'bottom', 'left', 'right']}>
      <GradientBackground />
      <View style={styles.topbar}>
        <Pressable
          onPress={onBack}
          accessibilityRole="button"
          accessibilityLabel={referralCopy.backButtonLabel}
          hitSlop={8}
          style={styles.backButton}
        >
          <Text style={styles.backButtonGlyph}>{'←'}</Text>
        </Pressable>
        <Text style={styles.title} numberOfLines={1}>
          {referralCopy.termsTitle}
        </Text>
        <View style={styles.backButton} />
      </View>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        <View style={styles.card}>
          {termsSections.map((section, index) => (
            <View key={section.title} style={styles.section}>
              <Text style={styles.sectionHeading}>
                {index + 1}. {section.title}
              </Text>
              <Text style={styles.sectionBody}>{section.body}</Text>
            </View>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: 'transparent',
  },
  topbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.screenPadding,
    paddingTop: spacing.screenPadding,
    gap: 10,
  },
  backButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: white[10],
  },
  backButtonGlyph: {
    ...type.title3,
    color: white[100],
  },
  title: {
    ...type.title3,
    color: white[100],
    flex: 1,
    textAlign: 'center',
  },
  scrollContent: {
    flexGrow: 1,
    alignItems: 'center',
    paddingHorizontal: spacing.screenPadding,
    paddingTop: 8,
    paddingBottom: 40,
  },
  card: {
    width: '100%',
    maxWidth: 430,
    gap: 20,
    padding: 18,
    borderRadius: 20,
    backgroundColor: CARD_FILL,
    borderWidth: 1,
    borderColor: white[40],
  },
  section: {
    gap: 6,
  },
  sectionHeading: {
    ...type.title4,
    color: white[100],
  },
  sectionBody: {
    ...type.body2,
    color: white[80],
    lineHeight: 21,
  },
});
