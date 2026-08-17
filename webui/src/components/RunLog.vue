<script setup lang="ts">
import { computed, nextTick, onUnmounted, reactive, ref, watch } from "vue";
import type { ProgressStep } from "../api";
import { renderFullContent } from "../pretty";

const props = defineProps<{
  sessionId: string;
  taskId: string | null;
  status: string;
  progress: ProgressStep[];
}>();

const expanded = reactive(new Set<number>());
const detailEls = ref<(HTMLElement | null)[]>([]);
const overflow = reactive(new Set<number>());
const railEl = ref<HTMLElement | null>(null);

const pinToBottom = ref(true);
let ignoreScrollEvent = false;
const NEAR_BOTTOM_PX = 48;

const DRAWER_W_KEY = "lumen_query_bench_drawer_w_v1";
const MIN_DRAWER_W = 360;
const MAX_DRAWER_W = () => Math.min(1200, Math.floor(window.innerWidth - 48));
const drawerW = ref(640);
const resizingDrawer = ref(false);

function loadDrawerWidth() {
  try {
    const n = Number(localStorage.getItem(DRAWER_W_KEY));
    if (Number.isFinite(n) && n >= MIN_DRAWER_W) {
      drawerW.value = Math.min(n, MAX_DRAWER_W());
    }
  } catch {
    /* ignore */
  }
}

function persistDrawerWidth() {
  try {
    localStorage.setItem(DRAWER_W_KEY, String(drawerW.value));
  } catch {
    /* ignore */
  }
}

function clampDrawerW(n: number) {
  return Math.min(MAX_DRAWER_W(), Math.max(MIN_DRAWER_W, Math.round(n)));
}

function startDrawerResize(e: PointerEvent) {
  e.preventDefault();
  e.stopPropagation();
  resizingDrawer.value = true;
  const target = e.currentTarget as HTMLElement;
  target.setPointerCapture(e.pointerId);

  const onMove = (ev: PointerEvent) => {
    // 左边框：宽度 = 视口右缘 - 指针 x（扣掉 overlay padding）
    const pad = 16;
    drawerW.value = clampDrawerW(window.innerWidth - pad - ev.clientX);
  };

  const onUp = (ev: PointerEvent) => {
    resizingDrawer.value = false;
    target.releasePointerCapture(ev.pointerId);
    target.removeEventListener("pointermove", onMove);
    target.removeEventListener("pointerup", onUp);
    target.removeEventListener("pointercancel", onUp);
    persistDrawerWidth();
  };

  target.addEventListener("pointermove", onMove);
  target.addEventListener("pointerup", onUp);
  target.addEventListener("pointercancel", onUp);
}

loadDrawerWidth();

/** 点开查看的全文抽屉（绑定当前 session，防串台） */
const viewer = ref<{ sessionId: string; step: string; body: string } | null>(null);

const viewerOpen = computed(
  () => Boolean(viewer.value && viewer.value.sessionId === props.sessionId)
);

const viewerHtml = computed(() => {
  if (!viewerOpen.value || !viewer.value) return "";
  return renderFullContent(viewer.value.body, viewer.value.step);
});

function resetLocalUi() {
  expanded.clear();
  overflow.clear();
  detailEls.value = [];
  pinToBottom.value = true;
  viewer.value = null;
}

function tone(step: string): string {
  if (/失败|错误/.test(step)) return "err";
  if (/完成|组织最终|导出/.test(step)) return "ok";
  if (/工具|SQL|固定分析|查询/.test(step)) return "tool";
  if (/想法|思考|决策|LLM|Agent/.test(step)) return "llm";
  return "";
}

function isLatest(i: number): boolean {
  return i === props.progress.length - 1;
}

function isCollapsed(i: number): boolean {
  if (isLatest(i)) return false;
  return overflow.has(i) && !expanded.has(i);
}

function stepBody(p: ProgressStep): string {
  return (p.full || p.detail || "").trim();
}

function isWaitingPlaceholder(p: ProgressStep): boolean {
  const d = (p.detail || "").trim();
  return /等待模型/.test(d) && !p.full;
}

