// Live mirror of the referral pipeline in a Google Sheet: one row per referred phone number,
// updated as that number moves through verification and payout. eaze-referral-service POSTs to
// this script's Web App URL (see app/services/sheets_webhook.py) — fire-and-forget, so nothing
// here can ever block or fail a referral. referral_verifications in Postgres remains the actual
// source of truth for the reward pipeline; this is the human-readable view of it.
//
// Three actions, all POSTed as JSON with the shared secret:
//   {action: "append",  referrerUserId, phoneE164}          -> add a row when a referral is made
//   {action: "update",  phoneE164, verification?, payment?,  -> advance that row's status
//                       friendCoins?, referrerCoins?}
//   {action: "list",    onlyVerified?}                      -> pull the phone numbers back out
// An omitted action defaults to "append", so older callers keep working unchanged.
//
// One-time setup:
//   1. Create a new Google Sheet (or open the one you want rows appended to).
//   2. Extensions -> Apps Script. Delete anything in Code.gs and paste this whole file in.
//      Use line comments (like this one), not /* */ block comments, if you retype any of this
//      by hand — the Apps Script editor auto-closes /* with a */ as you type, which silently
//      corrupts a pasted block comment (confirmed the hard way deploying this exact script).
//   3. Project Settings (gear icon) -> Script Properties -> add a property named
//      WEBHOOK_SECRET with a value you make up (a random string). This must match the
//      GOOGLE_SHEETS_WEBHOOK_SECRET env var on the backend, or requests are rejected.
//   4. Run the `setupSheet` function once from the Apps Script editor (Run -> setupSheet) to
//      write the header row and grant the script permission to edit this spreadsheet.
//   5. Deploy -> New deployment -> type "Web app". Execute as: Me. Who has access: Anyone.
//      Deploy, then copy the Web app URL it gives you.
//   6. Set that URL as GOOGLE_SHEETS_WEBHOOK_URL on the backend (see .env.tier-*.example) and
//      the same secret from step 3 as GOOGLE_SHEETS_WEBHOOK_SECRET. Restart the backend.
//   7. Whenever you edit this script, you must create a NEW deployment version (Deploy -> Manage
//      deployments -> Edit -> New version) for the change to actually take effect at the
//      existing URL — saving the file alone does not update a live Web App deployment.

const SHEET_NAME = 'Referrals';
const HEADER_ROW = [
  'Recorded At (script timezone)',
  'Referrer User ID (decoded)',
  'Phone Number Referred',
  'Verification',
  'Payment',
  "Friend's Coins",
  "Referrer's Coins",
  'Last Updated',
];

// 1-based column positions, matching HEADER_ROW above.
const COL_PHONE = 3;
const COL_VERIFICATION = 4;
const COL_PAYMENT = 5;
const COL_FRIEND_COINS = 6;
const COL_REFERRER_COINS = 7;
const COL_UPDATED = 8;

function setupSheet() {
  const sheet = getOrCreateSheet();
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADER_ROW);
    sheet.getRange(1, 1, 1, HEADER_ROW.length).setFontWeight('bold');
    sheet.setFrozenRows(1);
  }
}

function getOrCreateSheet() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  return spreadsheet.getSheetByName(SHEET_NAME) || spreadsheet.insertSheet(SHEET_NAME);
}

// Row number for a phone, or -1. Linear scan of one column — fine at this scale, and it avoids
// keeping a separate index that could drift out of sync with hand edits to the sheet.
function findRowByPhone(sheet, phoneE164) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return -1;
  const phones = sheet.getRange(2, COL_PHONE, lastRow - 1, 1).getValues();
  for (let i = 0; i < phones.length; i++) {
    if (String(phones[i][0]).trim() === String(phoneE164).trim()) return i + 2;
  }
  return -1;
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    const expectedSecret = PropertiesService.getScriptProperties().getProperty('WEBHOOK_SECRET');
    if (expectedSecret && body.secret !== expectedSecret) {
      return jsonResponse({ ok: false, error: 'invalid secret' });
    }

    const action = body.action || 'append';
    if (action === 'append') return handleAppend(body);
    if (action === 'update') return handleUpdate(body);
    if (action === 'list') return handleList(body);
    return jsonResponse({ ok: false, error: 'unknown action: ' + action });
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err) });
  }
}

