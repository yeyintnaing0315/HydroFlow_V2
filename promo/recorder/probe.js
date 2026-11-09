const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto("http://127.0.0.1:5173/", { waitUntil: "domcontentloaded" });
  for (const seconds of [8, 20]) {
    await page.waitForTimeout(seconds === 8 ? 8000 : 12000);
    const count = await page.getByText("Flood chance").count();
    const loading = await page.getByText("Loading flood prediction").count();
    const error = await page.locator(".state.error").allTextContents();
    console.log(seconds, "chance", count, "loading", loading, "errors", error.slice(0, 3));
    await page.screenshot({ path: `D:\\Ai_Project\\HydroFlow_V2\\promo\\probe-${seconds}.png` });
  }
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