function canOpen(p: ProgressStep): boolean {
  if (isWaitingPlaceholder(p)) return false;
  const body = stepBody(p);
  if (!body) return false;

  // 短决策 / 短参数：列表已够读，不挂「查看全文」
  if (/模型决策/.test(p.step) && body.length < 160 && !p.full) return false;
  if (/调用工具/.test(p.step) && !p.full && body.length < 160) return false;
  if (/^本轮无文字思考/.test(body)) return false;

  // LLM 思考：有 full（或足够长的正文）才可点开全文
  if (/LLM 思考|模型想法/.test(p.step)) {
    return Boolean(p.full) || body.length > 80;
  }

  // 工具返回 / SQL / 结论
  if (/工具返回|动态\s*SQL|组织最终|查询完成|固定分析/.test(p.step)) {
    return Boolean(p.full) || body.length > 80 || looksLikeOpenable(body);
  }

  return Boolean(
    p.full ||
      body.length > 120 ||
      /###|\|.*\||^\d+\.\s/m.test(body)
  );
}

function looksLikeOpenable(body: string): boolean {
  return /###|\|.*\||^\s*[\[{]/.test(body);
}

function openViewer(p: ProgressStep) {
  const body = stepBody(p);
  if (!body) return;
  viewer.value = { sessionId: props.sessionId, step: p.step, body };
  pinToBottom.value = false;
}

function closeViewer() {
  viewer.value = null;
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") closeViewer();
}

function toggleFold(i: number, e: Event) {
  e.stopPropagation();
  if (isLatest(i) || !overflow.has(i)) return;
  if (expanded.has(i)) expanded.delete(i);
  else expanded.add(i);
  void afterContentChange();
}

function isNearBottom(el: HTMLElement): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX;
}

function scrollToLatest() {
  const el = railEl.value;
  if (!el || !pinToBottom.value) return;
  ignoreScrollEvent = true;
  el.scrollTop = el.scrollHeight;
  requestAnimationFrame(() => {
    ignoreScrollEvent = false;
  });
}

function onRailScroll() {
  if (ignoreScrollEvent) return;
  const el = railEl.value;
  if (!el) return;
  pinToBottom.value = isNearBottom(el);
}

async function measureOverflow() {
  const sid = props.sessionId;
  overflow.clear();
  await nextTick();
  if (sid !== props.sessionId) return;
  const last = props.progress.length - 1;
  detailEls.value.forEach((el, i) => {
    if (!el || i === last) return;
    const lineHeight = parseFloat(getComputedStyle(el).lineHeight) || 16;
    const twoLines = lineHeight * 2 + 1;
    if (el.scrollHeight > twoLines) overflow.add(i);
  });
}

async function afterContentChange() {
  const sid = props.sessionId;
  await measureOverflow();
  await nextTick();
  if (sid !== props.sessionId) return;
  scrollToLatest();
}

watch(
  () => props.sessionId,
  () => {
    resetLocalUi();
  }
);

watch(
  () => [props.sessionId, props.taskId] as const,
  () => {
    expanded.clear();
    overflow.clear();
    pinToBottom.value = true;
    viewer.value = null;
  }
);

watch(
  () => props.progress.length,
  (len, prev) => {
    if (prev != null && len > prev) expanded.clear();
    void afterContentChange();
  },
  { immediate: true }
);

watch(
  () =>
    `${props.sessionId}|${props.taskId}|` +
    props.progress.map((p) => `${p.step}|${p.detail}|${p.full || ""}`).join("\n"),
  () => {
    void afterContentChange();
  }
);

watch(viewerOpen, (open) => {
  if (open) window.addEventListener("keydown", onKey);
  else window.removeEventListener("keydown", onKey);
});

onUnmounted(() => {
  window.removeEventListener("keydown", onKey);
  viewer.value = null;
});
</script>

