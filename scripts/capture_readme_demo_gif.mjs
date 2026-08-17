/**
 * 录制 README 演示 GIF：/dau → 出表 → 自然语言 → Run Log。
 * 依赖：本机 Edge + playwright + ffmpeg；后端 http://127.0.0.1:6010/
 *
 *   npm i -D playwright
 *   node .\scripts\capture_readme_demo_gif.mjs
 */
import path from "path";
import fs from "fs";
import { fileURLToPath, pathToFileURL } from "url";
import { spawnSync } from "child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const OUT_DIR = path.join(ROOT, "docs", "screenshots");
const TMP = path.join(OUT_DIR, "_gif_tmp");
const BASE = process.env.SHOT_BASE || "http://127.0.0.1:6010/";
const GIF = path.join(OUT_DIR, "05-demo.gif");

async function loadChromium() {
  const candidates = [
    path.join(ROOT, "node_modules", "playwright", "index.mjs"),
    path.join(ROOT, ".scratch_pw", "node_modules", "playwright", "index.mjs"),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) {
      const mod = await import(pathToFileURL(p).href);
      return mod.chromium;
    }
  }
  throw new Error("未找到 playwright，请先: npm i -D playwright");
}

function sh(cmd, args) {
  const r = spawnSync(cmd, args, { stdio: "inherit", shell: false });
  if (r.status !== 0) throw new Error(`${cmd} failed: ${r.status}`);
}

async function waitIdle(page, timeout = 180000) {
  await page.waitForFunction(
    () => {
      const send = document.querySelector("button.send");
      return !!send && !send.disabled && (send.textContent || "").includes("发送");
    },
    null,
    { timeout }
  );
}

async function waitTableOrRich(page, timeout = 180000) {
  await page.waitForSelector(
    ".msg.assistant .table-wrap table, .msg.assistant .rich",
    { timeout }
  );
}

async function main() {
  const chromium = await loadChromium();
  fs.mkdirSync(TMP, { recursive: true });
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch({
    channel: "msedge",
    headless: true,
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
    recordVideo: { dir: TMP, size: { width: 1280, height: 800 } },
  });
  const page = await context.newPage();

  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
  await page.addStyleTag({
    content: `.status span:nth-child(3) { visibility: hidden !important; }`,
  });
  await page.waitForSelector(".composer textarea");
  await page.waitForTimeout(900);

  // slash
  await page.locator(".hints button", { hasText: "/dau" }).click();
  await waitTableOrRich(page, 90000);
  await waitIdle(page, 90000);
  await page.waitForTimeout(1200);

  // natural language
  await page.locator("button.new").click();
  await page.waitForTimeout(400);
  const nl = "最近一周日活大概怎样？给两条可执行的运营建议。";
  await page.fill(".composer textarea", nl);
  await page.waitForTimeout(400);
  await page.locator("button.send").click();
  await page.waitForSelector(".rail .step", { timeout: 90000 });
  await waitTableOrRich(page, 180000);
  await waitIdle(page, 180000);
  await page.waitForTimeout(1500);

  await context.close();
  await browser.close();

  const videos = fs.readdirSync(TMP).filter((f) => f.endsWith(".webm"));
  if (!videos.length) throw new Error("no webm recorded");
  const webm = path.join(TMP, videos[0]);
  const sped = path.join(TMP, "sped.mp4");
  const palette = path.join(TMP, "palette.png");

  // ~3× 加速，压到约 10–15s；宽度 960，控制体积
  sh("ffmpeg", [
    "-y",
    "-i",
    webm,
    "-filter:v",
    "setpts=0.33*PTS,fps=12,scale=960:-1:flags=lanczos",
    "-an",
    sped,
  ]);
  sh("ffmpeg", [
    "-y",
    "-i",
    sped,
    "-vf",
    "palettegen=stats_mode=diff",
    palette,
  ]);
  sh("ffmpeg", [
    "-y",
    "-i",
    sped,
    "-i",
    palette,
    "-lavfi",
    "paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
    "-loop",
    "0",
    GIF,
  ]);

  for (const f of fs.readdirSync(TMP)) {
    fs.unlinkSync(path.join(TMP, f));
  }
  fs.rmdirSync(TMP);

  const mb = (fs.statSync(GIF).size / (1024 * 1024)).toFixed(2);
  console.log(`saved ${GIF} (${mb} MB)`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
