import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, white, spacing, type, fontFamily } from '../theme';
import { EazeLogo } from '../components/EazeLogo';
import { GradientBackground } from '../components/GradientBackground';
import { CopyableMessageCard } from '../components/CopyableMessageCard';
import { PhoneNumberField } from '../components/PhoneNumberField';
import { ConsentCheckbox } from '../components/ConsentCheckbox';
import { PrimaryButton } from '../components/PrimaryButton';
import { TextButton } from '../components/TextButton';
import { Toast } from '../components/Toast';
import { Popup } from '../components/Popup';
import { TermsScreen } from '../components/TermsScreen';
import { referralCopy, popupCopy, buildShareMessage, DOWNLOAD_URL } from '../content/referral';
import { copyToClipboard } from '../platform/clipboard';
import { useReferrerId } from '../state/useReferrerId';
import { useToast } from '../state/useToast';
import { getPlatformKind } from '../state/platformKind';
import { fetchReferralCode, submitReferralIntents, logMessageCopy, ReferralCodeResponse } from '../api/referralApi';
import { toE164 } from '../state/phoneValidation';

// This screen has no in-app navigation stack of its own — it's a single route opened via the
// Eaze app's banner link. On web (including this project's own Browser-pane testing) "leaving"
// is real browser history; on native/WebView there is no JS-reachable back action here at all —
// the host Eaze app owns the WebView chrome and its own back gesture. This only ever fires once
// the exit-intent popup (if shown) has been resolved.
function exitScreen() {
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    if (window.history.length > 1) {
      window.history.back();
    } else {
      window.close();
    }
  }
}

// On an actual iOS/Android WebView this is always the full device width, so this only visibly
// caps and centers content when previewed on a wider desktop browser — the screen still reads
// like a native mobile card instead of stretching edge to edge.
const MAX_CONTENT_WIDTH = 480;

// The headline has to hold one line. Measured in-browser, "Invite a friend, earn coins" set in
// Fraunces SemiBold costs ~12.4px of width per 1px of font size (395px at 32px), and the hero
// gets the viewport minus screenPadding on each side, capped at MAX_CONTENT_WIDTH. Picking a
// fixed size instead would mean choosing between wrapping on a 360dp phone and looking shrunken
// on everything wider, so it steps down only as far as the width actually forces.
const HEADLINE_WIDTH_PER_FONT_PX = 12.4;
const HEADLINE_SIZES = [32, 28, 24, 20];

function headlineTypeFor(viewportWidth: number) {
  const available = Math.min(viewportWidth, MAX_CONTENT_WIDTH) - spacing.screenPadding * 2;
  const fontSize =
    HEADLINE_SIZES.find((size) => size * HEADLINE_WIDTH_PER_FONT_PX <= available) ??
    HEADLINE_SIZES[HEADLINE_SIZES.length - 1];
  // 36/32 — headline1's own ratio, so the hero keeps its proportions at every step.
  return { fontSize, lineHeight: Math.round(fontSize * 1.125) };
}

type PhoneField = { id: number; local: string; valid: boolean };

