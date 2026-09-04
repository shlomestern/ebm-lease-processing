/**
 * Sign in to CORPIQ (ProprioLocation) headless, for unattended runs.
 *
 *   node tools/corpiq_login.js            # sign in, report what it reached
 *   node tools/corpiq_login.js --shot x   # ...and save a screenshot to x.png
 *
 * Credentials come from CORPIQ_EMAIL / CORPIQ_PASSWORD in the environment and
 * are never printed. Nothing is written to the CORPIQ account: this only signs
 * in and reads the lease list, so it is safe to run to check access.
 *
 * Two things are required in a cloud session and are easy to miss:
 *
 *   1. Chromium's Encrypted Client Hello makes the agent proxy drop the TLS
 *      handshake, and every page load fails with ERR_CONNECTION_RESET. The
 *      environment's setup script disables it via
 *      /etc/chromium/policies/managed/ccr.json.
 *   2. The browser must be pointed at the proxy explicitly — it does not read
 *      HTTPS_PROXY by itself.
 */
const { chromium } = require('playwright');

const LEASES_URL = 'https://demandes.corpiq.com/en/leases/#/leases';
const CHROMIUM = process.env.CORPIQ_CHROMIUM
  || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

async function login({ shot } = {}) {
  const email = process.env.CORPIQ_EMAIL;
  const password = process.env.CORPIQ_PASSWORD;
  if (!email || !password) {
    throw new Error('CORPIQ_EMAIL / CORPIQ_PASSWORD are not set in this environment');
  }
  const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;

  const browser = await chromium.launch({
    executablePath: CHROMIUM,
    headless: true,
    proxy: proxy ? { server: proxy } : undefined,
    args: ['--no-sandbox'],
  });
  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 },
    locale: 'en-CA',
  });
  const page = await context.newPage();

  await page.goto(LEASES_URL, { waitUntil: 'domcontentloaded', timeout: 45000 });

  if (await page.locator('input[name="password"]').first().isVisible().catch(() => false)) {
    await page.fill('input[name="username"]', email);
    await page.fill('input[name="password"]', password);
    const remember = page.locator('input[name="remember_me"]').first();
    if (await remember.isVisible().catch(() => false)) await remember.check().catch(() => {});
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {}),
      page.click('button[type="submit"], input[type="submit"]'),
    ]);
    await page.waitForTimeout(4000);
  }

  // A privacy-policy / important-message modal can sit in front of the app.
  for (const label of ['I accept', 'Accept', "J'accepte", 'Accepter', 'Continue', 'OK']) {
    const b = page.locator(`button:has-text("${label}")`).first();
    if (await b.isVisible().catch(() => false)) {
      await b.click().catch(() => {});
      await page.waitForTimeout(2000);
      break;
    }
  }

  await page.goto(LEASES_URL, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
  await page.waitForTimeout(5000);

  const stillLogin = await page.locator('input[name="password"]').first().isVisible().catch(() => false);
  if (stillLogin) {
    await browser.close();
    throw new Error('CORPIQ login did not complete — still on the sign-in page');
  }
  if (shot) await page.screenshot({ path: shot.endsWith('.png') ? shot : `${shot}.png` });

  return { browser, context, page };
}

module.exports = { login, LEASES_URL };

if (require.main === module) {
  const i = process.argv.indexOf('--shot');
  const shot = i > -1 ? process.argv[i + 1] : null;
  login({ shot })
    .then(async ({ browser, page }) => {
      const body = (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ');
      const credits = body.match(/REMAINING LEASES:\s*(\d+)/i);
      console.log('signed in :', /logout|déconnexion/i.test(body));
      console.log('url       :', page.url());
      if (credits) console.log('credits   :', credits[1]);
      console.log('list head :', body.slice(0, 220));
      await browser.close();
    })
    .catch((e) => {
      console.error('FAILED:', e.message);
      process.exit(1);
    });
}
