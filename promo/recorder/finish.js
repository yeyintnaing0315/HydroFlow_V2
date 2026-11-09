const { chromium } = require("playwright");
const path = require("path");

const APP = "http://127.0.0.1:5173/";
const PHOTO = "D:\\Ai_Project\\HydroFlow_V2\\data\\inventory\\Raw\\Foods\\rice\\rice01.jpg";
const FRAMES = path.join(__dirname, "..", "frames");

function cards(body) {
  return `<!DOCTYPE html><html lang="my"><head><meta charset="utf-8" /><style>
  html, body { margin: 0; width: 1920px; height: 1080px; background: #0B1F33; color: #f4fbff; font-family: Pyidaungsu, "Myanmar Text", sans-serif; }
  .wrap { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 80px; }
  .rule { width: 180px; height: 4px; background: #14B8A6; border-radius: 4px; margin: 28px auto; }
  p { font-size: 42px; line-height: 1.55; margin: 10px 0; max-width: 1500px; }
  </style></head><body><div class="wrap">${body}</div></body></html>`;
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  page.setDefaultTimeout(20000);
  await page.addInitScript(() => {
    const boot = () => {
      if (document.getElementById("hf-sub")) return;
      const style = document.createElement("style");
      style.textContent = `#hf-sub { position: fixed; z-index: 2147483647; left: 50%; bottom: 28px; transform: translateX(-50%);
        width: max-content; max-width: 92%; padding: 12px 22px; border-radius: 10px; background: rgba(0,0,0,0.72); color: #fff;
        font-family: Pyidaungsu, "Myanmar Text", sans-serif; font-size: 30px; line-height: 1.45; text-align: center; pointer-events: none; }`;
      document.documentElement.appendChild(style);
      const sub = document.createElement("div");
      sub.id = "hf-sub";
      document.documentElement.appendChild(sub);
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
  });

  await page.goto(APP, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Inventory Management", exact: true }).click();
  await page.getByRole("button", { name: "+ Add Item" }).click();
  await page.getByRole("button", { name: /Detect Object/ }).first().click();
  const dialogSelect = page.getByRole("dialog").locator("select");
  await dialogSelect.selectOption("foods");
  await page.locator("input[accept='image/*']").setInputFiles(PHOTO);
  const detect = page.getByRole("dialog").getByRole("button", { name: "Detect Object", exact: true });
  await page.waitForTimeout(400);
  if (await detect.isEnabled()) await detect.click();
  await page.getByRole("button", { name: /Save detected/ }).waitFor({ timeout: 90000 }).catch(() => {});
  await page.evaluate((line) => { document.getElementById("hf-sub").textContent = line; },
    "ဓာတ်ပုံဖြင့် စားသောက်ကုန်၊ အဝတ်၊ မီးဖိုချောင်ပစ္စည်းနှင့် အသုံးအဆောင်ကို ရေတွက်သည်။");
  await page.screenshot({ path: path.join(FRAMES, "21-detect.png") });
  await page.evaluate((line) => { document.getElementById("hf-sub").textContent = line; },
    "လက်ကျန်မပြောင်းမီ အရေအတွက်ကို အတည်ပြုရသည်။");
  await page.screenshot({ path: path.join(FRAMES, "22-confirm.png") });
  console.log("detect-frames");

  await page.setContent(cards(`<p>ရာသီဥတုမှ မြို့နယ်အမှတ်၊ စီမံချက်၊ ပြီးနောက် သိုလှောင်ရုံအထိ။</p>`));
  await page.screenshot({ path: path.join(FRAMES, "23-workflow.png") });
  await page.setContent(cards(`
    <p>HydroFlow V2 သည် ကျောင်းပရောဂျက် နမူနာဖြစ်သည်။</p>
    <p>တရားဝင် ရေကြီးမှု သတိပေးချက် မဟုတ်ပါ။</p>
    <div class="rule"></div>
    <p>ပဲခူးတိုင်းအတွက် တည်ဆောက်ထားသည်။</p>
  `));
  await page.screenshot({ path: path.join(FRAMES, "24-close.png") });
  console.log("closing-frames");
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