<template>
  <aside ref="railEl" class="rail" @scroll.passive="onRailScroll">
    <h2>Run Log</h2>
    <div class="head">
      <div>task {{ taskId || "—" }}</div>
      <div class="st">{{ status || "idle" }}</div>
      <div v-if="!pinToBottom" class="follow-hint">已暂停跟随 · 滚回底部继续</div>
    </div>
    <div v-if="!progress?.length" class="empty">等待执行步骤…</div>
    <ol v-else>
      <li
        v-for="(p, i) in progress"
        :key="`${sessionId}-${taskId || 'none'}-${i}-${p.step}`"
        class="step"
        :class="[
          tone(p.step),
          {
            latest: isLatest(i),
            collapsed: isCollapsed(i),
            clickable: canOpen(p),
          },
        ]"
        @click="canOpen(p) && openViewer(p)"
      >
        <strong>
          {{ p.step }}
          <span v-if="canOpen(p)" class="open-hint">查看全文</span>
        </strong>
        <span
          v-if="p.detail"
          :ref="(el) => { detailEls[i] = el as HTMLElement | null }"
          class="detail"
          :class="{ clamp: isCollapsed(i) }"
        >{{ p.detail }}</span>
        <button
          v-if="overflow.has(i) && !isLatest(i)"
          type="button"
          class="fold"
          @click="toggleFold(i, $event)"
        >
          {{ expanded.has(i) ? "收起摘要" : "展开摘要" }}
        </button>
      </li>
    </ol>
  </aside>

  <Teleport to="body">
    <div
      v-if="viewerOpen && viewer"
      class="overlay"
      :class="{ resizing: resizingDrawer }"
      @click.self="closeViewer"
    >
      <div
        class="drawer"
        role="dialog"
        aria-modal="true"
        :style="{ width: drawerW + 'px' }"
      >
        <div
          class="drawer-resizer"
          role="separator"
          aria-orientation="vertical"
          aria-label="调整全文窗口宽度"
          title="拖拽调整宽度"
          @pointerdown="startDrawerResize"
        />
        <header class="drawer-head">
          <div>
            <div class="drawer-kicker">Run Log · 完整内容</div>
            <h3>{{ viewer.step }}</h3>
          </div>
          <button type="button" class="close" @click="closeViewer">关闭</button>
        </header>
        <div class="drawer-body rich" v-html="viewerHtml" />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.rail {
  background: rgba(251, 252, 249, 0.92);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  box-shadow: var(--shadow);
}

h2 {
  margin: 0 0 10px;
  font-family: var(--display);
  font-size: 1.15rem;
  color: var(--oak);
}

.head {
  font-size: 0.78rem;
  color: var(--muted);
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--line);
}

.st {
  margin-top: 2px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--amber-deep);
  font-weight: 600;
}

.follow-hint {
  margin-top: 4px;
  font-size: 0.7rem;
  color: var(--amber-deep);
}

.empty {
  color: var(--muted);
  font-style: italic;
  font-size: 0.85rem;
}

ol {
  margin: 0;
  padding-left: 0;
  list-style: none;
  display: grid;
  gap: 10px;
}

.step {
  font-size: 0.8rem;
  color: var(--muted);
  padding: 8px 9px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: rgba(255, 255, 255, 0.55);
}

.step.clickable {
  cursor: pointer;
}

.step.clickable:hover {
  border-color: var(--amber);
}

.step strong {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  color: var(--ink);
  font-weight: 650;
  margin-bottom: 4px;
  font-size: 0.82rem;
}

.open-hint {
  flex: none;
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--amber-deep);
  letter-spacing: 0.02em;
}

.step .detail {
  display: block;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.45;
  font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  font-size: 0.74rem;
  color: #4a574e;
}

.step .detail.clamp {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  white-space: normal;
}

