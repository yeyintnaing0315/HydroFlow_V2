const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const APP = "http://127.0.0.1:5173/";
const PHOTO = "D:\\Ai_Project\\HydroFlow_V2\\data\\inventory\\Raw\\Foods\\rice\\rice01.jpg";
const OUT_DIR = path.join(__dirname, "..", "clips");
const STORY_DATE = "2024-07-28";
const NEXT_DATE = "2024-07-29";

function cards(body) {
  return `<!DOCTYPE html>
<html lang="my">
<head>
<meta charset="utf-8" />
<style>
  html, body { margin: 0; width: 1920px; height: 1080px; background: #0B1F33; color: #f4fbff;
    font-family: Pyidaungsu, "Myanmar Text", "Noto Sans Myanmar", sans-serif; }
  .wrap { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 80px; }
  .rule { width: 180px; height: 4px; background: #14B8A6; border-radius: 4px; margin: 28px auto; }
  h1 { font-family: "Segoe UI", sans-serif; font-weight: 650; font-size: 84px; letter-spacing: 0.5px; margin: 0; }
  p { font-size: 42px; line-height: 1.55; margin: 10px 0; max-width: 1500px; }
  .small { margin-top: 36px; font-size: 28px; color: #9fd9cf; }
</style>
</head>
<body><div class="wrap">${body}</div></body>
</html>`;
}

function log(message) {
  console.log(`${new Date().toISOString()} ${message}`);
}

async function hold(page, ms) {
  await page.waitForTimeout(ms);
}

async function say(page, text, ms) {
  await page.evaluate((line) => {
    const node = document.getElementById("hf-sub");
    if (node) node.textContent = line;
  }, text);
  await hold(page, ms);
}

async function clearSub(page) {
  await page.evaluate(() => {
    const node = document.getElementById("hf-sub");
    if (node) node.textContent = "";
  });
}

async function glide(page, x, y) {
  await page.mouse.move(x, y, { steps: 28 });
}

