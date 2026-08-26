/**
 * 重拍 README 截图（需本机 Edge + playwright；后端默认 http://127.0.0.1:6010/）。
 *
 *   npm i -D playwright --prefix .scratch_pw
 *   node .\scripts\capture_readme_shots.mjs
 */
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";
import { createRequire } from "module";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const OUT = path.resolve(ROOT, "docs", "screenshots");
const BASE = process.env.SHOT_BASE || "http://127.0.0.1:6010/";

const require = createRequire(import.meta.url);
function loadPlaywright() {
  try {
    return require("playwright");
  } catch {
    return require(path.join(ROOT, ".scratch_pw", "node_modules", "playwright"));
  }
}
const { chromium } = loadPlaywright();

async function waitIdle(page, timeout = 120000) {
  await page.waitForFunction(
    () => {
      const send = document.querySelector("button.send");
      return send && !send.disabled && send.textContent?.includes("发送");
    },
    { timeout }
  );
}

async function waitAssistantDone(page, timeout = 180000) {
  await page.waitForSelector(".msg.assistant .table-wrap table, .msg.assistant .rich", {
    timeout,
  });
  await waitIdle(page, timeout);
}

async function redactStatus(page) {
  await page.addStyleTag({
    content: `.status span:nth-child(3) { visibility: hidden !important; }`,
  });
}

async function clearAndGoto(page) {
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector(".composer textarea");
  await redactStatus(page);
}

async function openFullViewer(page, prefer = /工具返回|动态\s*SQL|LLM 思考/i) {
  const steps = page.locator(".rail .step.clickable");
  const n = await steps.count();
  let target = null;
  for (let i = 0; i < n; i++) {
    const el = steps.nth(i);
    const t = await el.innerText();
    if (prefer.test(t) && /查看全文/.test(t)) {
      target = el;
      if (/工具返回|动态\s*SQL/i.test(t)) break;
    }
  }
  if (!target && n > 0) {
    for (let i = n - 1; i >= 0; i--) {
      const el = steps.nth(i);
      const t = await el.innerText();
      if (/查看全文/.test(t)) {
        target = el;
        break;
      }
    }
  }
  if (!target) throw new Error("no clickable Run Log step with 查看全文");
  await target.click();
  await page.waitForSelector(".overlay .drawer", { timeout: 10000 });
  await page.waitForTimeout(500);
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    channel: "msedge",
    headless: true,
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1.5,
  });

  await clearAndGoto(page);

  // 1) 主界面
  await page.waitForSelector(".msg");
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(OUT, "01-overview.png"), fullPage: false });
  console.log("saved 01-overview.png");

  // 2) slash /dau（固定看板：表 + 图 + 报告产物）
  await page.locator(".hints button", { hasText: "/dau" }).click();
  await waitAssistantDone(page);
  // 等图表渲染进消息（有则更好；无图也不阻塞截图）
  await page
    .waitForSelector(".msg.assistant .md-img, .msg.assistant .artifacts .art-btn-chart", {
      timeout: 30000,
    })
    .catch(() => {});
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "02-slash-dau.png"), fullPage: false });
  console.log("saved 02-slash-dau.png");

  // 3) 自然语言（会走工具，Run Log 含查看全文）
  await page.locator("button.new").click();
  await page.waitForTimeout(400);
  const nl =
    "最近一周日活大概怎样？完课和练习有没有一起掉？给两条可执行的运营建议。";
  await page.fill(".composer textarea", nl);
  await page.locator("button.send").click();
  await waitAssistantDone(page, 180000);
  await page.waitForSelector(".rail .step", { timeout: 30000 });
  // 等到出现可点开全文的步骤
  await page
    .waitForFunction(
      () =>
        [...document.querySelectorAll(".rail .step")].some((el) =>
          /查看全文/.test(el.textContent || "")
        ),
      { timeout: 60000 }
    )
    .catch(() => {});
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "03-agent-nl.png"), fullPage: false });
  console.log("saved 03-agent-nl.png");

  // 4a) Run Log 栏：可见「查看全文」
  const rail = page.locator(".rail");
  await rail.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  await page.waitForTimeout(300);
  // 滚到带查看全文的步骤附近
  const hint = page.locator(".rail .step.clickable .open-hint").first();
  if (await hint.count()) {
    await hint.scrollIntoViewIfNeeded();
    await page.waitForTimeout(200);
  }
  await rail.screenshot({ path: path.join(OUT, "04-run-log.png") });
  console.log("saved 04-run-log.png (rail with 查看全文)");

  // 4b) 点开全文抽屉：SQL / 结果表美化
  await openFullViewer(page);
  await page.screenshot({
    path: path.join(OUT, "04b-run-log-viewer.png"),
    fullPage: false,
  });
  console.log("saved 04b-run-log-viewer.png (drawer open)");

  await browser.close();
  console.log("done →", OUT);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
