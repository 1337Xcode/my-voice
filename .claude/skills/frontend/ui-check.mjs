// Screenshots each URL at phone and desktop size, and lists what can be measured about the screen:
// horizontal overflow, text under 12 px, too many font sizes, saturated colours (violet and navy
// especially), icons in headings, emoji, a font other than Geist, placeholder or "demo" copy,
// unlabelled controls, and console or network errors. Taste still needs a person looking.
//   node .claude/skills/frontend/ui-check.mjs <url> [url...]
// Needs Playwright in the project, once: npm i -D playwright && npx playwright install chromium
import fs from 'node:fs';
import path from 'node:path';

const VIEWPORTS = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'desktop', width: 1440, height: 900 },
];
const OUT_DIR = path.join(process.cwd(), '.work', 'screens');
// Long enough for a dev server's first compile of a page.
const LOAD_TIMEOUT_MS = 60000;

/** Loads Playwright from the project, or says how to install it. */
async function loadPlaywright() {
  try {
    return await import('playwright');
  } catch {
    console.error('Playwright is not installed in this project. Run: npm i -D playwright && npx playwright install chromium');
    process.exit(1);
  }
}

/** Runs inside the page: measures layout, type, colour, copy and controls. Must stay self-contained. */
function measure() {
  const problems = [];
  const isVisible = (el) => {
    const box = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && Number(style.opacity) > 0;
  };
  const elements = [...document.body.querySelectorAll('*')].filter(isVisible);
  const ownText = (el) => [...el.childNodes].filter((node) => node.nodeType === 3).map((node) => node.textContent.trim()).join(' ').trim();
  const describe = (el) => `<${el.tagName.toLowerCase()}> "${(el.textContent || '').trim().slice(0, 40)}"`;

  // Layout: anything wider than the viewport makes the page scroll sideways.
  const overflow = document.documentElement.scrollWidth - window.innerWidth;
  if (overflow > 1) {
    const culprit = elements.find((el) => el.getBoundingClientRect().right > window.innerWidth + 1);
    problems.push(`page scrolls sideways by ${overflow}px${culprit ? `, first offender ${describe(culprit)}` : ''}`);
  }

  // Type: size floor, number of sizes, and the family.
  const texts = elements.filter((el) => ownText(el) !== '');
  const small = texts.filter((el) => parseFloat(getComputedStyle(el).fontSize) < 12);
  if (small.length > 0) problems.push(`${small.length} text elements under 12px, e.g. ${describe(small[0])}`);
  const sizes = new Set(texts.map((el) => getComputedStyle(el).fontSize));
  if (sizes.size > 6) problems.push(`${sizes.size} different font sizes (${[...sizes].join(', ')}); four or five is plenty`);
  const family = getComputedStyle(document.body).fontFamily;
  if (!/geist/i.test(family)) problems.push(`body font is ${family.split(',')[0]}, not Geist`);

  // Colour: every painted colour converted to sRGB through a 1px canvas, which accepts any CSS colour.
  const canvas = document.createElement('canvas');
  canvas.width = 1;
  canvas.height = 1;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  const toRgb = new Map();
  const rgbOf = (value) => {
    if (!toRgb.has(value)) {
      context.clearRect(0, 0, 1, 1);
      context.fillStyle = value;
      context.fillRect(0, 0, 1, 1);
      const [r, g, b, a] = context.getImageData(0, 0, 1, 1).data;
      toRgb.set(value, a < 26 ? null : [r, g, b]);
    }
    return toRgb.get(value);
  };
  const hueOf = ([r, g, b]) => {
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const delta = max - min;
    if (delta === 0) return { hue: 0, chroma: 0, lightness: max / 255 };
    const hue = max === r ? ((g - b) / delta) % 6 : max === g ? (b - r) / delta + 2 : (r - g) / delta + 4;
    return { hue: (hue * 60 + 360) % 360, chroma: delta / 255, lightness: (max + min) / 510 };
  };
  const saturated = new Map();
  const gradients = [];
  for (const el of elements) {
    const style = getComputedStyle(el);
    const painted = [style.color, style.backgroundColor];
    // A gradient lives in background-image; its colour stops count as painted colours too.
    if (/gradient\(/.test(style.backgroundImage)) {
      gradients.push(el);
      painted.push(...(style.backgroundImage.match(/(?:rgba?|oklch|oklab|lab|lch|hsla?|color)\([^)]*\)|#[0-9a-f]{3,8}\b/gi) ?? []));
    }
    if (parseFloat(style.borderTopWidth) > 0) painted.push(style.borderTopColor);
    if (el instanceof SVGElement) painted.push(style.fill, style.stroke);
    for (const value of painted) {
      const rgb = value && value !== 'none' ? rgbOf(value) : null;
      if (rgb === null || hueOf(rgb).chroma < 0.18) continue;
      const hex = `#${rgb.map((channel) => channel.toString(16).padStart(2, '0')).join('')}`;
      saturated.set(hex, (saturated.get(hex) ?? 0) + 1);
    }
  }
  const hues = new Set();
  for (const [hex, count] of saturated) {
    const rgb = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16));
    const { hue, lightness } = hueOf(rgb);
    hues.add(Math.round(hue / 30) % 12);
    // Indigo sits near 240, violet and purple at 250 to 300, fuchsia to 320; navy is a dark blue.
    if (hue >= 235 && hue <= 320) problems.push(`violet, indigo or purple ${hex} on ${count} elements`);
    else if (hue >= 200 && hue < 235 && lightness < 0.35) problems.push(`navy ${hex} on ${count} elements`);
  }
  if (hues.size > 3) problems.push(`${hues.size} different saturated hues (${[...saturated.keys()].slice(0, 6).join(', ')}); aim for one accent plus status colours`);
  if (gradients.length > 0) problems.push(`${gradients.length} gradient backgrounds, e.g. ${describe(gradients[0])}`);

  // Decoration: icons inside headings, and emoji anywhere on screen.
  const iconHeadings = [...document.querySelectorAll('h1, h2, h3, h4')].filter((heading) => isVisible(heading) && heading.querySelector('svg, img'));
  if (iconHeadings.length > 0) problems.push(`${iconHeadings.length} headings carry an icon, e.g. ${describe(iconHeadings[0])}`);
  const visibleText = document.body.innerText;
  const emoji = visibleText.match(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu);
  if (emoji) problems.push(`emoji on screen: ${[...new Set(emoji)].join(' ')}`);
  const placeholder = visibleText.match(/lorem ipsum|coming soon|\b(?:demo|mock|sample data|simulated|beta)\b/gi);
  if (placeholder) problems.push(`placeholder or demo copy on screen: ${[...new Set(placeholder.map((word) => word.toLowerCase()))].join(', ')}`);
  const hype = visibleText.match(/\bAI-powered\b|\brevolutionary\b|\bseamless(?:ly)?\b|\bsupercharge\w*|\bunleash\w*|\bgame-chang\w*|\bnext-gen\w*/gi);
  if (hype) problems.push(`marketing words on screen: ${[...new Set(hype.map((word) => word.toLowerCase()))].join(', ')}; say what it does instead`);

  // Controls a person or a screen reader cannot name.
  const named = (el) => (el.innerText || '').trim() !== '' || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.getAttribute('title');
  const unnamed = elements.filter((el) => el.matches('button, [role="button"], a[href]') && !named(el));
  if (unnamed.length > 0) problems.push(`${unnamed.length} buttons or links with no text or aria-label`);
  const fields = elements.filter((el) => el.matches('input:not([type="hidden"]), textarea, select'));
  const unlabelled = fields.filter((el) => !(el.labels?.length > 0 || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.getAttribute('placeholder')));
  if (unlabelled.length > 0) problems.push(`${unlabelled.length} form fields with no label`);
  const images = elements.filter((el) => el.matches('img:not([alt])'));
  if (images.length > 0) problems.push(`${images.length} images with no alt text`);
  return problems;
}

/** Opens one URL at one viewport, saves a full-page screenshot, and returns what it found. */
async function checkPage(browser, url, viewport) {
  const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
  const runtime = [];
  page.on('console', (message) => {
    if (message.type() === 'error') runtime.push(`console error: ${message.text().slice(0, 160)}`);
  });
  page.on('pageerror', (error) => runtime.push(`uncaught error: ${error.message.slice(0, 160)}`));
  page.on('response', (response) => {
    if (response.status() >= 400 && !response.url().endsWith('favicon.ico')) runtime.push(`${response.status()} from ${response.url()}`);
  });
  await page.goto(url, { waitUntil: 'networkidle', timeout: LOAD_TIMEOUT_MS });
  const slug = new URL(url).pathname.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'home';
  const file = path.join(OUT_DIR, `${slug}-${viewport.name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  const problems = [...(await page.evaluate(measure)), ...runtime];
  await page.close();
  return { file, problems };
}

/** Checks every URL at both sizes and prints the report. */
async function main() {
  const urls = process.argv.slice(2);
  if (urls.length === 0) {
    console.error('Usage: node .claude/skills/frontend/ui-check.mjs <url> [url...]');
    process.exit(1);
  }
  const { chromium } = await loadPlaywright();
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  try {
    for (const url of urls) {
      for (const viewport of VIEWPORTS) {
        const { file, problems } = await checkPage(browser, url, viewport);
        console.log(`\n${url} at ${viewport.width}x${viewport.height}: ${path.relative(process.cwd(), file)}`);
        console.log(problems.length === 0 ? '  nothing measurable to fix' : problems.map((problem) => `  - ${problem}`).join('\n'));
      }
    }
  } finally {
    await browser.close();
  }
  console.log('\nNow open each screenshot and review it against the frontend checklist: hierarchy, spacing and taste cannot be measured.');
}

main().catch((error) => {
  console.error(`ui-check could not finish: ${error.message}`);
  process.exit(1);
});
