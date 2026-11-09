const { chromium } = require("../recorder/node_modules/playwright");
const fs = require("fs");
const path = require("path");

const PAGE = "file:///" + path.resolve(__dirname, "index.html").replace(/\\/g, "/");
const FRAMES = path.join(__dirname, "frames");
const FPS = 30;
const DURATION_MS = 15000;

async function seek(page, time) {
  await page.evaluate(async (t) => {
    const animations = document.getAnimations();
    for (const anim of animations) {
      anim.pause();
      anim.currentTime = t;
    }
    await new Promise((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(resolve)),
    );
  }, time);
}

async function main() {
  fs.rmSync(FRAMES, { recursive: true, force: true });
  fs.mkdirSync(FRAMES, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
  });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto(PAGE, { waitUntil: "load" });
  await page.evaluate(async () => {
    await document.fonts.ready;
    if (!document.fonts.check('16px "Plus Jakarta Sans"')) {
      throw new Error("Plus Jakarta Sans did not load");
    }
    if (!document.fonts.check('16px "Noto Sans Myanmar"')) {
      throw new Error("Noto Sans Myanmar did not load");
    }
  });
  await page.waitForFunction(() => document.getAnimations().length >= 12);

  const previewOnly = process.argv.includes("--preview");
  const frameCount = Math.round((DURATION_MS / 1000) * FPS);
  const times = previewOnly
    ? [5500, 7000, 14000]
    : Array.from({ length: frameCount }, (_, i) => (i * 1000) / FPS);

  for (let i = 0; i < times.length; i += 1) {
    await seek(page, times[i]);
    const name = previewOnly
      ? `preview-${String(times[i]).padStart(5, "0")}.png`
      : `f${String(i).padStart(4, "0")}.png`;
    await page.screenshot({ path: path.join(FRAMES, name), type: "png" });
    if (i % 30 === 0) console.log("frame", i, "t", times[i]);
  }

  const sample = await page.evaluate(() => document.getAnimations().length);
  console.log("animations", sample, "frames", times.length);
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
