/**
 * EBM Lease Bridge  (Google Apps Script, bound to ebmteam220@gmail.com)
 * --------------------------------------------------------------------
 * Every minute:
 *   1. find NEW lease-request threads in the inbox,
 *   2. label them so they are never handled twice,
 *   3. send the acknowledgment reply,
 *   4. POST a JSON payload to WEBHOOK_URL so Claude starts drafting the lease.
 *
 * INSTALL: paste this whole file into Code.gs at script.google.com, fill in the
 * CONFIG block, save, then run the function  setup  once (it creates the labels
 * and the 1-minute trigger).  See the install guide for the exact clicks.
 */

// ============================== CONFIG =====================================

// Where Claude receives new lease requests. Must be a public HTTPS URL with a
// valid certificate. Leave "" to disable the webhook (reply + label still work).
var WEBHOOK_URL = "https://REPLACE-ME.example.com/hook";

// Optional shared secret. If set, every POST carries:
//   X-Bridge-Secret: <secret>
//   X-Bridge-Signature: sha256=<hex HMAC-SHA256 of the raw JSON body>
var SHARED_SECRET = "";

// Optional extra headers the webhook target may require (e.g. Authorization).
var EXTRA_HEADERS = {
  // "Authorization": "Bearer ..."
};

// Optional: also forward each new request as an email to this address
// (useful as a second delivery path while the webhook target is being chosen).
var FORWARD_COPY_TO = "";

// Acknowledgment reply text (plain text; sent once per thread).
var ACK_BODY =
  "Hi, I've received your email and the lease is being taken care of. " +
  "I'll follow up shortly if anything is missing.\n\n" +
  "Thanks,\nEmpire Building Management";
var ACK_SENDER_NAME = "Empire Building Management";

// Gmail labels used for idempotency.
var LABEL_ACKED   = "Lease-Ack-Sent";       // reply already sent
var LABEL_SENT    = "Lease-Sent-to-Claude"; // webhook delivered (2xx)
var LABEL_IGNORED = "Lease-Not-a-Lease";    // looked at, not a lease request
// (keep label names flat: no spaces or slashes, so label: search terms are exact)

// How far back to look for unlabeled threads. Keeps each run fast.
var LOOKBACK = "newer_than:2d";

// Trigger interval in minutes. Must be 1, 5, 10, 15 or 30.
// 1 = fastest. Consumer Gmail accounts get 90 min/day of trigger runtime,
// i.e. an average of 3.75 s per run at 1-minute cadence; an idle run of this
// script takes well under 1 s, so 1 is fine. Switch to 5 if you ever see
// "Service invoked too many times" in the Executions log.
var TRIGGER_EVERY_MINUTES = 1;

// Max threads to handle per run (protects the 6 min/execution limit).
var MAX_THREADS_PER_RUN = 10;

// HARD CIRCUIT BREAKER. The bridge will never send more than this many
// acknowledgment emails in one calendar day, no matter what else goes wrong.
// A real day of lease requests is a handful; if this cap is ever hit,
// something is broken and silence is the correct behaviour.
// (On 2026-09-01 a classifier bug sent ~93 duplicates. This is the backstop.)
var MAX_ACKS_PER_DAY = 12;

// Webhook retry attempts per thread (one attempt per run) before giving up.
var MAX_WEBHOOK_ATTEMPTS = 10;

// ============================ END CONFIG ===================================

var HANDLER_FUNCTION = "processNewLeaseRequests";
var ACK_MARKER = "the lease is being taken care of";

