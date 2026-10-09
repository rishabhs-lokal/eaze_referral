import React from 'react';
import { Linking, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, fontFamily, radius, spacing, type, white } from '../theme';

type Props = {
  label: string;
  message: string;
  copyButtonLabel: string;
  onCopy: () => void;
  // If the message contains this URL verbatim, that run of text is rendered as a real link.
  linkUrl?: string;
};

// The sender sees this message in a white bubble that looks exactly like the chat app they are
// about to paste it into — so a bare URL sitting there as dead text reads as broken. It is also
// the only way the referrer can check the link actually goes somewhere before sending it on.
//
// On web this has to be a real anchor, not an onPress handler: react-native-web turns `href` on
// a Text into an <a>, which is what gives long-press/right-click "copy link", middle-click, the
// hover status bar, and a popup blocker that does not silently eat the navigation. target=_blank
// because this screen holds numbers the referrer has typed but not yet saved, plus their consent
// tick — navigating away to preview a link would discard all of it.
//
// RN's own Text types don't declare href (it is a react-native-web extension), hence the cast.
const webLinkProps = (url: string) =>
  Platform.OS === 'web'
    ? ({ href: url, hrefAttrs: { target: '_blank', rel: 'noopener noreferrer' } } as object)
    : null;

// Deliberate, disclosed exception to the design handbook's "no drop shadow on persistent
// surfaces" rule (§1.5/§2, same rule Toast.tsx cites) — this card is meant to read as a
// message bubble sitting on top of the screen, not a flat panel, so it gets real elevation.
const cardElevation = Platform.select({
  web: { boxShadow: '0px 12px 28px rgba(0,0,0,0.35), 0px 3px 8px rgba(0,0,0,0.22)' },
  default: {
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.32,
    shadowRadius: 18,
    elevation: 14,
  },
}) as Record<string, unknown>;

// White "chat bubble" card — deliberately breaks from the app's dark-surface convention so
// the invite message itself reads like a WhatsApp message the user is about to send: white
// fill, black text, a squared-off bottom-left corner suggesting a bubble tail, and real
// elevation (see cardElevation above) instead of the usual fill+radius-only lift.
export function CopyableMessageCard({ label, message, copyButtonLabel, onCopy, linkUrl }: Props) {
  // Split rather than regex-scan for URLs: the only link in this message is the one the caller
  // handed us, and a stray match on anything else would turn copy the referrer is meant to read
  // into something tappable. `before`/`after` keep the surrounding sentence intact, so the
  // rendered text stays character-for-character what the Copy button puts on the clipboard.
  const [before, after] = linkUrl && message.includes(linkUrl) ? message.split(linkUrl) : [message, null];

  return (
    <View style={[styles.card, cardElevation]}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.message}>
        {before}
        {after !== null && linkUrl ? (
          <>
            <Text
              style={styles.link}
              accessibilityRole="link"
              {...webLinkProps(linkUrl)}
              // Native has no anchor — the handler is the whole mechanism there, and would open
              // a second tab on top of the href if it also ran on web.
              onPress={Platform.OS === 'web' ? undefined : () => Linking.openURL(linkUrl).catch(() => {})}
            >
              {linkUrl}
            </Text>
            {after}
          </>
        ) : null}
      </Text>
      <Pressable
        onPress={onCopy}
        accessibilityRole="button"
        style={({ pressed }) => [styles.copyButton, pressed && styles.copyButtonPressed]}
      >
        <Text style={styles.copyButtonLabel}>{copyButtonLabel}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    borderBottomRightRadius: 18,
    borderBottomLeftRadius: 4, // bubble "tail" corner
    padding: spacing.unit,
    gap: 12,
  },
  label: {
    ...type.title4,
    color: 'rgba(23,26,29,0.55)', // black100 at reduced opacity — the light-surface mirror of white[60]
  },
  message: {
    ...type.body1,
    fontFamily: fontFamily.bodyBoldItalic,
    color: colors.base.black100,
  },
  link: {
    // The card's own body style is inherited; only the colour and underline change, so the link
    // sits in the sentence at the same weight rather than becoming a second visual element.
    // Secondary purple, not the primary orange — orange on white is the lowest-contrast pair in
    // the palette, and this is the one run of text a referrer may actually want to tap.
    color: colors.secondary[500],
    textDecorationLine: 'underline',
  },
  copyButton: {
    height: 48,
    borderRadius: radius.button,
    backgroundColor: colors.primary[500],
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.unit,
  },
  copyButtonPressed: {
    backgroundColor: colors.primary[800],
  },
  copyButtonLabel: {
    ...type.label1P,
    color: white[100],
  },
});
