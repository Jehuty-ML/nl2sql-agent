import { chromium } from "playwright";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, "..", "docs", "screenshots");
const BASE = process.env.SHOT_BASE || "http://127.0.0.1:6010/";

async function waitIdle(page, timeout = 120000) {
  await page.waitForFunction(
    () => {
      const send = document.querySelector("button.send");
      return send && !send.disabled && send.textContent?.includes("发送");
    },
    { timeout }
  );
}

async function waitAssistantTable(page, timeout = 120000) {
  await page.waitForSelector(".msg.assistant .table-wrap table, .msg.assistant .rich", {
    timeout,
  });
}

async function redactStatus(page) {
  // README 公开截图：隐藏具体模型 endpoint，避免泄露账号侧 ID
  await page.addStyleTag({
    content: `.status span:nth-child(3) { visibility: hidden !important; }`,
  });
}

async function clearAndGoto(page) {
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.evaluate(() => {
    localStorage.clear();
  });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector(".composer textarea");
  await redactStatus(page);
}

async function main() {
  const browser = await chromium.launch({
    channel: "msedge",
    headless: true,
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1.5,
  });

  await clearAndGoto(page);

  // 1) 主界面（欢迎引导 + 三栏布局）
  await page.waitForSelector(".msg");
  await page.waitForTimeout(600);
  await page.screenshot({
    path: path.join(OUT, "01-overview.png"),
    fullPage: false,
  });
  console.log("saved 01-overview.png");

  // 2) slash 固定分析：/dau → 数据表
  await page.locator(".hints button", { hasText: "/dau" }).click();
  await waitAssistantTable(page);
  await waitIdle(page);
  await page.waitForTimeout(800);
  await page.screenshot({
    path: path.join(OUT, "02-slash-dau.png"),
    fullPage: false,
  });
  console.log("saved 02-slash-dau.png");

  // 3) 自然语言 Agent：结论 + 建议 + Run Log
  await page.locator("button.new").click();
  await page.waitForTimeout(400);
  const nl =
    "最近一周日活大概怎样？完课和练习有没有一起掉？给两条可执行的运营建议。";
  await page.fill(".composer textarea", nl);
  await page.locator("button.send").click();
  await waitAssistantTable(page, 180000);
  await waitIdle(page, 180000);
  // 等右侧 Run Log 有步骤
  await page.waitForSelector(".rail .step", { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1000);
  await page.screenshot({
    path: path.join(OUT, "03-agent-nl.png"),
    fullPage: false,
  });
  console.log("saved 03-agent-nl.png");

  // 4) Run Log 特写（只截右侧栏，与全页图区分开）
  const steps = page.locator(".rail .step");
  const n = await steps.count();
  for (let i = 0; i < n; i++) {
    const t = await steps.nth(i).innerText();
    if (/SQL|查询|工具|观察|JSON|路由/i.test(t)) {
      await steps.nth(i).click();
      break;
    }
  }
  await page.waitForTimeout(400);
  await page.locator(".rail").screenshot({
    path: path.join(OUT, "04-run-log.png"),
  });
  console.log("saved 04-run-log.png (rail crop)");

  await browser.close();
  console.log("done →", OUT);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