async function setDate(page, locator, value) {
  await locator.evaluate((el, next) => {
    const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
    proto.set.call(el, next);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
  await page.waitForTimeout(400);
}

async function pointAt(page, locator) {
  const box = await locator.boundingBox();
  if (!box) return null;
  await glide(page, box.x + Math.min(box.width / 2, 180), box.y + box.height / 2);
  return box;
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: OUT_DIR, size: { width: 1920, height: 1080 } },
    reducedMotion: "reduce",
  });
  await context.addInitScript(() => {
    const boot = () => {
      if (document.getElementById("hf-sub")) return;
      const style = document.createElement("style");
      style.textContent = `
        #hf-cursor { position: fixed; z-index: 2147483646; width: 22px; height: 22px; margin: -11px 0 0 -11px;
          border: 3px solid #14B8A6; border-radius: 50%; background: rgba(20,184,166,0.25);
          box-shadow: 0 0 0 6px rgba(11,31,51,0.25); pointer-events: none; left: 80px; top: 80px; }
        #hf-sub { position: fixed; z-index: 2147483647; left: 50%; bottom: 42px; transform: translateX(-50%);
          max-width: 1500px; min-height: 0; padding: 14px 28px; border-radius: 10px;
          background: rgba(0,0,0,0.72); color: #fff; font-family: Pyidaungsu, "Myanmar Text", sans-serif;
          font-size: 34px; line-height: 1.45; text-align: center; pointer-events: none; }
        #hf-sub:empty { display: none; }
      `;
      document.documentElement.appendChild(style);
      const cursor = document.createElement("div");
      cursor.id = "hf-cursor";
      const sub = document.createElement("div");
      sub.id = "hf-sub";
      document.documentElement.appendChild(cursor);
      document.documentElement.appendChild(sub);
      window.addEventListener("mousemove", (event) => {
        cursor.style.left = `${event.clientX}px`;
        cursor.style.top = `${event.clientY}px`;
      }, true);
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
  });

  const page = await context.newPage();
  page.on("pageerror", (error) => console.log("PAGEERROR", error.message));
  page.setDefaultTimeout(120000);

  log("title");
  await page.setContent(cards(`
    <h1>HydroFlow V2</h1>
    <div class="rule"></div>
    <p>ပဲခူးတိုင်း ရေကြီးမှု အလားအလာ</p>
    <p>ကျောင်းပရောဂျက်</p>
    <p class="small">ပဲခူးတိုင်း</p>
  `));
  await hold(page, 12000);

  await page.setContent(cards(`<p>မိုးရာသီမှာ မိုးရေနှင့် မြစ်ရေ တစ်ပြိုင်နက် တက်နိုင်သည်။</p>`));
  await hold(page, 8000);
  await page.setContent(cards(`<p>မြို့နယ်ရုံးသည် ရာသီဥတု၊ လူဦးရေ၊ လမ်းနှင့် ကယ်ဆယ်ရေးပစ္စည်းကို ကြည့်ရသည်။</p>`));
  await hold(page, 8000);

  log("home");
  await page.goto(APP, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Flood Prediction" }).waitFor();
  await page.getByText("Flood chance").waitFor({ timeout: 20000 }).catch(() => log("home-still-loading"));
  await page.getByRole("button", { name: "Bago East" }).waitFor({ timeout: 20000 }).catch(() => log("inventory-still-loading"));
  await glide(page, 240, 220);
  await say(page, "စာမျက်နှာ လေးခု။ လုပ်ငန်းစဉ် တစ်ခုတည်း။", 6000);

  const route = page.getByRole("heading", { name: "Route map" });
  await route.scrollIntoViewIfNeeded();
  await pointAt(page, route);
  await say(page, "ပင်မစာမျက်နှာတွင် ယနေ့ ရေကြီးမှု၊ နမူနာလမ်းနှင့် ပစ္စည်းလက်ကျန်ကို ပြသည်။", 8000);

  const east = page.getByRole("button", { name: "Bago East" });
  if (await east.count()) {
    await east.scrollIntoViewIfNeeded();
    await pointAt(page, east);
    await east.click();
    await hold(page, 1200);
    const west = page.getByRole("button", { name: "Bago West" });
    await pointAt(page, west);
    await west.click();
    await hold(page, 1200);
  }
  await say(page, "ပစ္စည်းလက်ကျန်ကို ပဲခူးအရှေ့နှင့် ပဲခူးအနောက်အတွက် ခွဲပြသည်။", 8000);

  const predictNav = page.getByRole("button", { name: "Flood Prediction", exact: true });
  await pointAt(page, predictNav);
  await say(page, "နောက်တစ်ဆင့်။ ရေကြီးမှု ခန့်မှန်းချက်။", 6000);
  log("prediction");
  await predictNav.click();

  await page.locator("h2.prediction-panel-title").waitFor();
  const map = page.getByRole("region", { name: "Bago flood risk map" }).or(page.locator(".leaflet-container")).first();
  await map.waitFor();
  await page.getByRole("list", { name: "Flood risk bands" }).waitFor();
  await hold(page, 1500);
  const mapBox = await page.locator(".leaflet-container").boundingBox();
  if (mapBox) {
    await glide(page, mapBox.x + mapBox.width * 0.45, mapBox.y + mapBox.height * 0.55);
    await page.mouse.down();
    await glide(page, mapBox.x + mapBox.width * 0.62, mapBox.y + mapBox.height * 0.42);
    await page.mouse.up();
  }
  await say(page, "ပဲခူးတိုင်းမှ မြို့နယ် ၂၃ မြို့နယ်။", 6000);
  await say(page, "အရောင်သည် အန္တရာယ်အဆင့်ကို ပြသည်။ နိမ့်၊ အလယ်အလတ်၊ မြင့်၊ ပြင်းထန်။", 8000);

  const legend = page.getByRole("list", { name: "Flood risk bands" });
  await pointAt(page, legend);
  await say(page, "အမှတ်သည် မိုးရေနှင့် ပုံစံထုတ် မြစ်ရေစီးဆင်းမှုကို သုံးသည်။", 7000);
  await say(page, "ဒါသည် တိုင်းတာထားသော မြစ်ရေတံခါး မဟုတ်ပါ။", 6000);

  const township = page.getByLabel("Selected township");
  await pointAt(page, township);
  await township.selectOption({ label: "Bago" });
  await page.getByText("Flood chance").waitFor();
  await say(page, "မြို့နယ်ကို ရွေးပါ။ ထိုနေ့၏ ရေကြီးနိုင်ခြေကို ပြသည်။", 7000);

  const date = page.getByLabel("Selected date");
  await pointAt(page, date);
  await setDate(page, date, STORY_DATE);
  await page.getByRole("button", { name: "Plan resource allocation" }).waitFor({ timeout: 90000 }).catch(() => log("no-plan-button-yet"));
  await hold(page, 1500);
  await setDate(page, date, NEXT_DATE);
  await hold(page, 1800);
  await setDate(page, date, STORY_DATE);
  const past = page.getByRole("button", { name: "Previous 7 days" });
  await pointAt(page, past);
  await past.click();
  await say(page, "ရက်စွဲကို ရွှေ့ပြီး နေ့များကို နှိုင်းယှဉ်ပါ။", 6000);

  const planButton = page.getByRole("button", { name: "Plan resource allocation" });
  await page.evaluate((line) => {
    const node = document.getElementById("hf-sub");
    if (node) node.textContent = line;
  }, "မြင့်သောနေ့တွင် အရင်းအမြစ်စီမံချက်ကို ဆက်လုပ်သည်။");
  log("allocation");
  if (await planButton.count()) {
    await pointAt(page, planButton);
    await planButton.click();
  } else {
    const allocationNav = page.getByRole("button", { name: "Resource Allocation", exact: true });
    await pointAt(page, allocationNav);
    await allocationNav.click();
  }
  await hold(page, 6000);

  await page.getByRole("heading", { name: "Route map" }).waitFor();
  await hold(page, 1500);
  const people = page.getByText("Affected people").first();
  await pointAt(page, people);
  await say(page, "မြင့်သောမြို့နယ်အတွက် လူဦးရေနှင့် လိုအပ်သောပစ္စည်းကို ပြသည်။", 7000);
  await say(page, "ခိုလှုံရေး၊ စားနပ်ရိက္ခာနှင့် သောက်ရေကို သုံးရက်စာ ပုံဖော်သည်။", 7000);
  await say(page, "ဤအရေအတွက်သည် စီမံချက်ပုံဖြစ်သည်။ ကွင်းဆင်းစာရင်း မဟုတ်ပါ။", 7000);

  const floodHistory = page.getByText("Flood history", { exact: true });
  await floodHistory.scrollIntoViewIfNeeded();
  await pointAt(page, floodHistory);
  await floodHistory.click();
  await page.getByRole("heading", { name: "High & severe flood history" }).waitFor({ timeout: 30000 }).catch(() => {});
  await hold(page, 1500);
  await say(page, "မျဉ်းသည် မြို့နယ်ဗဟိုချက်များကြား နမူနာလမ်းကြောင်းဖြစ်သည်။", 7000);

  const inventoryNav = page.getByRole("button", { name: "Inventory Management", exact: true });
  await pointAt(page, inventoryNav);
  await say(page, "သိုလှောင်ရုံမှာ ရှိပြီးသားပစ္စည်းကို ဆက်ကြည့်သည်။", 6000);
  log("inventory");
  await inventoryNav.click();

  await page.getByRole("table", { name: "Inventory items" }).waitFor();
  await glide(page, 1100, 420);
  await say(page, "ကယ်ဆယ်ရေးပစ္စည်းလက်ကျန်ကို မျက်နှာပြင်တစ်ခုမှာ ထားသည်။", 6000);

  const add = page.getByRole("button", { name: "+ Add Item" });
  await pointAt(page, add);
  await add.click();
  const detectChoice = page.getByRole("button", { name: /Detect Object/ });
  await detectChoice.waitFor();
  await pointAt(page, detectChoice);
  await detectChoice.click();
  const classSelect = page.locator("select").filter({ has: page.locator("option[value='foods']") }).first();
  await classSelect.selectOption("foods");
  await page.locator("input[type='file'][accept='image/*']").setInputFiles(PHOTO);
  await hold(page, 800);
  const detectButton = page.getByRole("button", { name: "Detect Object", exact: true });
  await pointAt(page, detectButton);
  await say(page, "ဓာတ်ပုံဖြင့် စားသောက်ကုန်၊ အဝတ်၊ မီးဖိုချောင်ပစ္စည်းနှင့် အသုံးအဆောင်ကို ရေတွက်သည်။", 2000);
  await detectButton.click();
  const save = page.getByRole("button", { name: /Save detected/ });
  const failed = page.locator(".form-error");
  await Promise.race([
    save.waitFor({ timeout: 90000 }),
    failed.waitFor({ timeout: 90000 }),
  ]).catch(() => {});
  if (await save.count()) {
    await pointAt(page, save);
    await say(page, "လက်ကျန်မပြောင်းမီ အရေအတွက်ကို အတည်ပြုရသည်။", 6000);
  } else {
    await say(page, "လက်ကျန်မပြောင်းမီ အရေအတွက်ကို အတည်ပြုရသည်။", 4000);
    const close = page.getByRole("button", { name: "Close" });
    if (await close.count()) await close.click();
  }
  const close = page.getByRole("button", { name: "Close" });
  if (await close.count()) {
    await pointAt(page, close);
    await close.click();
  }
  await page.getByRole("table", { name: "Inventory items" }).waitFor();
  await say(page, "ရာသီဥတုမှ မြို့နယ်အမှတ်၊ စီမံချက်၊ ပြီးနောက် သိုလှောင်ရုံအထိ။", 8000);
  await clearSub(page);

  log("close");
  await page.setContent(cards(`
    <p>HydroFlow V2 သည် ကျောင်းပရောဂျက် နမူနာဖြစ်သည်။</p>
    <p>တရားဝင် ရေကြီးမှု သတိပေးချက် မဟုတ်ပါ။</p>
    <div class="rule"></div>
    <p>ပဲခူးတိုင်းအတွက် တည်ဆောက်ထားသည်။</p>
  `));
  await hold(page, 18000);

  const video = page.video();
  await context.close();
  await browser.close();
  if (video) {
    const saved = path.join(OUT_DIR, "hydroflow-raw.webm");
    await video.saveAs(saved);
    console.log(saved);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