function handleAppend(body) {
  if (!body.referrerUserId || !body.phoneE164) {
    return jsonResponse({ ok: false, error: 'referrerUserId and phoneE164 are required' });
  }
  setupSheet(); // no-op if the header row already exists
  const sheet = getOrCreateSheet();

  // Re-submitting a number that's already here must not create a duplicate row — the sheet is
  // a mirror of one-row-per-number, same as referral_intents' own uniqueness.
  if (findRowByPhone(sheet, body.phoneE164) !== -1) {
    return jsonResponse({ ok: true, duplicate: true });
  }

  const now = new Date();
  sheet.appendRow([
    now,
    body.referrerUserId,
    body.phoneE164,
    'Awaiting check',
    'Pending',
    'Pending',
    'Pending',
    now,
  ]);

  // Force the phone column to plain text. Sheets otherwise coerces "+919876543210" into the
  // number 919876543210 and drops the plus, so the value read back no longer matches the
  // phone_e164 the backend stores — which would silently narrow every reconcile pass to zero
  // rows. Set after appendRow because the coercion happens on write.
  const row = sheet.getLastRow();
  sheet.getRange(row, COL_PHONE).setNumberFormat('@').setValue(String(body.phoneE164));

  return jsonResponse({ ok: true });
}

// Advances an existing row. Every status field is optional — the backend sends only what it
// just learned, so a verification update doesn't clobber payout columns and vice versa.
function handleUpdate(body) {
  if (!body.phoneE164) {
    return jsonResponse({ ok: false, error: 'phoneE164 is required' });
  }
  const sheet = getOrCreateSheet();
  const row = findRowByPhone(sheet, body.phoneE164);
  if (row === -1) {
    return jsonResponse({ ok: false, error: 'phone not found in sheet' });
  }

  if (body.verification) sheet.getRange(row, COL_VERIFICATION).setValue(body.verification);
  if (body.payment) sheet.getRange(row, COL_PAYMENT).setValue(body.payment);
  if (body.friendCoins) sheet.getRange(row, COL_FRIEND_COINS).setValue(body.friendCoins);
  if (body.referrerCoins) sheet.getRange(row, COL_REFERRER_COINS).setValue(body.referrerCoins);
  sheet.getRange(row, COL_UPDATED).setValue(new Date());

  return jsonResponse({ ok: true, row: row });
}

// Pull the phone numbers back out of the sheet. `onlyVerified` limits it to numbers that passed
// the pre-existing-user check, which is the set still eligible to earn coins.
function handleList(body) {
  const sheet = getOrCreateSheet();
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return jsonResponse({ ok: true, count: 0, rows: [] });

  const values = sheet.getRange(2, 1, lastRow - 1, HEADER_ROW.length).getValues();
  const rows = [];
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (body.onlyVerified && String(v[COL_VERIFICATION - 1]) !== 'Verified') continue;
    rows.push({
      referrerUserId: v[1],
      phoneE164: v[2],
      verification: v[COL_VERIFICATION - 1],
      payment: v[COL_PAYMENT - 1],
      friendCoins: v[COL_FRIEND_COINS - 1],
      referrerCoins: v[COL_REFERRER_COINS - 1],
    });
  }
  return jsonResponse({ ok: true, count: rows.length, rows: rows });
}

// Apps Script Web Apps always reply HTTP 200 at the transport level regardless of what the
// script itself decides — there's no API to set a custom status code — so the real outcome
// lives entirely in this JSON body's `ok` field. app/services/sheets_webhook.py checks `ok`,
// never the HTTP status, for exactly this reason.
function jsonResponse(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON);
}
