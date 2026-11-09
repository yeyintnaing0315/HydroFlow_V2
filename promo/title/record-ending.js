const { chromium } = require("../recorder/node_modules/playwright");
const fs = require("fs");
const path = require("path");

const PAGE = "file:///" + path.resolve(__dirname, "ending.html").replace(/\\/g, "/");
const FRAMES = path.join(__dirname, "ending-frames");
const FPS = 30;
const DURATION_MS = 6000;

async function seek(page, time) {
  await page.evaluate(async (t) => {
    for (const anim of document.getAnimations()) {
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
    if (!document.fonts.check('16px "Myanmar Text"', "ကျေးဇူးတင်ပါသည်")) {
      throw new Error("Myanmar Text did not load");
    }
  });
  await page.waitForFunction(() => document.getAnimations().length >= 3);

  if (process.argv.includes("--preview")) {
    await seek(page, 2000);
    await page.screenshot({ path: path.join(__dirname, "ending-preview.png"), type: "png" });
    await browser.close();
    return;
  }
  const frameCount = Math.round((DURATION_MS / 1000) * FPS);
  for (let i = 0; i < frameCount; i += 1) {
    await seek(page, (i * 1000) / FPS);
    await page.screenshot({
      path: path.join(FRAMES, `f${String(i).padStart(4, "0")}.png`),
      type: "png",
    });
    if (i % 30 === 0) console.log("frame", i);
  }
  console.log("frames", frameCount);
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