/** Main entry point, run by the time-driven trigger. */
function processNewLeaseRequests() {
  var t0 = Date.now();
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) {
    Logger.log("Another run is still active; skipping.");
    return;
  }
  try {
    var labels = ensureLabels_();
    var me = Session.getEffectiveUser().getEmail().toLowerCase();

    // 1) Brand-new threads: nothing from us on them yet.
    var q = "in:inbox " + LOOKBACK +
            " -label:" + quoteLabel_(LABEL_ACKED) +
            " -label:" + quoteLabel_(LABEL_IGNORED);
    var threads = GmailApp.search(q, 0, MAX_THREADS_PER_RUN);
    var handledNow = {};
    for (var i = 0; i < threads.length; i++) {
      handledNow[threads[i].getId()] = true;
      try {
        handleThread_(threads[i], labels, me);
      } catch (e) {
        Logger.log("Thread " + threads[i].getId() + " failed: " + e);
      }
    }

    // 2) Retry webhook for acknowledged threads whose POST failed on an earlier run.
    if (WEBHOOK_URL) {
      var rq = LOOKBACK + " label:" + quoteLabel_(LABEL_ACKED) +
               " -label:" + quoteLabel_(LABEL_SENT);
      var retries = GmailApp.search(rq, 0, MAX_THREADS_PER_RUN);
      for (var j = 0; j < retries.length; j++) {
        if (handledNow[retries[j].getId()]) continue; // one attempt per run
        try {
          retryWebhook_(retries[j], labels);
        } catch (e2) {
          Logger.log("Retry " + retries[j].getId() + " failed: " + e2);
        }
      }
    }
  } finally {
    lock.releaseLock();
    recordRuntime_(Date.now() - t0);
  }
}

/** Decide, reply, label, POST. */
function handleThread_(thread, labels, me) {
  var msgs = thread.getMessages();
  var msg = lastInboundMessage_(msgs, me);
  if (!msg) return; // only our own messages on this thread

  var info = extractInfo_(thread, msg);
  var verdict = classify_(info);
  if (!verdict.isLease) {
    thread.addLabel(labels.ignored);
    return;
  }

  // Never answer our own mail, whatever the classifier decided.
  if (info.fromSelf) {
    thread.addLabel(labels.ignored);
    Logger.log("Refusing to reply to our own message on thread " + thread.getId());
    return;
  }

  // Global circuit breaker: however wrong anything else goes, the bridge can
  // never send more than MAX_ACKS_PER_DAY messages in a day.
  if (!consumeAckQuota_()) {
    Logger.log("DAILY ACK CAP (" + MAX_ACKS_PER_DAY + ") REACHED — sending nothing further today.");
    return;
  }

  // (1) Acknowledge. Label FIRST so a crash after reply() can't double-send.
  // Reply to the REQUESTER'S message, not thread.reply(): the latter answers
  // whatever message is last on the thread, which after our own ack is us —
  // producing a self-addressed reply that looks like a fresh request.
  thread.addLabel(labels.acked);
  msg.reply(ACK_BODY, { name: ACK_SENDER_NAME });
  Logger.log("Ack sent to " + info.from + " on thread " + thread.getId() + " (" + info.subject + ")");

  // Optional email copy.
  if (FORWARD_COPY_TO) {
    try {
      msg.forward(FORWARD_COPY_TO, {
        subject: "[Lease request] " + info.subject,
        name: ACK_SENDER_NAME
      });
    } catch (e) {
      Logger.log("Forward copy failed: " + e);
    }
  }

  // (2) Tell Claude.
  if (WEBHOOK_URL) {
    var ok = postWebhook_(buildPayload_(info, verdict, 1));
    if (ok) thread.addLabel(labels.sent);
    else setAttempts_(thread.getId(), 1);
  }
}

/** Re-POST for a thread that was acknowledged but never delivered. */
function retryWebhook_(thread, labels) {
  var id = thread.getId();
  var attempts = getAttempts_(id);
  if (attempts >= MAX_WEBHOOK_ATTEMPTS) return;
  var me = Session.getEffectiveUser().getEmail().toLowerCase();
  var msg = lastInboundMessage_(thread.getMessages(), me);
  if (!msg) return;
  var info = extractInfo_(thread, msg);
  var verdict = classify_(info);
  var ok = postWebhook_(buildPayload_(info, verdict, attempts + 1));
  if (ok) {
    thread.addLabel(labels.sent);
    clearAttempts_(id);
  } else {
    setAttempts_(id, attempts + 1);
  }
}

/** Newest message on the thread that is not one of ours. */
function lastInboundMessage_(msgs, me) {
  for (var i = msgs.length - 1; i >= 0; i--) {
    var m = msgs[i];
    var from = (m.getFrom() || "").toLowerCase();
    if (from.indexOf(me) !== -1) continue;
    var body = m.getPlainBody() || "";
    if (body.indexOf(ACK_MARKER) !== -1 && from.indexOf("empire") !== -1) continue;
    return m;
  }
  return null;
}