.fold {
  margin-top: 4px;
  padding: 0;
  border: none;
  background: none;
  color: var(--amber-deep);
  font: inherit;
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.fold:hover {
  color: var(--ink);
}

.step.latest {
  border-color: #d8c49a;
  box-shadow: inset 2px 0 0 var(--amber);
}

.step.llm {
  border-color: #e6d4b0;
  background: #fffaf0;
}

.step.tool {
  border-color: #c9d7c4;
  background: #f4f8f2;
}

.step.ok {
  border-color: #c5d9c8;
  background: #f2f7f3;
}

.step.err {
  border-color: #e4c4c4;
  background: #fbf3f3;
}

.overlay {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: rgba(28, 32, 26, 0.35);
  display: flex;
  justify-content: flex-end;
  padding: 16px;
}

.overlay.resizing {
  cursor: col-resize;
  user-select: none;
}

.overlay.resizing * {
  cursor: col-resize !important;
  user-select: none !important;
}

.drawer {
  position: relative;
  width: min(640px, 100%);
  max-width: calc(100vw - 32px);
  max-height: 100%;
  background: #fffcf7;
  border: 1px solid var(--line);
  border-radius: 12px;
  box-shadow: 0 18px 50px rgba(30, 28, 20, 0.22);
  display: grid;
  grid-template-rows: auto 1fr;
  overflow: hidden;
}

.drawer-resizer {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -2px;
  width: 10px;
  z-index: 3;
  cursor: col-resize;
  touch-action: none;
}

.drawer-resizer::after {
  content: "";
  position: absolute;
  top: 18%;
  bottom: 18%;
  left: 4px;
  width: 3px;
  border-radius: 3px;
  background: transparent;
  transition: background 0.15s ease;
}

.drawer-resizer:hover::after,
.overlay.resizing .drawer-resizer::after {
  background: var(--amber);
}

.drawer-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding: 14px 16px;
  border-bottom: 1px solid var(--line);
  background: #f7f4ee;
}

.drawer-kicker {
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 4px;
}

.drawer-head h3 {
  margin: 0;
  font-size: 1rem;
  color: var(--oak);
  font-family: var(--display);
}

.close {
  border: 1px solid var(--line);
  background: #fff;
  border-radius: 8px;
  padding: 6px 10px;
  font: inherit;
  font-size: 0.8rem;
  cursor: pointer;
}

.close:hover {
  border-color: var(--amber);
}

.drawer-body {
  overflow: auto;
  padding: 16px 18px 24px;
  font-size: 0.92rem;
  line-height: 1.55;
}

.rich :deep(.md-h3),
.rich :deep(.md-h4) {
  margin: 14px 0 8px;
  font-size: 1rem;
  font-weight: 650;
  color: #1f2a22;
}

.rich :deep(.md-h3:first-child),
.rich :deep(.md-h4:first-child) {
  margin-top: 0;
}

.rich :deep(.md-p),
.rich :deep(.md-li) {
  margin: 0 0 6px;
}

.rich :deep(.md-muted) {
  margin: 4px 0 0;
  font-size: 0.75rem;
  color: var(--muted);
}

.rich :deep(.md-hr) {
  border: none;
  border-top: 1px solid var(--line);
  margin: 14px 0;
}

.rich :deep(strong) {
  font-weight: 650;
}

.rich :deep(.meta-chips) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.rich :deep(.chip) {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eef3ea;
  border: 1px solid #d5e0d0;
  font-size: 0.72rem;
  font-weight: 600;
  color: #2f4034;
}

.rich :deep(.callout) {
  padding: 10px 12px;
  border-radius: 8px;
  margin: 0 0 12px;
  font-size: 0.86rem;
  line-height: 1.45;
}

.rich :deep(.callout.err) {
  background: #fbf1f1;
  border: 1px solid #e8c8c8;
  color: #6b2e2e;
}

.rich :deep(.callout.hint) {
  background: #fff8eb;
  border: 1px solid #ebd7b0;
  color: #5c4520;
}

