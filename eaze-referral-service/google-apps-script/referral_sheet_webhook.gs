// Mirrors accepted referrals — the referrer's decoded user_id and the phone number they
// referred — into a row of this spreadsheet. eaze-referral-service POSTs to this script's Web
// App URL, fire-and-forget, once per newly-accepted phone number (see
// app/services/sheets_webhook.py). This is a supplementary, human-readable view for anyone who
// wants to glance at referral activity without DB access — referral_intents in Postgres remains
// the actual source of truth for the reward pipeline.
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
const HEADER_ROW = ['Recorded At (script timezone)', 'Referrer User ID (decoded)', 'Phone Number Referred'];

function setupSheet() {
  const sheet = getOrCreateSheet();
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADER_ROW);
    sheet.getRange(1, 1, 1, HEADER_ROW.length).setFontWeight('bold');
  }
}

function getOrCreateSheet() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  return spreadsheet.getSheetByName(SHEET_NAME) || spreadsheet.insertSheet(SHEET_NAME);
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    const expectedSecret = PropertiesService.getScriptProperties().getProperty('WEBHOOK_SECRET');
    if (expectedSecret && body.secret !== expectedSecret) {
      return jsonResponse({ ok: false, error: 'invalid secret' });
    }
    if (!body.referrerUserId || !body.phoneE164) {
      return jsonResponse({ ok: false, error: 'referrerUserId and phoneE164 are required' });
    }

    setupSheet(); // no-op if the header row already exists
    getOrCreateSheet().appendRow([new Date(), body.referrerUserId, body.phoneE164]);

    return jsonResponse({ ok: true });
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err) });
  }
}

// Apps Script Web Apps always reply HTTP 200 at the transport level regardless of what the
// script itself decides — there's no API to set a custom status code — so the real outcome
// lives entirely in this JSON body's `ok` field. app/services/sheets_webhook.py checks `ok`,
// never the HTTP status, for exactly this reason.
function jsonResponse(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON);
}
