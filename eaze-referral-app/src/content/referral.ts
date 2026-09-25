// Copy rules from Eaze_design_handbook.md §4: sentence case, no exclamation marks,
// specific over hype, numbers read first.

// EXPO_PUBLIC_* vars are inlined at build time — this is what makes the 1000-coin and 500-coin
// builds of this exact same codebase (see docker-compose.tier-*.yml / k8s/tier-*/ on the backend)
// show the right number without a code fork. There is no default/un-tiered build and therefore
// no fallback value — a missing or invalid EXPO_PUBLIC_REWARD_COINS fails loudly instead of
// silently shipping a made-up coin amount.
export const REWARD_COINS = Number(process.env.EXPO_PUBLIC_REWARD_COINS);
if (!Number.isFinite(REWARD_COINS) || REWARD_COINS <= 0) {
  throw new Error(
    'EXPO_PUBLIC_REWARD_COINS must be set to a positive number in .env — copy ' +
      '.env.tier-1000.example or .env.tier-500.example (there is no default tier).'
  );
}

export const referralCopy = {
  eyebrow: 'Refer a friend',
  headline: 'Invite a friend, earn coins',
  body: `When your friend downloads Eaze with your link and makes their first recharge, you both get ${REWARD_COINS} coins.`,
  messageCardLabel: 'Your invite message',
  copyButton: 'Copy message',
  copiedToast: 'Message copied',
  copyFailedToast: "Couldn't copy the message, try again",
  phoneSectionTitle: "Add your friend's number",
  phoneSectionBody: "We'll let you know the moment they join.",
  addAnotherNumber: '+  Add another number',
  removeNumber: 'Remove',
  submitButton: 'Save numbers',
  submitSuccessToast: 'Numbers saved',
  submitFailedToast: "Couldn't save your numbers, try again",
  maxPhoneFields: 5,
  missingLinkHeadline: 'Open this from the Eaze app',
  missingLinkBody: "This page only works when it's opened through the Refer a friend banner in Eaze.",
  backButtonLabel: 'Go back',
  termsButtonLabel: 'Terms and Conditions',
  termsTitle: 'Terms and Conditions',
  phoneDisclaimer:
    "Note: a phone number already referred by another user cannot be claimed again and will not be rewarded. By submitting a number, you acknowledge and accept the Terms and Conditions governing this referral program.",
};

// Terms and Conditions — same section pattern as eaze-level-up's TERMS_SECTIONS /
// renderTerms() (numbered title + body pairs rendered into a card). This is the actual
// legal text supplied for the program, not paraphrased copy — do not reword without
// updating the source document. `links` on a section is an optional map of inline
// citations; TermsScreen.tsx splits the body on `{{key}}` tokens and renders each as a
// tappable link via Linking.openURL.
export const termsDocumentTitle = 'Terms & Conditions – User Referral Program';

