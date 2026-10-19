// Copy rules from Eaze_design_handbook.md §4: sentence case, no exclamation marks,
// specific over hype, numbers read first.

// The download link pasted into the invite message. A OneLink, so one URL resolves to the right
// store for whatever device the friend opens it on.
//
// This replaced the backend's own /r/{code} redirect, which logged a click per visit into
// referral_clicks. Nothing about the reward depends on the link — attribution is phone-only, and
// the friend never enters a code — so swapping it changes no payout behaviour. What it does cost
// is click analytics: referral_clicks will stop receiving rows, and the share-to-install funnel
// becomes OneLink's to report rather than ours.
export const DOWNLOAD_URL =
  process.env.EXPO_PUBLIC_DOWNLOAD_URL ?? 'https://eaze.onelink.me/x8qY/eirps9xf';

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
  submitButton: 'Add your friend',
  // Takes the count because a referrer can submit up to five at once, and because a sibling
  // number can be rejected as already-registered while the rest land — "friends added" after
  // exactly one went through would misreport what actually happened.
  submitSuccessToast: (saved: number) => (saved === 1 ? 'Friend added' : `${saved} friends added`),
  submitFailedToast: "Couldn't add your friend, try again",
  // Hard ceiling on how many fields can be on screen at once. The real limit is the referrer's
  // remaining allowance, which the API reports — this only stops the form growing past anything
  // anyone could ever submit, for the case where the cap is raised server-side.
  maxPhoneFields: 5,
  // The allowance, stated where it is about to bite rather than only in the Terms. Singular at
  // one left because "1 invites left" is the kind of thing people notice and nothing else is.
  invitesLeft: (left: number, limit: number) =>
    left === 1 ? `1 of ${limit} invites left` : `${left} of ${limit} invites left`,
  invitesExhaustedTitle: "You've used all your invites",
  invitesExhaustedBody: (limit: number) =>
    `You've referred ${limit} friends, which is the most this program allows. Your invite message still works for the friends you've already added — they just need to download Eaze and make their first recharge.`,
  missingLinkHeadline: 'Open this from the Eaze app',
  missingLinkBody: "This page only works when it's opened through the Refer a friend banner in Eaze.",
  backButtonLabel: 'Go back',
  termsButtonLabel: 'Terms and Conditions',
  termsTitle: 'Terms and Conditions',
  // Sits between the "Friend's Phone Number" label and the input, so it is read before a number
  // is typed rather than after.
  phoneDisclaimer:
    'Note: a phone number already referred by another user cannot be claimed again and will not be rewarded.',

  // The consent gate below the input. Must be ticked before anything can be saved — the
  // referrer is sharing someone else's phone number with Eaze, and that is their consent to
  // confirm, not something to infer from a button press. {{terms}} is rendered as an inline
  // link so the document is reachable from the sentence that references it.
  consentLabel:
    "By adding this number, you confirm you have your friend's permission to share it with Eaze. You also acknowledge and accept the {{terms}} governing the User Referral Programme.",
  consentTermsLinkLabel: 'Terms & Conditions',
  // Two messages, because the referrer can hit the gate at two different moments and each one
  // needs to name the next action: tapping a locked field, or pressing Save with nothing ticked.
  consentFirstToast: 'Tick the declaration below to add a number',
  consentRequiredToast: 'Please confirm the declaration before saving',
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
  // The three-referral cap is stated here in words, as legal text has to be. The enforced
  // number lives in MAX_REFERRALS_PER_USER on the service — raising it means editing this
  // sentence too, or the Terms will promise a limit the program no longer applies.
  {
    title: 'How Referrals Work',
    body: 'You take part by entering your friend’s phone number on the Referral Page, which can only be reached through the "Refer a friend" banner inside the Eaze App. A referral is created the moment you submit a valid, correctly-formatted number — there is no code or link your friend needs to enter. Each phone number can be claimed by only one referrer; if a number has already been submitted by someone else, your submission will not create a referral. You may refer a maximum of three phone numbers under this program. Once you have submitted three, no further numbers can be entered, and any additional number you attempt to submit will not create a referral and will not earn coins for you or for that person. A number that is not accepted — because it is already registered on Eaze App, because it has already been claimed by another referrer, or because it is not a valid mobile number — does not count towards this limit. Sharing the invitation message or the download link does not, by itself, create a referral: if a person installs Eaze App through your link but you did not submit their phone number on the Referral Page, no referral exists for them and no coins will be credited to you or to them. You may not refer your own phone number. Before any phone number can be entered, you must tick the declaration shown on the Referral Page; no number can be entered or submitted until you do. By ticking it you confirm that you have that person’s permission to share their phone number with Eaze App for the purpose of this referral program, and that you accept these Terms.',
  },
  {
    title: 'Verification',
    body: 'Eaze App may review a referral, a signup, or a recharge before crediting coins, particularly where activity appears unusual or automated. Eaze App may delay, decline, or reverse a coin credit pending this review. Decisions made under this section are final, subject to Eaze’s standard grievance redressal process.',
  },
  {
    title: 'Coin Crediting',
    body: 'Both coin rewards are credited only once your friend completes their first successful recharge on Eaze App using the exact phone number you submitted. Signing up alone does not trigger either reward — neither yours nor your friend\'s. Eaze App confirms the recharge against its own payment records before any coins are credited, so there may be a short delay between the recharge and the coins appearing. Each reward is credited once per referral; retried or duplicate requests will not result in double crediting.',
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
  alreadyRegistered: {
    eyebrow: 'Already on Eaze',
    title: 'That number has an Eaze account',
    // Deliberately specific about WHY, because the alternative reads as a bug: the referrer
    // typed a valid number, pressed Save, and nothing was saved. Naming the numbers lets them
    // see at a glance which one to replace when they entered several.
    bullets: [
      'The referral bonus is only for people new to Eaze, so this number was not saved.',
      'Try a friend who has not used Eaze before.',
    ],
    primaryLabel: 'Use a different number',
  },
  // Shown when a submission runs into the cap — either partially (some numbers saved, the rest
  // did not) or entirely. Names the numbers that did not save, for the same reason the
  // already-registered popup does: the referrer typed a valid number, pressed the button, and
  // has to be able to see which one did not land rather than inferring it from a count.
  limitReached: {
    eyebrow: 'Invite limit reached',
    title: 'You can refer up to {{limit}} friends',
    bullets: [
      'These numbers were not saved, and no coins can be earned for them:',
      'The friends you have already added are unaffected — they still earn you both coins when they recharge.',
    ],
    primaryLabel: 'Got it',
  },
  // Fires the moment the message reaches the clipboard — the last point at which the referrer
  // can still choose who to send it to. The whole programme turns on a fact the message itself
  // cannot carry: the link identifies nobody, so a recipient whose number was never submitted
  // is invisible to us no matter how they install. Stated in the same terms as T&C §2 rather
  // than softened, because the consequence is that nobody gets paid.
  shareWarning: {
    eyebrow: 'Before you send',
    title: 'The link on its own earns nothing',
    bullets: [
      'Coins are credited only for the numbers you have saved here. The link carries no record of who sent it.',
      `If someone installs Eaze through this message and you did not save their number first, neither of you receives the ${REWARD_COINS} coins.`,
      'Send it to the friends whose numbers you saved, and save any others before sharing with them.',
    ],
    primaryLabel: 'Understood',
    secondaryLabel: 'Add another number',
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

// Every referrer shares the same DOWNLOAD_URL — nothing about the reward is carried in the
// link. Attribution is phone-only: the referrer already told us their friend's number, and
// that is the entire mechanism (see signup-match in eaze-referral-service). The friend enters
// no code and the link identifies nobody.
export function buildShareMessage(): string {
  return [
    // Deliberately says nothing about how many invites the sender has. The previous opening
    // ("Eaze gives me three invites") hard-coded the cap into a string every user reads, which
    // made MAX_REFERRALS_PER_USER impossible to change without also changing this file and T&C
    // §2 in step. The Terms still state the limit, because that is where a limit belongs; the
    // message no longer has to.
    "Hey, I would love to invite you on Eaze.",
    // "once you make your first recharge" is the load-bearing phrase and must not be softened to
    // anything that reads as a signup bonus. Coins move only after a confirmed payment (T&C §4),
    // so a message promising them at install would have every new user wondering, correctly,
    // where their coins went. This string is what people actually read — long before the Terms.
    `You get ${REWARD_COINS} bonus coins once you make your first recharge. I've been on it for some time now and it's worth a try.`,
    `💰 Here you go: ${DOWNLOAD_URL}`,
    // Paragraphs are single lines joined by blank lines, never hard-wrapped mid-sentence: the
    // receiving chat app does its own wrapping, and baked-in line breaks that looked right at
    // one width turn into ragged half-lines at another.
  ].join('\n\n');
}
