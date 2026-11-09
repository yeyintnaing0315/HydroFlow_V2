const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const APP = "http://127.0.0.1:5173/";
const PHOTO = "D:\\Ai_Project\\HydroFlow_V2\\data\\inventory\\Raw\\Foods\\rice\\rice01.jpg";
const FRAMES = path.join(__dirname, "..", "frames");
const STORY_DATE = "2024-07-28";
const NEXT_DATE = "2024-07-29";
const frames = [];

function cards(body) {
  return `<!DOCTYPE html>
<html lang="my"><head><meta charset="utf-8" />
<style>
  html, body { margin: 0; width: 1920px; height: 1080px; background: #0B1F33; color: #f4fbff;
    font-family: Pyidaungsu, "Myanmar Text", sans-serif; }
  .wrap { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 80px; }
  .rule { width: 180px; height: 4px; background: #14B8A6; border-radius: 4px; margin: 28px auto; }
  h1 { font-family: "Segoe UI", sans-serif; font-weight: 650; font-size: 84px; margin: 0; }
  p { font-size: 42px; line-height: 1.55; margin: 10px 0; max-width: 1500px; }
  .small { margin-top: 36px; font-size: 28px; color: #9fd9cf; }
</style></head><body><div class="wrap">${body}</div></body></html>`;
}

async function shot(page, name, seconds) {
  const file = path.join(FRAMES, `${name}.png`);
  await page.screenshot({ path: file });
  frames.push({ file: file.replace(/\\/g, "/"), seconds });
  console.log("frame", name, seconds);
}

async function say(page, text) {
  await page.evaluate((line) => {
    const node = document.getElementById("hf-sub");
    if (node) node.textContent = line;
  }, text);
}

async function glide(page, locator) {
  const box = await locator.boundingBox().catch(() => null);
  if (!box) return;
  await page.mouse.move(box.x + Math.min(box.width / 2, 160), box.y + box.height / 2, { steps: 12 });
}

