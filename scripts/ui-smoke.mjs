#!/usr/bin/env node
/**
 * Browser smoke test for the WebUI (graph page + kb wizard).
 *
 * Why this exists: the graph panel crashed on drag because a state updater read
 * `dragRef.current!.dx` after `pointerup` had already cleared the ref. That is a
 * runtime-only failure — a type check and a production build both pass. This
 * script drives a real browser so the same class of bug fails loudly.
 *
 * Usage:
 *   npm i puppeteer-core          # once, anywhere (or in web/)
 *   node scripts/ui-smoke.mjs http://127.0.0.1:16108/
 *
 * `URL` defaults to http://127.0.0.1:16108/ (coffee WebUI). Point it at 6109 for
 * ai-history. A tunnel works too:
 *   ssh -N -L 16108:127.0.0.1:6108 faye@<trial-host>
 *
 * Exit code: 0 ok, 1 page errors found, 2 the script could not run.
 */
import { createRequire } from 'node:module';

// puppeteer-core is not a project dependency (it would bloat every web build).
// Resolve it from wherever it happens to be installed: PUPPETEER_DIR, or the
// usual module resolution.
let puppeteer;
try {
  puppeteer = (await import('puppeteer-core')).default;
} catch {
  const dir = process.env.PUPPETEER_DIR;
  if (!dir) {
    console.error(
      'puppeteer-core not found. Install it (npm i puppeteer-core) or set PUPPETEER_DIR to a directory that has it.',
    );
    process.exit(2);
  }
  puppeteer = createRequire(`${dir}/package.json`)('puppeteer-core');
}

const URL = process.argv[2] || process.env.URL || 'http://127.0.0.1:16108/';
const CHROME = process.env.CHROME_PATH || '/usr/bin/google-chrome';

const GRAPH_LABELS = ['图谱', 'Graph', 'グラフ'];
const WIZARD_LABELS = ['新建库', 'New KB', '新規KB'];
const PREVIEW_LABELS = ['预览计划', 'Preview plan', '計画をプレビュー'];
const EXPAND_LABELS = ['展开邻居', 'Expand neighbours', '隣接ノードを展開'];
const PRUNE_LABELS = ['隐藏未展开节点', 'Hide unexpanded', '未展開を隠す'];
const RESET_LABELS = ['重置视图', 'Reset view', '表示をリセット'];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* The two helpers below run inside the page (serialised by puppeteer), so they
   must be self-contained: no imports, no closure over Node variables. */

/** Click the first button whose trimmed text matches one of the labels. */
function clickByLabel(labels) {
  const b = [...document.querySelectorAll('button')].find((x) =>
    labels.includes((x.textContent || '').trim()),
  );
  if (!b) return false;
  b.click();
  return true;
}

/** Set a controlled input's value so React notices the change. */
function setInput(value) {
  const input = document.querySelector('input');
  if (!input) return false;
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'value',
  ).set;
  setter.call(input, value);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
}

const main = async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 1000 });

  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', (e) => pageErrors.push(String(e)));
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text());
  });

  const report = { url: URL };

  await page.goto(URL, { waitUntil: 'networkidle2', timeout: 60000 });

  // ── graph ────────────────────────────────────────────────────────────
  if (!(await page.evaluate(clickByLabel, GRAPH_LABELS))) {
    throw new Error('graph nav button not found');
  }
  await page.waitForSelector('canvas', { timeout: 30000 });
  await sleep(4000);

  const box = await page.$eval('canvas', (el) => {
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height };
  });

  const drag = async (fromX, fromY, toX, toY, steps = 12) => {
    await page.mouse.move(fromX, fromY);
    await page.mouse.down();
    for (let i = 1; i <= steps; i++) {
      await page.mouse.move(
        fromX + ((toX - fromX) * i) / steps,
        fromY + ((toY - fromY) * i) / steps,
      );
    }
    await page.mouse.up();
  };

  const cx = box.x + box.w / 2;
  const cy = box.y + box.h / 2;

  // Pan (press on empty space).
  await drag(cx, cy, cx + 160, cy + 90);
  await sleep(400);

  // Drag a node: hover a grid until the cursor turns into a pointer.
  report.nodeDrag = false;
  outer: for (let gx = 0.2; gx <= 0.8; gx += 0.1) {
    for (let gy = 0.2; gy <= 0.8; gy += 0.1) {
      const px = box.x + box.w * gx;
      const py = box.y + box.h * gy;
      await page.mouse.move(px, py);
      await sleep(60);
      const cursor = await page.$eval('canvas', (el) => el.style.cursor);
      if (cursor === 'pointer') {
        await drag(px, py, px + 40, py - 30, 8);
        report.nodeDrag = true;
        break outer;
      }
    }
  }
  await sleep(400);

  // Zoom.
  await page.mouse.move(cx, cy);
  await page.mouse.wheel({ deltaY: -240 });
  await sleep(300);
  await page.mouse.wheel({ deltaY: 480 });
  await sleep(400);

  // Sidebar focus, expand, double-click, prune, reset, search.
  report.sidebarClick = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')];
    const entity = btns.find(
      (b) =>
        b.querySelectorAll('span').length === 2 &&
        !b.className.includes('navItem'),
    );
    if (!entity) return false;
    entity.click();
    return true;
  });
  await sleep(1200);
  report.expand = await page.evaluate(clickByLabel, EXPAND_LABELS);
  await sleep(1500);
  await page.mouse.click(cx, cy, { clickCount: 2 });
  await sleep(1500);
  report.prune = await page.evaluate(clickByLabel, PRUNE_LABELS);
  await sleep(600);
  report.reset = await page.evaluate(clickByLabel, RESET_LABELS);
  report.search = await page.evaluate(setInput, 'a');
  await sleep(600);

  // Check the graph survived every interaction *before* leaving the panel.
  report.canvasStillThere = await page.evaluate(() => !!document.querySelector('canvas'));
  report.hasErrorOverlay = await page.evaluate(() => !!document.querySelector('nextjs-portal'));

  // ── kb wizard (dry run: nothing is written) ──────────────────────────
  report.wizardOpened = await page.evaluate(clickByLabel, WIZARD_LABELS);
  await sleep(1200);
  if (report.wizardOpened) {
    await page.evaluate(setInput, 'bad name!');
    await sleep(300);
    report.previewDisabledOnBadName = await page.evaluate((labs) => {
      const b = [...document.querySelectorAll('button')].find((x) =>
        labs.includes((x.textContent || '').trim()),
      );
      return b ? b.disabled : null;
    }, PREVIEW_LABELS);

    await page.evaluate(setInput, 'smoke-probe-kb');
    await sleep(300);
    report.previewEnabledOnGoodName = await page.evaluate((labs) => {
      const b = [...document.querySelectorAll('button')].find((x) =>
        labs.includes((x.textContent || '').trim()),
      );
      return b ? !b.disabled : null;
    }, PREVIEW_LABELS);

    await page.evaluate(clickByLabel, PREVIEW_LABELS);
    await sleep(2000);
    report.planRendered = await page.evaluate(
      () => (document.body.innerText || '').includes('smoke-probe-kb'),
    );
  }

  report.pageErrors = pageErrors;
  report.consoleErrors = consoleErrors.slice(0, 5);

  await browser.close();

  console.log(JSON.stringify(report, null, 2));

  const failed =
    pageErrors.length > 0 ||
    consoleErrors.length > 0 ||
    report.hasErrorOverlay ||
    !report.canvasStillThere ||
    report.nodeDrag !== true;
  return failed ? 1 : 0;
};

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error('FAILED:', err.message);
    process.exit(2);
  });
