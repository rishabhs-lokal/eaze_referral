/**
 * Mirrors accepted referrals — the referrer's decoded user_id and the phone number they
 * referred — into a row of this spreadsheet. eaze-referral-service POSTs to this script's Web
 * App URL, fire-and-forget, once per newly-accepted phone number (see
 * app/services/sheets_webhook.py). This is a supplementary, human-readable view for anyone who
 * wants to glance at referral activity without DB access — referral_intents in Postgres remains
 * the actual source of truth for the reward pipeline.
 *
 * One-time setup:
 *   1. Create a new Google Sheet (or open the one you want rows appended to).
 *   2. Extensions -> Apps Script. Delete anything in Code.gs and paste this whole file in.
 *   3. Project Settings (gear icon) -> Script Properties -> add a property named
 *      WEBHOOK_SECRET with a value you make up (a random string). This must match the
 *      GOOGLE_SHEETS_WEBHOOK_SECRET env var on the backend, or requests are rejected.
 *   4. Run the `setupSheet` function once from the Apps Script editor (Run -> setupSheet) to
 *      write the header row and grant the script permission to edit this spreadsheet.
 *   5. Deploy -> New deployment -> type "Web app". Execute as: Me. Who has access: Anyone.
 *      Deploy, then copy the Web app URL it gives you.
 *   6. Set that URL as GOOGLE_SHEETS_WEBHOOK_URL on the backend (see .env.tier-*.example) and
 *      the same secret from step 3 as GOOGLE_SHEETS_WEBHOOK_SECRET. Restart the backend.
 *   7. Whenever you edit this script, you must create a NEW deployment version (Deploy -> Manage
 *      deployments -> Edit -> New version) for the change to actually take effect at the
 *      existing URL — saving the file alone does not update a live Web App deployment.
 */

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
      return jsonResponse({ ok: false, error: 'invalid secret' }, 401);
    }
    if (!body.referrerUserId || !body.phoneE164) {
      return jsonResponse({ ok: false, error: 'referrerUserId and phoneE164 are required' }, 400);
    }

    setupSheet(); // no-op if the header row already exists
    getOrCreateSheet().appendRow([new Date(), body.referrerUserId, body.phoneE164]);

    return jsonResponse({ ok: true });
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err) }, 500);
  }
}

// Apps Script's ContentService can't actually set a custom HTTP status code on the response
// (Web Apps always reply 200 at the transport level) -- the `status` argument is accepted here
// for symmetry with the backend's expectations and so the JSON body itself always carries the
// real outcome; the backend checks `ok`, not the transport status.
function jsonResponse(payload, status) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON);
}
