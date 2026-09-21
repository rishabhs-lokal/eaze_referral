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
cp .env.example .env   # point EXPO_PUBLIC_API_BASE_URL at eaze-referral-service
npm run web             # or: npx expo start --web
```

Open `http://localhost:8081/?user_id=<base64>` — `user_id` is the real Eaze user id,
base64-encoded, exactly as the in-app banner's generated URL will carry it (see
`src/state/useReferrerId.ts`). **There is no fallback.** A user can only ever reach this screen
via a link the Eaze app itself generated; a missing `user_id` shows a blocking "open this from
the Eaze app" screen instead of the referral form.

The base64 **decode happens on the backend**, not here (`eaze-referral-service/app/services/identity.py`)
— this screen just extracts the raw param from the URL and passes it straight through on every
API call, unmodified. Centralizing the decode server-side means any future caller (a native
client, direct API use) gets the same normalization for free, and the backend is the one place
that ever needs to change if the encoding scheme changes.

To build a test URL locally:

```bash
python3 -c "import base64; print(base64.b64encode(b'some-user-id').decode())"
# → http://localhost:8081/?user_id=<output>
```

Every load of this screen (i.e. every call to `GET /api/referral/code/:userId`) records a
first-seen login in the backend's `login_logs` table — one row per user_id, timestamped on their
first visit only, never updated on later visits. Every "Copy message" tap and every phone number
submitted are also logged server-side (`message_copy_logs`, `referral_logs`) — see the backend's
README for details.

## Deviations from the design handbook, disclosed

- **Headline font**: the handbook specifies "Fraunces 144pt SuperSoft" (the `opsz=144, SOFT=100`
  instance of the variable font). No static build of that exact instance is published, and React
  Native can't apply CSS `font-variation-settings` to reach a variable axis at runtime. Substituted
  `Fraunces_600SemiBold` (see `src/theme/typography.ts`) — swap it the moment the real font file
  is available.

## Known gap

Android's Play Install Referrer capture and the iOS manual-code-entry fallback (for the case
where the friend taps the store link directly, rather than the referrer pre-registering their
number) aren't wired here — that requires the actual native Eaze app repo. `/r/:code` on the
backend already logs the click and passes `?referrer=<code>` through to the store link, so
wiring up Install Referrer later is a drop-in.