async function setDate(locator, value) {
  await locator.evaluate((el, next) => {
    const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
    proto.set.call(el, next);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
}

async function main() {
  fs.mkdirSync(FRAMES, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  page.setDefaultTimeout(30000);
  await page.addInitScript(() => {
    const boot = () => {
      if (document.getElementById("hf-sub")) return;
      const style = document.createElement("style");
      style.textContent = `
        #hf-cursor { position: fixed; z-index: 2147483646; width: 22px; height: 22px; margin: -11px 0 0 -11px;
          border: 3px solid #14B8A6; border-radius: 50%; background: rgba(20,184,166,0.25); pointer-events: none; left: -40px; top: -40px; }
        #hf-sub { position: fixed; z-index: 2147483647; left: 50%; bottom: 28px; transform: translateX(-50%);
          width: max-content; max-width: 92%; padding: 12px 22px; border-radius: 10px; background: rgba(0,0,0,0.72); color: #fff;
          font-family: Pyidaungsu, "Myanmar Text", sans-serif; font-size: 30px; line-height: 1.45; text-align: center; pointer-events: none; }
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

  await page.setContent(cards(`
    <h1>HydroFlow V2</h1><div class="rule"></div>
    <p>ပဲခူးတိုင်း ရေကြီးမှု အလားအလာ</p>
    <p>ကျောင်းပရောဂျက်</p>
    <p class="small">ပဲခူးတိုင်း</p>
  `));
  await shot(page, "01-title", 12);

  await page.setContent(cards(`<p>မိုးရာသီမှာ မိုးရေနှင့် မြစ်ရေ တစ်ပြိုင်နက် တက်နိုင်သည်။</p>`));
  await shot(page, "02-monsoon", 8);
  await page.setContent(cards(`<p>မြို့နယ်ရုံးသည် ရာသီဥတု၊ လူဦးရေ၊ လမ်းနှင့် ကယ်ဆယ်ရေးပစ္စည်းကို ကြည့်ရသည်။</p>`));
  await shot(page, "03-office", 8);

  await page.goto(APP, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Flood Prediction" }).first().waitFor();
  await page.getByText("Flood chance").first().waitFor({ timeout: 40000 }).catch(() => {});
  await page.getByRole("button", { name: "Bago East" }).first().waitFor({ timeout: 15000 }).catch(() => {});
  const nav = page.getByRole("button", { name: "Flood Prediction", exact: true });
  await glide(page, nav);
  await say(page, "စာမျက်နှာ လေးခု။ လုပ်ငန်းစဉ် တစ်ခုတည်း။");
  await shot(page, "04-home", 6);

  const route = page.getByRole("heading", { name: "Route map" }).first();
  await route.scrollIntoViewIfNeeded().catch(() => {});
  await glide(page, route);
  await say(page, "ပင်မစာမျက်နှာတွင် ယနေ့ ရေကြီးမှု၊ နမူနာလမ်းနှင့် ပစ္စည်းလက်ကျန်ကို ပြသည်။");
  await shot(page, "05-home-route", 8);

  const east = page.getByRole("button", { name: "Bago East" }).first();
  if (await east.count()) {
    await east.click();
    await page.waitForTimeout(600);
    await page.getByRole("button", { name: "Bago West" }).first().click();
    await page.waitForTimeout(600);
  }
  await glide(page, east);
  await say(page, "ပစ္စည်းလက်ကျန်ကို ပဲခူးအရှေ့နှင့် ပဲခူးအနောက်အတွက် ခွဲပြသည်။");
  await shot(page, "06-depots", 8);

  await glide(page, nav);
  await say(page, "နောက်တစ်ဆင့်။ ရေကြီးမှု ခန့်မှန်းချက်။");
  await shot(page, "07-to-prediction", 6);
  await nav.click();
  await page.locator(".leaflet-container").first().waitFor();
  await page.waitForTimeout(2500);
  const map = page.locator(".leaflet-container").first();
  const mapBox = await map.boundingBox();
  if (mapBox) await page.mouse.move(mapBox.x + mapBox.width * 0.55, mapBox.y + mapBox.height * 0.48, { steps: 8 });
  await say(page, "ပဲခူးတိုင်းမှ မြို့နယ် ၂၃ မြို့နယ်။");
  await shot(page, "08-map", 6);

  const legend = page.getByRole("list", { name: "Flood risk bands" }).first();
  await glide(page, legend);
  await say(page, "အရောင်သည် အန္တရာယ်အဆင့်ကို ပြသည်။ နိမ့်၊ အလယ်အလတ်၊ မြင့်၊ ပြင်းထန်။");
  await shot(page, "09-bands", 8);
  await say(page, "အမှတ်သည် မိုးရေနှင့် ပုံစံထုတ် မြစ်ရေစီးဆင်းမှုကို သုံးသည်။");
  await shot(page, "10-inputs", 7);
  await say(page, "ဒါသည် တိုင်းတာထားသော မြစ်ရေတံခါး မဟုတ်ပါ။");
  await shot(page, "11-not-gauge", 6);

  const township = page.getByLabel("Selected township").first();
  await township.selectOption({ label: "Bago" }).catch(() => {});
  const date = page.getByLabel("Selected date").first();
  await glide(page, date);
  await setDate(date, STORY_DATE);
  await page.getByRole("button", { name: "Plan resource allocation" }).first().waitFor({ timeout: 90000 }).catch(() => {});
  await page.waitForTimeout(800);
  await say(page, "မြို့နယ်ကို ရွေးပါ။ ထိုနေ့၏ ရေကြီးနိုင်ခြေကို ပြသည်။");
  await shot(page, "12-bago-severe", 7);

  await setDate(date, NEXT_DATE);
  await page.waitForTimeout(1200);
  await page.getByRole("button", { name: "Previous 7 days" }).first().click().catch(() => {});
  await say(page, "ရက်စွဲကို ရွှေ့ပြီး နေ့များကို နှိုင်းယှဉ်ပါ။");
  await shot(page, "13-compare-dates", 6);

  await setDate(date, STORY_DATE);
  await page.getByRole("button", { name: "Plan resource allocation" }).first().waitFor({ timeout: 90000 }).catch(() => {});
  const planButton = page.getByRole("button", { name: "Plan resource allocation" }).first();
  await say(page, "မြင့်သောနေ့တွင် အရင်းအမြစ်စီမံချက်ကို ဆက်လုပ်သည်။");
  await shot(page, "14-plan-button", 6);
  if (await planButton.count()) await planButton.click();
  else await page.getByRole("button", { name: "Resource Allocation", exact: true }).click();
  await page.getByRole("heading", { name: "Route map" }).first().waitFor({ timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(1500);

  const people = page.getByText("Affected people").first();
  await glide(page, people);
  await say(page, "မြင့်သောမြို့နယ်အတွက် လူဦးရေနှင့် လိုအပ်သောပစ္စည်းကို ပြသည်။");
  await shot(page, "15-people", 7);
  await say(page, "ခိုလှုံရေး၊ စားနပ်ရိက္ခာနှင့် သောက်ရေကို သုံးရက်စာ ပုံဖော်သည်။");
  await shot(page, "16-package", 7);
  await say(page, "ဤအရေအတွက်သည် စီမံချက်ပုံဖြစ်သည်။ ကွင်းဆင်းစာရင်း မဟုတ်ပါ။");
  await shot(page, "17-illustration", 7);

  const floodHistory = page.getByText("Flood history", { exact: true }).first();
  await floodHistory.click().catch(() => {});
  await page.waitForTimeout(1000);
  await glide(page, page.locator(".leaflet-container").first());
  await say(page, "မျဉ်းသည် မြို့နယ်ဗဟိုချက်များကြား နမူနာလမ်းကြောင်းဖြစ်သည်။");
  await shot(page, "18-route", 7);

  const inventoryNav = page.getByRole("button", { name: "Inventory Management", exact: true });
  await glide(page, inventoryNav);
  await say(page, "သိုလှောင်ရုံမှာ ရှိပြီးသားပစ္စည်းကို ဆက်ကြည့်သည်။");
  await shot(page, "19-to-stock", 6);
  await inventoryNav.click();
  await page.getByRole("table", { name: "Inventory items" }).waitFor({ timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(800);
  await say(page, "ကယ်ဆယ်ရေးပစ္စည်းလက်ကျန်ကို မျက်နှာပြင်တစ်ခုမှာ ထားသည်။");
  await shot(page, "20-stock", 6);

  const add = page.getByRole("button", { name: "+ Add Item" }).first();
  if (await add.count()) {
    await add.click();
    const detectChoice = page.getByRole("button", { name: /Detect Object/ }).first();
    await detectChoice.waitFor({ timeout: 10000 }).catch(() => {});
    if (await detectChoice.count()) {
      await detectChoice.click();
      const selects = page.locator("select");
      const selectCount = await selects.count();
      for (let index = 0; index < selectCount; index += 1) {
        if (await selects.nth(index).locator("option[value='foods']").count()) {
          await selects.nth(index).selectOption("foods");
          break;
        }
      }
      await page.locator("input[accept='image/*']").setInputFiles(PHOTO);
      const detectButton = page.getByRole("button", { name: "Detect Object", exact: true }).last();
      await page.waitForTimeout(500);
      if (await detectButton.isEnabled()) await detectButton.click();
      await page.getByRole("button", { name: /Save detected/ }).first().waitFor({ timeout: 90000 }).catch(() => {});
    }
  }
  await say(page, "ဓာတ်ပုံဖြင့် စားသောက်ကုန်၊ အဝတ်၊ မီးဖိုချောင်ပစ္စည်းနှင့် အသုံးအဆောင်ကို ရေတွက်သည်။");
  await shot(page, "21-detect", 8);
  const save = page.getByRole("button", { name: /Save detected/ }).first();
  if (await save.count()) await glide(page, save);
  await say(page, "လက်ကျန်မပြောင်းမီ အရေအတွက်ကို အတည်ပြုရသည်။");
  await shot(page, "22-confirm", 6);
  const close = page.getByRole("button", { name: "Close" }).first();
  if (await close.count()) await close.click();
  await page.waitForTimeout(500);
  await say(page, "ရာသီဥတုမှ မြို့နယ်အမှတ်၊ စီမံချက်၊ ပြီးနောက် သိုလှောင်ရုံအထိ။");
  await shot(page, "23-workflow", 8);

  await page.setContent(cards(`
    <p>HydroFlow V2 သည် ကျောင်းပရောဂျက် နမူနာဖြစ်သည်။</p>
    <p>တရားဝင် ရေကြီးမှု သတိပေးချက် မဟုတ်ပါ။</p>
    <div class="rule"></div>
    <p>ပဲခူးတိုင်းအတွက် တည်ဆောက်ထားသည်။</p>
  `));
  await shot(page, "24-close", 18);

  fs.writeFileSync(path.join(FRAMES, "frames.json"), JSON.stringify(frames, null, 2));
  await browser.close();
  console.log("frames", frames.length);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
