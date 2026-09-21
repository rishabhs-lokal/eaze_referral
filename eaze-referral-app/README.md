# eaze-referral-app

The referral landing screen a user sees after tapping the in-app "Refer a friend" banner.
Expo + React Native + TypeScript, React Native Web for browser, Android as the native target —
per the shared-architecture rules in `REACT_NATIVE_WEB_HARNESS.md` (this app follows that file's
stack/layout conventions; it does not build "Aperture", the unrelated demo brief in that file).
Visual system is `Eaze_design_handbook.md`.

## What's in this screen

- Eaze mark, top right.
- A catchy, sentence-case invite message in a copyable card — one tap copies it (with a web
  `execCommand` fallback for browser contexts that deny the Clipboard API).
- A mandatory "add your friend's phone number" form: +91-prefixed fields, up to 5, client-side
  validated against the Indian mobile format, submitted to the backend.

## Setup

```bash
npm install
cp .env.example .env   # point EXPO_PUBLIC_API_BASE_URL at eaze-referral-backend
npm run web             # or: npx expo start --web
```

Open `http://localhost:8081/?ref=<referrerId>` — the `ref` query param stands in for the
signed-token auth handoff the real banner→webapp flow will eventually pass (see the TODO in
`src/state/useReferrerId.ts`). Without it, the screen falls back to a `demo-referrer` id so it's
still viewable standalone.

## Deviations from the design handbook, disclosed

- **Headline font**: the handbook specifies "Fraunces 144pt SuperSoft" (the `opsz=144, SOFT=100`
  instance of the variable font). No static build of that exact instance is published, and React
  Native can't apply CSS `font-variation-settings` to reach a variable axis at runtime. Substituted
  `Fraunces_600SemiBold` (see `src/theme/typography.ts`) — swap it the moment the real font file
  is available.
- **Eaze mark**: no logo asset was supplied, so the top-right mark is a placeholder monogram
  (`src/components/EazeLogo.tsx`), not the real logo.

## Known gap

Android's Play Install Referrer capture and the iOS manual-code-entry fallback (for the case
where the friend taps the store link directly, rather than the referrer pre-registering their
number) aren't wired here — that requires the actual native Eaze app repo. `/r/:code` on the
backend already logs the click and passes `?referrer=<code>` through to the store link, so
wiring up Install Referrer later is a drop-in.