/** Pull the fields we need out of a message. */
function extractInfo_(thread, msg) {
  var body = "";
  try { body = msg.getPlainBody() || ""; } catch (e) { body = ""; }
  if (!body) {
    try { body = stripHtml_(msg.getBody() || ""); } catch (e2) { body = ""; }
  }
  var atts = [];
  try {
    var a = msg.getAttachments({ includeInlineImages: false, includeAttachments: true });
    for (var i = 0; i < a.length; i++) {
      atts.push({ name: a[i].getName(), contentType: a[i].getContentType(), size: a[i].getSize() });
    }
  } catch (e3) { /* ignore */ }

  var autoSubmitted = "";
  try { autoSubmitted = msg.getHeader("Auto-Submitted") || ""; } catch (e4) { /* ignore */ }

  return {
    threadId: thread.getId(),
    messageId: msg.getId(),
    subject: msg.getSubject() || thread.getFirstMessageSubject() || "",
    from: msg.getFrom() || "",
    to: msg.getTo() || "",
    cc: msg.getCc() || "",
    date: msg.getDate(),
    body: body,
    attachments: atts,
    permalink: thread.getPermalink ? thread.getPermalink() : "",
    autoSubmitted: autoSubmitted,
    messageCount: thread.getMessageCount ? thread.getMessageCount() : 0,
    fromSelf: isFromSelf_(msg.getFrom() || "")
  };
}

/** True when a message was sent by this mailbox (any alias form). */
function isFromSelf_(from) {
  var f = (from || "").toLowerCase();
  var me = "";
  try { me = (Session.getEffectiveUser().getEmail() || "").toLowerCase(); } catch (e) { me = ""; }
  if (me && f.indexOf(me) !== -1) return true;
  // Fall back to the literal mailbox, in case getEffectiveUser() is empty in a
  // trigger context — an empty "me" must never make this return false-negative.
  if (f.indexOf("ebmteam220@gmail.com") !== -1) return true;
  return false;
}

/**
 * Lease-request detector. Returns { isLease, reason, signals }.
 *  - subject contains "lease for"                       -> lease
 *  - forwards a SingleKey report (subject/body/attachment) -> lease
 *  - body has (name/email/phone) + rent + start date     -> lease
 */
function classify_(info) {
  var subj = (info.subject || "").toLowerCase();
  var body = (info.body || "").toLowerCase();
  var text = subj + "\n" + body;
  var signals = {};

  // Hard excludes: auto-replies / bounces / our own acknowledgment.
  if (/^auto-(replied|generated)/i.test(info.autoSubmitted || "")) {
    return { isLease: false, reason: "auto-submitted", signals: signals };
  }
  if (/^(automatic reply|out of office|delivery status notification|undeliverable)/i.test(subj)) {
    return { isLease: false, reason: "auto-reply", signals: signals };
  }
  // Our own acknowledgment, bounced back into the inbox. This MUST be excluded
  // unconditionally: the ack carries the subject "Re: Lease for ...", so any
  // carve-out based on the subject makes the script answer its own replies
  // forever. (That is exactly what happened on 2026-09-01: ~93 duplicates.)
  if (body.indexOf(ACK_MARKER) !== -1) {
    return { isLease: false, reason: "our-ack", signals: signals };
  }
  // Anything we sent ourselves is never an incoming request.
  if (info.fromSelf) {
    return { isLease: false, reason: "from-self", signals: signals };
  }

  signals.subjectLeaseFor = /\blease\s+for\b/.test(subj);
  signals.singleKey = /single\s*key/.test(text) ||
    info.attachments.some(function (a) { return /single\s*key/i.test(a.name || ""); });
  signals.email = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/.test(body);
  signals.phone = /(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b/.test(body);
  signals.tenantName = /\b(tenant|name|locataire|nom)\s*[:\-]/.test(body);
  signals.rent = /\b(rent|loyer|monthly)\b[^\n]{0,40}\$?\s?\d{3,5}|\$\s?\d{1,2},?\d{3}(\.\d{2})?\s*(\/|per)?\s*(mo|month|mois)?/.test(body);
  signals.startDate =
    /\b(start|move[\s-]?in|lease\s+start|commenc|d[ée]but|from)\b[^\n]{0,40}(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}|\d{4}-\d{2}-\d{2}|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2})/.test(body) ||
    /\b(1st|first)\s+of\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/.test(body);

  if (signals.subjectLeaseFor) return { isLease: true, reason: "subject", signals: signals };
  if (signals.singleKey)      return { isLease: true, reason: "singlekey", signals: signals };

  var contact = signals.email || signals.phone || signals.tenantName;
  if (contact && signals.rent && signals.startDate) {
    return { isLease: true, reason: "body-fields", signals: signals };
  }
  return { isLease: false, reason: "no-match", signals: signals };
}