export function ReferralScreen() {
  const { width: viewportWidth } = useWindowDimensions();
  const headlineType = headlineTypeFor(viewportWidth);
  const referrerStatus = useReferrerId();
  const referrerId = referrerStatus.status === 'ready' ? referrerStatus.userId : null;
  const { toast, showToast } = useToast();

  const [referralCode, setReferralCode] = useState<ReferralCodeResponse | null>(null);
  const [codeLoading, setCodeLoading] = useState(true);
  const [codeError, setCodeError] = useState(false);

  // The referrer's allowance. Server-owned on purpose: it is a per-person running total that
  // survives across sessions and devices, so there is nothing on this page it could be derived
  // from. `limit` stays null until the first load answers, and every branch below treats null
  // as "not known yet" rather than as zero — guessing zero would show someone the exhausted
  // state for a few hundred milliseconds before correcting itself.
  const [referralsUsed, setReferralsUsed] = useState(0);
  const [referralsLimit, setReferralsLimit] = useState<number | null>(null);
  const referralsLeft = referralsLimit === null ? null : Math.max(0, referralsLimit - referralsUsed);
  const outOfInvites = referralsLeft === 0;
  const maxFields = Math.min(referralCopy.maxPhoneFields, referralsLeft ?? referralCopy.maxPhoneFields);

  const nextFieldId = useRef(0);
  const [fields, setFields] = useState<PhoneField[]>([{ id: 0, local: '', valid: false }]);
  const [attemptedSubmit, setAttemptedSubmit] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const platformKind = useRef(getPlatformKind()).current;
  const scrollRef = useRef<ScrollView>(null);

  // Whether the referrer has ever successfully registered a friend's number with the backend
  // this session — the gate for copying/sharing the message and for leaving without a nudge.
  // Attribution is phone-only (see REFERRAL_PROGRAM_PLAN.md), so sharing before this is true
  // would produce a link that can never actually credit anyone.
  const [hasSavedNumbers, setHasSavedNumbers] = useState(false);
  const [showNeedsNumberPopup, setShowNeedsNumberPopup] = useState(false);
  const [showInvalidNumberPopup, setShowInvalidNumberPopup] = useState(false);
  const [consentGiven, setConsentGiven] = useState(false);
  const [showConsentError, setShowConsentError] = useState(false);
  const [showAlreadyRegisteredPopup, setShowAlreadyRegisteredPopup] = useState(false);
  const [alreadyRegisteredNumbers, setAlreadyRegisteredNumbers] = useState<string[]>([]);
  const [showShareWarningPopup, setShowShareWarningPopup] = useState(false);
  const [showLimitReachedPopup, setShowLimitReachedPopup] = useState(false);
  const [limitRejectedNumbers, setLimitRejectedNumbers] = useState<string[]>([]);
  // Once per session. The warning has to land before the first paste, but a referrer copying a
  // second time has already read it, and a dialog on every copy would be dismissed unread —
  // which is the state we are trying to avoid.
  const shareWarningSeen = useRef(false);
  const [showExitPopup, setShowExitPopup] = useState(false);
  const [showTerms, setShowTerms] = useState(false);

  const scrollToPhoneSection = useCallback(() => {
    // The phone section is the first thing under the hero now, so scrolling to the top
    // surfaces it without needing per-field layout measurement.
    scrollRef.current?.scrollTo({ y: 0, animated: true });
  }, []);

  const loadCode = useCallback(() => {
    if (!referrerId) return;
    setCodeLoading(true);
    setCodeError(false);
    fetchReferralCode(referrerId)
      .then((res) => {
        setReferralCode(res);
        setReferralsUsed(res.referralsUsed);
        setReferralsLimit(res.referralsLimit);
        // hasSavedNumbers gates the Copy button, and it used to start false on every visit —
        // so a referrer who added numbers yesterday came back today and was told to add one
        // before they could copy their own message. Harmless-looking until the cap existed;
        // now someone who has used all their invites could never copy a message again, because
        // the only thing that flipped this was a save they are no longer allowed to make.
        if (res.referralsUsed > 0) setHasSavedNumbers(true);
      })
      .catch(() => setCodeError(true))
      .finally(() => setCodeLoading(false));
  }, [referrerId]);

  useEffect(() => {
    if (referrerId) loadCode();
  }, [referrerId, loadCode]);

  const handleCopy = useCallback(async () => {
    if (!referralCode || !referrerId) return;
    if (!hasSavedNumbers) {
      setShowNeedsNumberPopup(true);
      return;
    }
    const message = buildShareMessage();
    const ok = await copyToClipboard(message);
    showToast(ok ? 'success' : 'error', ok ? referralCopy.copiedToast : referralCopy.copyFailedToast);
    // Only after a copy that actually succeeded — warning someone about a message they do not
    // have would be noise.
    if (ok && !shareWarningSeen.current) {
      shareWarningSeen.current = true;
      setShowShareWarningPopup(true);
    }
    // Best-effort — the click count matters, but it should never block or fail the copy itself.
    logMessageCopy(referrerId).catch(() => {});
  }, [referralCode, referrerId, showToast, hasSavedNumbers]);

  // Consent comes first: until the declaration is ticked there is nothing to type a number
  // into. Silence would read as a broken field, so every blocked touch says why and points at
  // the checkbox that unblocks it.
  const notifyConsentFirst = useCallback(() => {
    setShowConsentError(true);
    showToast('error', referralCopy.consentFirstToast);
  }, [showToast]);

  const updateField = (id: number, local: string) => {
    setFields((prev) => prev.map((f) => (f.id === id ? { ...f, local } : f)));
  };

  const setFieldValidity = (id: number, valid: boolean) => {
    setFields((prev) => prev.map((f) => (f.id === id ? { ...f, valid } : f)));
  };

  const addField = () => {
    if (fields.length >= maxFields) return;
    nextFieldId.current += 1;
    setFields((prev) => [...prev, { id: nextFieldId.current, local: '', valid: false }]);
  };

  const removeField = (id: number) => {
    setFields((prev) => (prev.length <= 1 ? prev : prev.filter((f) => f.id !== id)));
  };

  const handleSubmit = async () => {
    if (!referrerId) return;
    setAttemptedSubmit(true);

    // The declaration gates everything. Checked before format validation so a referrer who has
    // not consented is told that first, rather than being walked through fixing a number for a
    // submission that was never going to be allowed.
    if (!consentGiven) {
      setShowConsentError(true);
      showToast('error', referralCopy.consentRequiredToast);
      return;
    }

    // Every visible field is mandatory now (one by default; any extra ones only exist
    // because the user tapped "Add another number") — fill it in or remove it.
    const allValid = fields.every((f) => f.valid);
    if (!allValid) {
      setShowInvalidNumberPopup(true);
      return;
    }

    setSubmitting(true);
    try {
      const result = await submitReferralIntents({
        referrerUserId: referrerId,
        phoneNumbersE164: fields.map((f) => toE164(f.local)),
      });

      // The backend checks each number against Eaze's real user base before saving. A number
      // that already has an account can never earn anyone coins, so it isn't saved — and
      // saying so here is the only chance the referrer gets to use a different number. Without
      // this they'd see a success toast for numbers that were silently dropped.
      const alreadyOnEaze = result.skipped
        .filter((s) => s.reason === 'already_registered')
        .map((s) => s.phone);

      if (alreadyOnEaze.length > 0) {
        setAlreadyRegisteredNumbers(alreadyOnEaze);
        setShowAlreadyRegisteredPopup(true);
      }

      // The server is the authority on the allowance — it counts inside the same locked
      // transaction that just wrote. Taking its word rather than decrementing locally keeps
      // this correct when a sibling number was rejected, or when the same referrer has the
      // page open twice.
      setReferralsUsed(result.referralsUsed);
      setReferralsLimit(result.referralsLimit);

      // Reachable even though the form caps its own field count: another tab, a stale page
      // loaded before an earlier save, or a referrer who was already over the limit when it
      // was introduced. Whatever the route, these numbers did not save and saying so is the
      // only way they find out.
      const overLimit = result.skipped
        .filter((s) => s.reason === 'referral_limit_reached')
        .map((s) => s.phone);

      if (overLimit.length > 0) {
        setLimitRejectedNumbers(overLimit);
        setShowLimitReachedPopup(true);
      }

      // Anything that did save is still a success, even if a sibling number was rejected —
      // only clear the fields and congratulate them when something actually landed.
      if (result.saved > 0) {
        setHasSavedNumbers(true);
        showToast('success', referralCopy.submitSuccessToast(result.saved));
        setFields([{ id: ++nextFieldId.current, local: '', valid: false }]);
        setAttemptedSubmit(false);
      }
    } catch {
      showToast('error', referralCopy.submitFailedToast);
    } finally {
      setSubmitting(false);
    }
  };

  const handleBack = useCallback(() => {
    if (!hasSavedNumbers) {
      setShowExitPopup(true);
      return;
    }
    exitScreen();
  }, [hasSavedNumbers]);

  if (referrerStatus.status === 'loading') {
    return (
      <SafeAreaView style={styles.safeArea} edges={['top', 'bottom', 'left', 'right']}>
        <GradientBackground />
        <View style={styles.centerFill}>
          <ActivityIndicator color={colors.primary[500]} />
        </View>
      </SafeAreaView>
    );
  }

  if (referrerStatus.status === 'missing') {
    return (
      <SafeAreaView style={styles.safeArea} edges={['top', 'bottom', 'left', 'right']}>
        <GradientBackground />
        <View style={styles.scrollContent}>
          <View style={styles.contentMaxWidth}>
            <View style={styles.header}>
              <View />
              <EazeLogo />
            </View>
            <View style={styles.hero}>
              <Text style={styles.headline}>{referralCopy.missingLinkHeadline}</Text>
              <Text style={styles.body}>{referralCopy.missingLinkBody}</Text>
            </View>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  if (showTerms) {
    return <TermsScreen onBack={() => setShowTerms(false)} />;
  }

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'bottom', 'left', 'right']}>
      <GradientBackground />
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View
          style={[
            styles.contentMaxWidth,
            { paddingBottom: platformKind === 'android' ? spacing.screenPadding + 8 : spacing.screenPadding },
          ]}
        >
          <View style={styles.header}>
            <Pressable
              onPress={handleBack}
              accessibilityRole="button"
              accessibilityLabel={referralCopy.backButtonLabel}
              hitSlop={8}
              style={styles.backButton}
            >
              <Text style={styles.backButtonGlyph}>{'←'}</Text>
            </Pressable>
            <EazeLogo />
          </View>

          <View style={styles.hero}>
            <Text style={styles.eyebrow}>{referralCopy.eyebrow}</Text>
            <Text style={[styles.headline, headlineType]} numberOfLines={1} adjustsFontSizeToFit>
              {referralCopy.headline}
            </Text>
            <Text style={styles.body}>{referralCopy.body}</Text>
          </View>

          {outOfInvites ? (
            // Everything that could add a referral goes away rather than being disabled — a
            // dead form invites repeated attempts at something that cannot succeed. The invite
            // card below deliberately stays: the friends already added still have to install
            // and recharge, and this message is what gets them there.
            <View style={styles.exhaustedCard}>
              <Text style={styles.sectionTitle}>{referralCopy.invitesExhaustedTitle}</Text>
              <Text style={styles.exhaustedBody}>
                {referralCopy.invitesExhaustedBody(referralsLimit ?? 0)}
              </Text>
            </View>
          ) : (
          <View style={styles.phoneSection}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>{referralCopy.phoneSectionTitle}</Text>
              {referralsLeft !== null && referralsLimit !== null && (
                <Text style={styles.invitesLeft}>
                  {referralCopy.invitesLeft(referralsLeft, referralsLimit)}
                </Text>
              )}
            </View>
            <Text style={styles.sectionBody}>{referralCopy.phoneSectionBody}</Text>

            <View style={styles.phoneFieldsGroup}>
              {fields.map((field, index) => (
                <PhoneNumberField
                  key={field.id}
                  label={index === 0 ? "Friend's Phone Number" : `Friend's Phone Number ${index + 1}`}
                  note={index === 0 ? referralCopy.phoneDisclaimer : undefined}
                  value={field.local}
                  onChangeValue={(local) => updateField(field.id, local)}
                  onValidityChange={(valid) => setFieldValidity(field.id, valid)}
                  showErrorWhenEmpty={attemptedSubmit}
                  required
                  locked={!consentGiven}
                  onLockedPress={notifyConsentFirst}
                  rightAccessory={
                    fields.length > 1 ? (
                      <TextButton label={referralCopy.removeNumber} tone="error" onPress={() => removeField(field.id)} />
                    ) : undefined
                  }
                />
              ))}
            </View>

            <ConsentCheckbox
              checked={consentGiven}
              onChange={(next) => {
                setConsentGiven(next);
                if (next) setShowConsentError(false);
              }}
              label={referralCopy.consentLabel}
              termsLabel={referralCopy.consentTermsLinkLabel}
              onPressTerms={() => setShowTerms(true)}
              showError={showConsentError}
            />

            {fields.length < maxFields && (
              <TextButton
                label={referralCopy.addAnotherNumber}
                onPress={consentGiven ? addField : notifyConsentFirst}
              />
            )}

            <PrimaryButton label={referralCopy.submitButton} onPress={handleSubmit} loading={submitting} />
          </View>
          )}

          {codeLoading ? (
            <View style={styles.codeLoading}>
              <ActivityIndicator color={colors.primary[500]} />
            </View>
          ) : codeError ? (
            <View style={styles.codeError}>
              <Text style={styles.codeErrorText}>Couldn't load your invite link</Text>
              <TextButton label="Retry" onPress={loadCode} />
            </View>
          ) : referralCode ? (
            <CopyableMessageCard
              label={referralCopy.messageCardLabel}
              message={buildShareMessage()}
              linkUrl={DOWNLOAD_URL}
              copyButtonLabel={referralCopy.copyButton}
              onCopy={handleCopy}
            />
          ) : null}

          <View style={styles.termsRow}>
            <TextButton
              label={referralCopy.termsButtonLabel}
              onPress={() => setShowTerms(true)}
              tone="muted"
              centered
            />
          </View>
        </View>
      </ScrollView>

      {toast && (
        <View style={[styles.toastHost, Platform.OS === 'web' && styles.toastHostWeb, { pointerEvents: 'none' }]}>
          <Toast tone={toast.tone} message={toast.message} />
        </View>
      )}

      <Popup
        visible={showNeedsNumberPopup}
        onClose={() => setShowNeedsNumberPopup(false)}
        eyebrow={popupCopy.needsNumber.eyebrow}
        title={popupCopy.needsNumber.title}
        bullets={popupCopy.needsNumber.bullets}
        primaryLabel={popupCopy.needsNumber.primaryLabel}
        onPrimary={() => {
          setShowNeedsNumberPopup(false);
          scrollToPhoneSection();
        }}
      />

      <Popup
        visible={showShareWarningPopup}
        onClose={() => setShowShareWarningPopup(false)}
        eyebrow={popupCopy.shareWarning.eyebrow}
        title={popupCopy.shareWarning.title}
        bullets={popupCopy.shareWarning.bullets}
        primaryLabel={popupCopy.shareWarning.primaryLabel}
        onPrimary={() => setShowShareWarningPopup(false)}
        // "Add another number" is only an offer while there is a number to add. Shown to
        // someone who has spent all three it scrolls them to a section that is no longer on the
        // page — an action that visibly does nothing, on the one dialog whose whole purpose is
        // to be believed.
        secondaryLabel={outOfInvites ? undefined : popupCopy.shareWarning.secondaryLabel}
        onSecondary={
          outOfInvites
            ? undefined
            : () => {
                setShowShareWarningPopup(false);
                scrollToPhoneSection();
              }
        }
      />

      <Popup
        visible={showInvalidNumberPopup}
        onClose={() => setShowInvalidNumberPopup(false)}
        eyebrow={popupCopy.invalidNumber.eyebrow}
        title={popupCopy.invalidNumber.title}
        bullets={popupCopy.invalidNumber.bullets}
        primaryLabel={popupCopy.invalidNumber.primaryLabel}
        onPrimary={() => {
          setShowInvalidNumberPopup(false);
          scrollToPhoneSection();
        }}
      />

      <Popup
        visible={showAlreadyRegisteredPopup}
        onClose={() => setShowAlreadyRegisteredPopup(false)}
        eyebrow={popupCopy.alreadyRegistered.eyebrow}
        title={popupCopy.alreadyRegistered.title}
        // The rejected numbers lead, so a referrer who entered several can see at a glance
        // which one to replace.
        bullets={[alreadyRegisteredNumbers.join(', '), ...popupCopy.alreadyRegistered.bullets]}
        primaryLabel={popupCopy.alreadyRegistered.primaryLabel}
        onPrimary={() => {
          setShowAlreadyRegisteredPopup(false);
          scrollToPhoneSection();
        }}
      />

      <Popup
        visible={showLimitReachedPopup}
        onClose={() => setShowLimitReachedPopup(false)}
        eyebrow={popupCopy.limitReached.eyebrow}
        title={popupCopy.limitReached.title.replace('{{limit}}', String(referralsLimit ?? ''))}
        // The rejected numbers sit between the two lines rather than at the top, so the
        // sentence that introduces them is read first.
        bullets={[
          popupCopy.limitReached.bullets[0],
          limitRejectedNumbers.join(', '),
          popupCopy.limitReached.bullets[1],
        ]}
        primaryLabel={popupCopy.limitReached.primaryLabel}
        onPrimary={() => setShowLimitReachedPopup(false)}
      />

      <Popup
        visible={showExitPopup}
        onClose={() => setShowExitPopup(false)}
        eyebrow={popupCopy.exitReminder.eyebrow}
        title={popupCopy.exitReminder.title}
        bullets={popupCopy.exitReminder.bullets}
        primaryLabel={popupCopy.exitReminder.primaryLabel}
        onPrimary={() => {
          setShowExitPopup(false);
          scrollToPhoneSection();
        }}
        secondaryLabel={popupCopy.exitReminder.secondaryLabel}
        onSecondary={() => {
          setShowExitPopup(false);
          exitScreen();
        }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: 'transparent', // GradientBackground owns the fill
  },
  scrollContent: {
    flexGrow: 1,
    width: '100%', // without this the content container shrinks to its children's intrinsic
    // width instead of the ScrollView's full width, and alignItems below has nothing to center within
    alignItems: 'center', // centers contentMaxWidth when the viewport is wider than a phone
  },
  contentMaxWidth: {
    width: '100%',
    maxWidth: MAX_CONTENT_WIDTH,
    paddingHorizontal: spacing.screenPadding,
    paddingTop: spacing.screenPadding,
    gap: 28,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
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
  hero: {
    gap: 10,
  },
  eyebrow: {
    ...type.title4,
    color: white[60],
  },
  headline: {
    ...type.headline1,
    color: white[100],
  },
  body: {
    ...type.body1,
    color: white[80],
  },
  centerFill: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  codeLoading: {
    height: 96,
    alignItems: 'center',
    justifyContent: 'center',
  },
  codeError: {
    gap: 4,
  },
  codeErrorText: {
    ...type.body2,
    color: colors.error[500],
  },
  phoneSection: {
    gap: 16,
  },
  exhaustedCard: {
    gap: 8,
    padding: 16,
    borderRadius: 16,
    backgroundColor: white[10],
  },
  // Not sectionBody: that one carries marginTop: -8 to tuck under a section title in the form
  // layout, which here cancels the card's own gap and jams the two lines together.
  exhaustedBody: {
    ...type.body2,
    color: white[60],
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: 8,
  },
  invitesLeft: {
    ...type.body3,
    color: white[60],
  },
  sectionTitle: {
    ...type.title3,
    color: white[100],
  },
  sectionBody: {
    ...type.body2,
    color: white[60],
    marginTop: -8,
  },
  phoneFieldsGroup: {
    gap: 12,
  },
  termsRow: {
    alignItems: 'center',
  },
  toastHost: {
    position: 'absolute',
    bottom: 24,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  toastHostWeb: {
    // @ts-expect-error web-only CSS position value, harmless on native
    position: 'fixed',
  },
});
