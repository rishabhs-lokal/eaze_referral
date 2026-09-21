import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, white, spacing, type } from '../theme';
import { EazeLogo } from '../components/EazeLogo';
import { GradientBackground } from '../components/GradientBackground';
import { CopyableMessageCard } from '../components/CopyableMessageCard';
import { PhoneNumberField } from '../components/PhoneNumberField';
import { PrimaryButton } from '../components/PrimaryButton';
import { TextButton } from '../components/TextButton';
import { Toast } from '../components/Toast';
import { referralCopy, buildShareMessage } from '../content/referral';
import { copyToClipboard } from '../platform/clipboard';
import { useReferrerId } from '../state/useReferrerId';
import { useToast } from '../state/useToast';
import { getPlatformKind } from '../state/platformKind';
import { fetchReferralCode, submitReferralIntents, logMessageCopy, ReferralCodeResponse } from '../api/referralApi';
import { toE164 } from '../state/phoneValidation';

// On an actual iOS/Android WebView this is always the full device width, so this only visibly
// caps and centers content when previewed on a wider desktop browser — the screen still reads
// like a native mobile card instead of stretching edge to edge.
const MAX_CONTENT_WIDTH = 480;

type PhoneField = { id: number; local: string; valid: boolean };

export function ReferralScreen() {
  const referrerStatus = useReferrerId();
  const referrerId = referrerStatus.status === 'ready' ? referrerStatus.userId : null;
  const { toast, showToast } = useToast();

  const [referralCode, setReferralCode] = useState<ReferralCodeResponse | null>(null);
  const [codeLoading, setCodeLoading] = useState(true);
  const [codeError, setCodeError] = useState(false);

  const nextFieldId = useRef(1);
  const [fields, setFields] = useState<PhoneField[]>([
    { id: 0, local: '', valid: false },
    { id: 1, local: '', valid: false },
  ]);
  const [attemptedSubmit, setAttemptedSubmit] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const platformKind = useRef(getPlatformKind()).current;

  const loadCode = useCallback(() => {
    if (!referrerId) return;
    setCodeLoading(true);
    setCodeError(false);
    fetchReferralCode(referrerId)
      .then((res) => setReferralCode(res))
      .catch(() => setCodeError(true))
      .finally(() => setCodeLoading(false));
  }, [referrerId]);

  useEffect(() => {
    if (referrerId) loadCode();
  }, [referrerId, loadCode]);

  const handleCopy = useCallback(async () => {
    if (!referralCode || !referrerId) return;
    const message = buildShareMessage({ shareUrl: referralCode.shareUrl });
    const ok = await copyToClipboard(message);
    showToast(ok ? 'success' : 'error', ok ? referralCopy.copiedToast : referralCopy.copyFailedToast);
    // Best-effort — the click count matters, but it should never block or fail the copy itself.
    logMessageCopy(referrerId).catch(() => {});
  }, [referralCode, referrerId, showToast]);

  const updateField = (id: number, local: string) => {
    setFields((prev) => prev.map((f) => (f.id === id ? { ...f, local } : f)));
  };

  const setFieldValidity = (id: number, valid: boolean) => {
    setFields((prev) => prev.map((f) => (f.id === id ? { ...f, valid } : f)));
  };

  const addField = () => {
    if (fields.length >= referralCopy.maxPhoneFields) return;
    nextFieldId.current += 1;
    setFields((prev) => [...prev, { id: nextFieldId.current, local: '', valid: false }]);
  };

  const removeField = (id: number) => {
    setFields((prev) => (prev.length <= 1 ? prev : prev.filter((f) => f.id !== id)));
  };

  const handleSubmit = async () => {
    if (!referrerId) return;
    setAttemptedSubmit(true);
    const allValid = fields.every((f) => f.valid);
    if (!allValid) return;

    setSubmitting(true);
    try {
      await submitReferralIntents({
        referrerUserId: referrerId,
        phoneNumbersE164: fields.map((f) => toE164(f.local)),
      });
      showToast('success', referralCopy.submitSuccessToast);
      const first = ++nextFieldId.current;
      const second = ++nextFieldId.current;
      setFields([
        { id: first, local: '', valid: false },
        { id: second, local: '', valid: false },
      ]);
      setAttemptedSubmit(false);
    } catch {
      showToast('error', referralCopy.submitFailedToast);
    } finally {
      setSubmitting(false);
    }
  };

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

  return (
    <SafeAreaView style={styles.safeArea} edges={['top', 'bottom', 'left', 'right']}>
      <GradientBackground />
      <ScrollView
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
            <View />
            <EazeLogo />
          </View>

          <View style={styles.hero}>
            <Text style={styles.eyebrow}>{referralCopy.eyebrow}</Text>
            <Text style={styles.headline}>{referralCopy.headline}</Text>
            <Text style={styles.body}>{referralCopy.body}</Text>
          </View>

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
              message={buildShareMessage({ shareUrl: referralCode.shareUrl })}
              copyButtonLabel={referralCopy.copyButton}
              onCopy={handleCopy}
            />
          ) : null}

          <View style={styles.phoneSection}>
            <Text style={styles.sectionTitle}>{referralCopy.phoneSectionTitle}</Text>
            <Text style={styles.sectionBody}>{referralCopy.phoneSectionBody}</Text>

            <View style={styles.phoneFieldsGroup}>
              {fields.map((field, index) => (
                <PhoneNumberField
                  key={field.id}
                  label={index === 0 ? "Friend's phone number" : `Friend's phone number ${index + 1}`}
                  value={field.local}
                  onChangeValue={(local) => updateField(field.id, local)}
                  onValidityChange={(valid) => setFieldValidity(field.id, valid)}
                  showErrorWhenEmpty={attemptedSubmit}
                  rightAccessory={
                    fields.length > 1 ? (
                      <TextButton label={referralCopy.removeNumber} tone="error" onPress={() => removeField(field.id)} />
                    ) : undefined
                  }
                />
              ))}
            </View>

            {fields.length < referralCopy.maxPhoneFields && (
              <TextButton label={referralCopy.addAnotherNumber} onPress={addField} />
            )}
          </View>

          <PrimaryButton label={referralCopy.submitButton} onPress={handleSubmit} loading={submitting} />
        </View>
      </ScrollView>

      {toast && (
        <View style={[styles.toastHost, Platform.OS === 'web' && styles.toastHostWeb, { pointerEvents: 'none' }]}>
          <Toast tone={toast.tone} message={toast.message} />
        </View>
      )}
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
