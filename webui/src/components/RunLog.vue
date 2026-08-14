<script setup lang="ts">
import { nextTick, reactive, ref, watch } from "vue";
import type { ProgressStep } from "../api";

const props = defineProps<{
  taskId: string | null;
  status: string;
  progress: ProgressStep[];
}>();

/** 用户主动展开的步骤下标（非最新步默认折叠超长内容） */
const expanded = reactive(new Set<number>());
const detailEls = ref<(HTMLElement | null)[]>([]);
/** 实际超出 2 行、需要折叠控件的步骤 */
const overflow = reactive(new Set<number>());
const railEl = ref<HTMLElement | null>(null);

/** 贴底跟随：有新日志时自动滚到底；用户手动上滑后关闭，滚回底部再开 */
const pinToBottom = ref(true);
let ignoreScrollEvent = false;
const NEAR_BOTTOM_PX = 48;

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

function toggle(i: number) {
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
  // 手动拖到离底部较远 → 停止自动跟随；回到底部附近 → 恢复
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
  }
);

watch(
  () => props.progress.length,
  (len, prev) => {
    if (prev != null && len > prev) {
      expanded.clear();
    }
    void afterContentChange();
  },
  { immediate: true }
);

watch(
  () => props.progress.map((p) => `${p.step}|${p.detail}`).join("\n"),
  () => {
    void afterContentChange();
  }
);
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
        :class="[tone(p.step), { latest: isLatest(i), collapsed: isCollapsed(i) }]"
      >
        <strong>{{ p.step }}</strong>
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
          @click="toggle(i)"
        >
          {{ expanded.has(i) ? "收起" : "展开" }}
        </button>
      </li>
    </ol>
  </aside>
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

.step strong {
  display: block;
  color: var(--ink);
  font-weight: 650;
  margin-bottom: 4px;
  font-size: 0.82rem;
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
</style>