.rich :deep(.code-block) {
  margin: 8px 0 14px;
  border: 1px solid #d8d3c8;
  border-radius: 10px;
  overflow: hidden;
  background: #1e2420;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.rich :deep(.code-bar) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background: #2a322c;
  color: #c5d0c4;
  font-size: 0.68rem;
  font-weight: 650;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.rich :deep(.code) {
  margin: 0;
  padding: 12px 14px;
  overflow: auto;
  max-height: min(52vh, 520px);
  font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  font-size: 0.78rem;
  line-height: 1.55;
  color: #e7eee6;
  white-space: pre;
}

.rich :deep(.code.wrap),
.rich :deep(.code-block[data-lang="sql"] .code) {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.rich :deep(.tok-kw) {
  color: #7ec8ff;
  font-weight: 650;
}

.rich :deep(.tok-str) {
  color: #c6e59a;
}

.rich :deep(.tok-key) {
  color: #9fd0ff;
}

.rich :deep(.tok-num) {
  color: #f0c674;
}

.rich :deep(.tok-bool) {
  color: #e8a0c8;
}

.rich :deep(.tok-cmt) {
  color: #8a9688;
  font-style: italic;
}

.rich :deep(.tok-punc) {
  color: #aeb8ac;
}

.rich :deep(.table-scroll) {
  margin: 10px 0 14px;
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
}

.rich :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.84rem;
  min-width: 280px;
}

.rich :deep(th),
.rich :deep(td) {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}

.rich :deep(th) {
  background: #f4f6f1;
  font-weight: 600;
}

.rich :deep(.doc-think) {
  font-size: 0.9rem;
  line-height: 1.65;
  color: #2a332c;
}

.rich :deep(.doc-think .md-p),
.rich :deep(.doc-think .md-li) {
  margin: 0 0 10px;
}

.rich :deep(.doc-think .md-h3),
.rich :deep(.doc-think .md-h4) {
  margin: 18px 0 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #e6e0d4;
  color: var(--oak);
  font-family: var(--display);
}

.rich :deep(.doc-think .md-h3:first-child),
.rich :deep(.doc-think .md-h4:first-child) {
  margin-top: 0;
}

.rich :deep(.doc-think code) {
  font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  font-size: 0.84em;
  padding: 0.1em 0.35em;
  border-radius: 4px;
  background: #eef2ea;
  border: 1px solid #d8e0d4;
}

.rich :deep(.doc-json .md-h4) {
  margin: 16px 0 8px;
  color: var(--oak);
  font-family: var(--display);
}

.rich :deep(.doc-json .md-h4:first-of-type) {
  margin-top: 4px;
}
</style>

<!-- Teleport 到 body 时补一份非 scoped，避免个别环境下深选择器未命中导致「像纯文本 JSON」 -->
<style>
.overlay .drawer-body.rich {
  white-space: normal;
  color: #2a332c;
}
.overlay .drawer-body.rich .meta-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}
.overlay .drawer-body.rich .chip {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eef3ea;
  border: 1px solid #d5e0d0;
  font-size: 0.72rem;
  font-weight: 600;
  color: #2f4034;
}
.overlay .drawer-body.rich .code-block {
  margin: 8px 0 14px;
  border: 1px solid #d8d3c8;
  border-radius: 10px;
  overflow: hidden;
  background: #1e2420;
}
.overlay .drawer-body.rich .code-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background: #2a322c;
  color: #c5d0c4;
  font-size: 0.68rem;
  font-weight: 650;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.overlay .drawer-body.rich .code {
  margin: 0;
  padding: 12px 14px;
  overflow: auto;
  max-height: min(52vh, 520px);
  font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  font-size: 0.78rem;
  line-height: 1.55;
  color: #e7eee6;
  white-space: pre;
}
.overlay .drawer-body.rich .code.wrap,
.overlay .drawer-body.rich .code-block[data-lang="sql"] .code {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.overlay .drawer-body.rich .tok-kw {
  color: #7ec8ff;
  font-weight: 650;
}
.overlay .drawer-body.rich .tok-str {
  color: #c6e59a;
}
.overlay .drawer-body.rich .tok-num {
  color: #f0c674;
}
.overlay .drawer-body.rich .table-scroll {
  margin: 10px 0 14px;
  overflow-x: auto;
  border: 1px solid #e0dcd2;
  border-radius: 8px;
  background: #fff;
}
.overlay .drawer-body.rich table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.84rem;
  min-width: 280px;
}
.overlay .drawer-body.rich th,
.overlay .drawer-body.rich td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid #e0dcd2;
  white-space: nowrap;
}
.overlay .drawer-body.rich th {
  background: #f4f6f1;
  font-weight: 600;
}
.overlay .drawer-body.rich .md-h4 {
  margin: 16px 0 8px;
  font-size: 1rem;
  font-weight: 650;
  color: #5c4030;
}
</style>