export const termsSections = [
  {
    title: 'Program Overview & Eligibility',
    body: 'This User Referral Program allows a registered Eaze App user to refer a new, unregistered Eaze App user, with both users receiving coins once the applicable conditions below are met. The referral bonus does not apply to a phone number already registered on Eaze App. By accessing the referral page linked from the Eaze App (the "Referral Page"), you accept these Terms, read together with Eaze App’s {{terms}} and {{privacy}}.',
    links: {
      terms: { label: 'Terms & Conditions', url: 'https://www.eazeapp.com/terms' },
      privacy: { label: 'Privacy Policy', url: 'https://www.eazeapp.com/privacypolicy' },
    },
  },
  {
    title: 'How Referrals Work',
    body: 'You take part by entering your friend’s phone number on the Referral Page, which can only be reached through the "Refer a friend" banner inside the Eaze App. A referral is created the moment you submit a valid, correctly-formatted number — there is no code or link your friend needs to enter. Each phone number can be claimed by only one referrer; if a number has already been submitted by someone else, your submission will not create a referral. You may not refer your own phone number. By submitting a friend’s phone number, you confirm that you have their permission to share it with Eaze App for the purpose of this referral program.',
  },
  {
    title: 'Verification',
    body: 'Eaze App may review a referral, a signup, or a recharge before crediting coins, particularly where activity appears unusual or automated. Eaze App may delay, decline, or reverse a coin credit pending this review. Decisions made under this section are final, subject to Eaze’s standard grievance redressal process.',
  },
  {
    title: 'Coin Crediting',
    body: 'The coin amount shown on the Referral Page is credited to your friend the moment they sign up on Eaze App using the exact phone number you submitted. Your own coin reward is credited only once your friend completes their first successful recharge on Eaze App — signing up alone does not trigger your reward. Each reward is credited once per referral; retried or duplicate requests will not result in double crediting.',
  },
  {
    title: 'Fair Play',
    body: 'Referring your own number, submitting a number without such person’s permission, using multiple or automated accounts, or attempting to trigger a reward without a genuine signup or recharge constitutes unfair practice. Eaze App may void the referral, reverse any credited coins, and take further action including temporary suspension or permanent blocking of your Eaze App account.',
  },
  {
    title: 'Program Changes',
    body: 'Eaze App reserves the right to modify, pause, or end this referral program, adjust the reward amount, or expire a pending referral at any time, with or without notice. Any such change will apply prospectively and will not affect coins already credited or referrals already completed at the time of the change.',
  },
  {
    title: 'Limitation of Liability',
    body: 'Eaze App is not liable for delays or failures in crediting coins caused by technical issues, third-party payment systems, or other causes beyond Eaze App’s reasonable control.',
  },
  {
    title: 'Governing Law',
    body: 'These Terms are governed by the laws of India, and courts in Bengaluru shall have exclusive jurisdiction over any dispute arising out of or in connection with this program.',
  },
];

// Copy for the three popups — Popup.tsx, wired from ReferralScreen.tsx.
export const popupCopy = {
  needsNumber: {
    eyebrow: 'Before you share',
    title: "Add your friend's number first",
    bullets: [
      `We can only pay out the ${REWARD_COINS} coins if we know whose signup to credit.`,
      'Add at least one number below, then come back to copy your message.',
    ],
    primaryLabel: 'Add a number',
  },
  invalidNumber: {
    eyebrow: 'Check the number',
    title: 'Enter a valid 10-digit number',
    bullets: [
      'Indian mobile numbers only — 10 digits, starting with 6-9.',
      'Every field needs a valid number before we can save.',
    ],
    primaryLabel: 'Fix it',
  },
  exitReminder: {
    eyebrow: "Don't leave yet",
    title: `Your friend could earn ${REWARD_COINS} coins`,
    bullets: [
      `You and your friend both get ${REWARD_COINS} coins once they sign up and recharge.`,
      "It only takes adding their number — you haven't added one yet.",
    ],
    primaryLabel: "Add their number",
    secondaryLabel: 'Exit anyway',
  },
};

// `shareUrl` is a redirect (e.g. https://l.eaze.app/r/EAZE-XXXX) that logs the click server-side
// for funnel visibility, then forwards to the Play Store or App Store based on the visitor's
// device. It's just the download link now — attribution doesn't depend on it or on any code the
// friend would need to enter. The referrer already told us this friend's number; that's the
// entire attribution mechanism (see signup-match in eaze-referral-backend).
export function buildShareMessage(params: { shareUrl: string }): string {
  const { shareUrl } = params;
  return [
    "I'm on Eaze 🎉 and it's worth your first recharge.",
    `💰 Download the app and get ${REWARD_COINS} coins to start: ${shareUrl}`,
    // Blank line between the two sentences — this is the literal string that gets copied
    // and shared, so the spacing carries over wherever it's pasted, not just in-app.
  ].join('\n\n');
}
