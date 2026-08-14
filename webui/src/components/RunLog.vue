<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from "vue";
import type { ProgressStep } from "../api";
import { renderMarkdown } from "../markdown";

const props = defineProps<{
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

/** 点开查看的全文抽屉 */
const viewer = ref<{ step: string; body: string } | null>(null);

const viewerHtml = computed(() =>
  viewer.value ? renderMarkdown(viewer.value.body) : ""
);

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

function canOpen(p: ProgressStep): boolean {
  const body = stepBody(p);
  if (!body) return false;
  // 有 full，或正文较长 / 含 Markdown 结构
  return Boolean(
    p.full ||
      body.length > 120 ||
      /###|\|.*\||^\d+\.\s/m.test(body)
  );
}

function openViewer(p: ProgressStep) {
  const body = stepBody(p);
  if (!body) return;
  viewer.value = { step: p.step, body };
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
  overflow.clear();
  await nextTick();
  const last = props.progress.length - 1;
  detailEls.value.forEach((el, i) => {
    if (!el || i === last) return;
    const lineHeight = parseFloat(getComputedStyle(el).lineHeight) || 16;
    const twoLines = lineHeight * 2 + 1;
    if (el.scrollHeight > twoLines) overflow.add(i);
  });
}

async function afterContentChange() {
  await measureOverflow();
  await nextTick();
  scrollToLatest();
}

watch(
  () => props.taskId,
  () => {
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
  () => props.progress.map((p) => `${p.step}|${p.detail}|${p.full || ""}`).join("\n"),
  () => {
    void afterContentChange();
  }
);

watch(viewer, (v) => {
  if (v) window.addEventListener("keydown", onKey);
  else window.removeEventListener("keydown", onKey);
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
        :key="i"
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
    <div v-if="viewer" class="overlay" @click.self="closeViewer">
      <div class="drawer" role="dialog" aria-modal="true">
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

.drawer {
  width: min(640px, 100%);
  max-height: 100%;
  background: #fffcf7;
  border: 1px solid var(--line);
  border-radius: 12px;
  box-shadow: 0 18px 50px rgba(30, 28, 20, 0.22);
  display: grid;
  grid-template-rows: auto 1fr;
  overflow: hidden;
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

.rich :deep(.md-hr) {
  border: none;
  border-top: 1px solid var(--line);
  margin: 14px 0;
}

.rich :deep(strong) {
  font-weight: 650;
}

.rich :deep(.table-scroll) {
  margin: 10px 0 14px;
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
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
</style>
