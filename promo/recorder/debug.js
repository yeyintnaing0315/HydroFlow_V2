const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  page.on("console", (msg) => console.log("CONSOLE", msg.type(), msg.text()));
  page.on("pageerror", (err) => console.log("PAGEERROR", err.message));
  page.on("requestfailed", (req) => console.log("FAIL", req.url(), req.failure()?.errorText));
  const response = await page.goto("http://127.0.0.1:5173/", { waitUntil: "networkidle", timeout: 60000 });
  console.log("STATUS", response && response.status());
  await page.waitForTimeout(5000);
  console.log("BODY", (await page.locator("body").innerText()).slice(0, 800));
  await page.screenshot({ path: "D:\\Ai_Project\\HydroFlow_V2\\promo\\debug-home.png" });
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