/**
 * Payload for the Claude routine /fire endpoint.
 * That API accepts ONE field, "text" (max 65,536 chars), which arrives in the
 * routine run inside a <routine-fire-payload> block. So we format the request
 * as readable text rather than nested JSON.
 */
function buildPayload_(info, verdict, attempt) {
  var body = info.body || "";
  var atts = (info.attachments || []).map(function (a) { return a.name; }).join(", ");
  var lines = [
    "A new lease request just arrived in the Empire Building Management inbox.",
    "",
    "Gmail thread ID: " + info.threadId,
    "Gmail message ID: " + info.messageId,
    "Gmail search (use with the Gmail tools): rfc822msgid:" + info.messageId,
    "Gmail link: " + (info.permalink || "(none)"),
    "Subject: " + (info.subject || "(none)"),
    "From: " + (info.from || "(unknown)"),
    "To: " + (info.to || ""),
    "Cc: " + (info.cc || ""),
    "Received: " + (info.date ? new Date(info.date).toISOString() : "(unknown)"),
    "Attachments: " + (atts || "(none)"),
    "Detected as a lease request because: " + (verdict && verdict.reason ? verdict.reason : "n/a"),
    "Delivery attempt: " + attempt,
    "",
    "NOTE: the acknowledgment reply has ALREADY been sent to the sender by the",
    "Gmail bridge, and the thread is labelled '" + LABEL_ACKED + "'. Do not reply again.",
    "Proceed with drafting the lease.",
    "",
    "----- FULL EMAIL BODY -----",
    body.slice(0, 40000)
  ];
  return { text: lines.join("\n").slice(0, 65000) };
}

/**
 * POST to the Claude routine /fire endpoint. Returns true on any 2xx.
 * The URL and token are read from Script Properties (File > Project settings >
 * Script properties) so the secret never lives in this source file:
 *   FIRE_URL    https://api.anthropic.com/v1/claude_code/routines/trig_.../fire
 *   FIRE_TOKEN  sk-ant-oat01-...
 */
function postWebhook_(payload) {
  var props = PropertiesService.getScriptProperties();
  var url = props.getProperty("FIRE_URL") || WEBHOOK_URL;
  var token = props.getProperty("FIRE_TOKEN") || "";
  if (!url || url.indexOf("REPLACE-ME") !== -1) {
    Logger.log("FIRE_URL script property is not set — skipping the call to Claude.");
    return false;
  }
  if (!token) {
    Logger.log("FIRE_TOKEN script property is not set — skipping the call to Claude.");
    return false;
  }
  var json = JSON.stringify(payload);
  var headers = {
    "Authorization": "Bearer " + token,
    "anthropic-beta": "experimental-cc-routine-2026-04-01",
    "anthropic-version": "2023-06-01"
  };
  for (var k in EXTRA_HEADERS) headers[k] = EXTRA_HEADERS[k];
  var options = {
    method: "post",
    contentType: "application/json",
    headers: headers,
    payload: json,
    muteHttpExceptions: true,
    followRedirects: true
  };
  try {
    var resp = UrlFetchApp.fetch(url, options);
    var code = resp.getResponseCode();
    Logger.log("Claude routine fire -> HTTP " + code +
               (code >= 300 ? " body=" + String(resp.getContentText()).slice(0, 300) : " (session started)"));
    return code >= 200 && code < 300;
  } catch (e) {
    Logger.log("Claude routine fire error: " + e);
    return false;
  }
}

function hmacHex_(text, secret) {
  var sig = Utilities.computeHmacSha256Signature(text, secret);
  return sig.map(function (b) { return ("0" + (b & 0xff).toString(16)).slice(-2); }).join("");
}

// ------------------------------ helpers ------------------------------------

function ensureLabels_() {
  return {
    acked:   GmailApp.getUserLabelByName(LABEL_ACKED)   || GmailApp.createLabel(LABEL_ACKED),
    sent:    GmailApp.getUserLabelByName(LABEL_SENT)    || GmailApp.createLabel(LABEL_SENT),
    ignored: GmailApp.getUserLabelByName(LABEL_IGNORED) || GmailApp.createLabel(LABEL_IGNORED)
  };
}

