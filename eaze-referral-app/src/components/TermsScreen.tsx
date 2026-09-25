import React from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, white, spacing, type } from '../theme';
import { GradientBackground } from './GradientBackground';
import { referralCopy, termsDocumentTitle, termsSections } from '../content/referral';

type Props = {
  onBack: () => void;
};

// Matches eaze-level-up's #terms screen: same full-page gradient as the rest of the app, a
// back-arrow + centered title top bar, and sections (numbered title + body) inside a single
// card using that app's own card-fill tone (primary-500 at low opacity) rather than this app's
// usual neutral white-10 surface — the one deliberate borrow from that screen's visual language.
const CARD_FILL = 'rgba(255,158,68,0.14)'; // eaze-level-up's --card-fill

type TermsLink = { label: string; url: string };

// A section body may embed `{{key}}` tokens (see content/referral.ts's Program Overview &
// Eligibility section) that resolve against that section's own `links` map. Splits the plain
// string on those tokens and renders the rest as ordinary text, with each token replaced by a
// tappable inline Text — RN allows nested Text nodes to wrap inline within a parent paragraph,
// so this reads as one continuous sentence, not a separate block.
function renderSectionBody(body: string, links?: Record<string, TermsLink>) {
  if (!links) return body;
  const parts = body.split(/(\{\{\w+\}\})/g);
  return parts.map((part, i) => {
    const match = part.match(/^\{\{(\w+)\}\}$/);
    if (!match) return part;
    const link = links[match[1]];
    if (!link) return part;
    return (
      <Text key={i} style={styles.link} onPress={() => Linking.openURL(link.url)}>
        {link.label}
      </Text>
    );
  });
}

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
          <Text style={styles.documentTitle}>{termsDocumentTitle}</Text>
          {termsSections.map((section, index) => (
            <View key={section.title} style={styles.section}>
              <Text style={styles.sectionHeading}>
                {index + 1}. {section.title}
              </Text>
              <Text style={styles.sectionBody}>
                {renderSectionBody(section.body, (section as { links?: Record<string, TermsLink> }).links)}
              </Text>
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
  documentTitle: {
    ...type.title2,
    color: white[100],
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
  link: {
    color: colors.primary[500],
    textDecorationLine: 'underline',
  },
});
