// Copy rules from Eaze_design_handbook.md §4: sentence case, no exclamation marks,
// specific over hype, numbers read first.

export const referralCopy = {
  eyebrow: 'Refer a friend',
  headline: 'Invite a friend, earn coins',
  body: 'When your friend downloads Eaze with your link and makes their first recharge, you both get 50 coins.',
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
};

// `shareUrl` is a redirect (e.g. https://l.eaze.app/r/EAZE-XXXX) that logs the click server-side
// for funnel visibility, then forwards to the Play Store or App Store based on the visitor's
// device. It's just the download link now — attribution doesn't depend on it or on any code the
// friend would need to enter. The referrer already told us this friend's number; that's the
// entire attribution mechanism (see signup-match in eaze-referral-backend).
export function buildShareMessage(params: { shareUrl: string }): string {
  const { shareUrl } = params;
  return [
    "I'm on Eaze and it's worth your first recharge.",
    `Download the app and get 50 coins to start: ${shareUrl}`,
  ].join('\n');
}