function quoteLabel_(name) {
  // Label names are flat (no spaces/slashes) so they can be used verbatim.
  return name;
}

function stripHtml_(html) {
  return html.replace(/<style[\s\S]*?<\/style>/gi, " ")
             .replace(/<[^>]+>/g, " ")
             .replace(/&nbsp;/g, " ")
             .replace(/&amp;/g, "&")
             .replace(/\s+/g, " ")
             .trim();
}

function getAttempts_(threadId) {
  var v = PropertiesService.getScriptProperties().getProperty("attempts:" + threadId);
  return v ? parseInt(v, 10) : 0;
}
function setAttempts_(threadId, n) {
  PropertiesService.getScriptProperties().setProperty("attempts:" + threadId, String(n));
}
function clearAttempts_(threadId) {
  PropertiesService.getScriptProperties().deleteProperty("attempts:" + threadId);
}

/**
 * Daily send budget. Returns true and consumes one slot if the bridge may send
 * another acknowledgment today; false once MAX_ACKS_PER_DAY is exhausted.
 * The counter is keyed by date, so it resets itself each day.
 */
function consumeAckQuota_() {
  var p = PropertiesService.getScriptProperties();
  var today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd");
  var key = "acks:" + today;
  var used = parseInt(p.getProperty(key) || "0", 10);
  if (used >= MAX_ACKS_PER_DAY) return false;
  p.setProperty(key, String(used + 1));
  return true;
}

/** How many acknowledgments have gone out today (for the status report). */
function acksUsedToday_() {
  var today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd");
  return parseInt(PropertiesService.getScriptProperties().getProperty("acks:" + today) || "0", 10);
}

/** Keeps a rolling average of run time so you can check the 90 min/day budget. */
function recordRuntime_(ms) {
  try {
    var p = PropertiesService.getScriptProperties();
    var n = parseInt(p.getProperty("stats:runs") || "0", 10) + 1;
    var total = parseInt(p.getProperty("stats:ms") || "0", 10) + ms;
    p.setProperty("stats:runs", String(n));
    p.setProperty("stats:ms", String(total));
    Logger.log("Run took " + ms + " ms (avg " + Math.round(total / n) + " ms over " + n + " runs)");
  } catch (e) { /* ignore */ }
}

// ------------------------------ one-time setup ------------------------------

/** RUN THIS ONCE from the editor: creates labels + the 1-minute trigger. */
function setup() {
  ensureLabels_();
  // Remove any previous trigger for the handler, then create exactly one.
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === HANDLER_FUNCTION) {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  ScriptApp.newTrigger(HANDLER_FUNCTION)
    .timeBased()
    .everyMinutes(TRIGGER_EVERY_MINUTES)
    .create();
  Logger.log("Trigger installed: " + HANDLER_FUNCTION + " every " + TRIGGER_EVERY_MINUTES + " min.");
}

/** Stops the bridge (deletes the trigger). Labels and mail are untouched. */
function teardown() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === HANDLER_FUNCTION) {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  Logger.log("Trigger removed.");
}

/** Sends a test POST to WEBHOOK_URL without touching Gmail. */
function testWebhook() {
  var ok = postWebhook_({
    event: "lease_request.test", version: 1, source: "gmail-apps-script",
    account: Session.getEffectiveUser().getEmail(), sent_at: new Date().toISOString(),
    thread_id: "TEST", message_id: "TEST", subject: "Lease for Test Tenant",
    from: "tester@example.com", snippet: "This is a test from the EBM Lease Bridge."
  });
  Logger.log("testWebhook: " + (ok ? "OK (2xx)" : "FAILED - see log above"));
}

/** Shows what the detector thinks of the newest inbox threads (no side effects). */
function previewClassification() {
  var me = Session.getEffectiveUser().getEmail().toLowerCase();
  var threads = GmailApp.search("in:inbox " + LOOKBACK, 0, 10);
  for (var i = 0; i < threads.length; i++) {
    var msg = lastInboundMessage_(threads[i].getMessages(), me);
    if (!msg) continue;
    var info = extractInfo_(threads[i], msg);
    var v = classify_(info);
    Logger.log((v.isLease ? "LEASE   " : "ignore  ") + "[" + v.reason + "] " + info.subject + "  <" + info.from + ">");
  }
}
