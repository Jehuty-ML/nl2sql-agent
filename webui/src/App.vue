<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import {
  createSession,
  fetchHealth,
  fetchTask,
  formatResult,
  newMessage,
  startChat,
  type HealthInfo,
  type Session,
} from "./api";
import SessionList from "./components/SessionList.vue";
import MessageList from "./components/MessageList.vue";
import Composer from "./components/Composer.vue";
import RunLog from "./components/RunLog.vue";
import { deriveSessionTitle } from "./sessionTitle";
import { canExportSessionReport, downloadSessionReport } from "./sessionReport";

const STORAGE_KEY = "lumen_query_bench_sessions_v5";
const LAYOUT_KEY = "lumen_query_bench_layout_v1";

const MIN_LEFT = 180;
const MAX_LEFT = 440;
const MIN_RIGHT = 200;
const MAX_RIGHT = 560;
const MIN_CENTER = 360;

const sessions = ref<Session[]>([]);
const activeId = ref("");
const health = ref<HealthInfo | null>(null);
const leftW = ref(250);
const rightW = ref(270);
const layoutEl = ref<HTMLElement | null>(null);
const dragging = ref<"left" | "right" | null>(null);

let healthTimer: number | undefined;
let pollTimer: number | undefined;
const inflightPolls = new Set<string>();

const active = computed(() => sessions.value.find((s) => s.id === activeId.value) || null);
/** 仅锁定当前会话的输入；其它会话可并行提问 */
const activeBusy = computed(() => active.value?.status === "running");
/** 至少完成过一轮分析对话后，才可整理下载 Markdown 报告 */
const canDownloadReport = computed(() => canExportSessionReport(active.value));

const exporting = ref(false);

async function onDownloadReport() {
  if (!active.value || !canExportSessionReport(active.value) || exporting.value) return;
  exporting.value = true;
  try {
    await downloadSessionReport(active.value);
  } catch (e: any) {
    const cur = active.value;
    if (cur) {
      cur.messages.push(
        newMessage("assistant", `报告打包失败: ${e?.message || e}`)
      );
      persist();
    }
  } finally {
    exporting.value = false;
  }
}

const layoutStyle = computed(() => ({
  gridTemplateColumns: `${leftW.value}px 6px minmax(0, 1fr) 6px ${rightW.value}px`,
}));

function sessionById(id: string): Session | undefined {
  return sessions.value.find((s) => s.id === id);
}

function clamp(n: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, n));
}

function loadLayout() {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    if (typeof data.leftW === "number") leftW.value = clamp(data.leftW, MIN_LEFT, MAX_LEFT);
    if (typeof data.rightW === "number") rightW.value = clamp(data.rightW, MIN_RIGHT, MAX_RIGHT);
  } catch {
    /* ignore */
  }
}

function persistLayout() {
  localStorage.setItem(
    LAYOUT_KEY,
    JSON.stringify({ leftW: leftW.value, rightW: rightW.value })
  );
}

function startResize(side: "left" | "right", e: PointerEvent) {
  if (window.matchMedia("(max-width: 980px)").matches) return;
  e.preventDefault();
  dragging.value = side;
  const target = e.currentTarget as HTMLElement;
  target.setPointerCapture(e.pointerId);

  const onMove = (ev: PointerEvent) => {
    const box = layoutEl.value?.getBoundingClientRect();
    if (!box) return;
    const gap = 24;
    if (side === "left") {
      const maxByCenter = box.width - rightW.value - MIN_CENTER - gap;
      leftW.value = clamp(ev.clientX - box.left, MIN_LEFT, Math.min(MAX_LEFT, maxByCenter));
    } else {
      const maxByCenter = box.width - leftW.value - MIN_CENTER - gap;
      rightW.value = clamp(box.right - ev.clientX, MIN_RIGHT, Math.min(MAX_RIGHT, maxByCenter));
    }
  };

  const onUp = (ev: PointerEvent) => {
    dragging.value = null;
    target.releasePointerCapture(ev.pointerId);
    target.removeEventListener("pointermove", onMove);
    target.removeEventListener("pointerup", onUp);
    target.removeEventListener("pointercancel", onUp);
    persistLayout();
  };

  target.addEventListener("pointermove", onMove);
  target.addEventListener("pointerup", onUp);
  target.addEventListener("pointercancel", onUp);
}

function persist() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ activeId: activeId.value, sessions: sessions.value })
  );
}

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    const data = JSON.parse(raw);
    sessions.value = (data.sessions || []).map((s: Session) => ({
      ...s,
      status:
        s.status === "running" || s.status === "pending" || s.status === "accepted"
          ? "running"
          : s.status,
    }));
    activeId.value = data.activeId || sessions.value[0]?.id || "";
    return sessions.value.length > 0;
  } catch {
    return false;
  }
}

function ensureSession() {
  if (!load()) {
    const s = createSession();
    sessions.value = [s];
    activeId.value = s.id;
    persist();
  }
}

function addSession() {
  const s = createSession();
  sessions.value = [s, ...sessions.value];
  activeId.value = s.id;
  persist();
}

function removeSession(id: string) {
  sessions.value = sessions.value.filter((s) => s.id !== id);
  if (!sessions.value.length) {
    const s = createSession();
    sessions.value = [s];
    activeId.value = s.id;
  } else if (activeId.value === id) {
    activeId.value = sessions.value[0].id;
  }
  persist();
}

function selectSession(id: string) {
  activeId.value = id;
  persist();
}

async function refreshHealth() {
  try {
    health.value = await fetchHealth();
  } catch {
    health.value = { status: "down", clickhouse: "down", llm_enabled: false };
  }
}

async function pollRunningSessions() {
  for (const s of sessions.value) {
    const taskId = s.taskId;
    if (!taskId) continue;
    if (s.deliveredTaskId === taskId) continue;
    if (inflightPolls.has(taskId)) continue;

    inflightPolls.add(taskId);
    try {
      const task = await fetchTask(taskId);
      s.progress = task.progress || [];
      s.updatedAt = Date.now();

      if (task.status === "succeeded" || task.status === "failed") {
        const formatted = formatResult(task.final_result);
        s.messages.push(
          newMessage("assistant", formatted.content, formatted.table, {
            taskId,
            evidencePath: formatted.evidencePath,
            evidenceFiles: formatted.evidenceFiles,
            reportPath: formatted.reportPath,
            chartPath: formatted.chartPath,
            deliveryNotice: formatted.deliveryNotice,
            deliveryStatus: formatted.deliveryStatus,
            dataTables: formatted.dataTables,
          })
        );
        s.deliveredTaskId = taskId;
        s.status = task.status;
      } else {
        s.status = "running";
      }
      persist();
    } catch (e: any) {
      if (e?.code === "TASK_NOT_FOUND") {
        s.messages.push(
          newMessage(
            "assistant",
            "任务已失效（服务可能已重启）。请重新发送问题；固定分析请点 /dau 等 slash。"
          )
        );
        s.deliveredTaskId = taskId;
        s.status = "failed";
        s.updatedAt = Date.now();
        persist();
      }
    } finally {
      inflightPolls.delete(taskId);
    }
  }
}

async function ask(query: string) {
  const q = query.trim();
  const sessionId = activeId.value;
  const s = sessionById(sessionId);
  if (!q || !s || s.status === "running") return;

  s.messages.push(newMessage("user", q));
  if (s.title === "新分析") s.title = deriveSessionTitle(q);
  s.status = "running";
  s.progress = [];
  s.taskId = null;
  s.deliveredTaskId = null;
  s.updatedAt = Date.now();
  persist();

  try {
    const { task_id } = await startChat(q);
    const started = sessionById(sessionId);
    if (!started) return;
    started.taskId = task_id;
    started.status = "running";
    started.updatedAt = Date.now();
    persist();
    await pollRunningSessions();
  } catch (e: any) {
    const cur = sessionById(sessionId);
    if (!cur) return;
    cur.messages.push(newMessage("assistant", `请求失败: ${e?.message || e}`));
    cur.status = "failed";
    cur.updatedAt = Date.now();
    persist();
  }
}

watch(sessions, persist, { deep: true });

onMounted(() => {
  loadLayout();
  ensureSession();
  refreshHealth();
  healthTimer = window.setInterval(refreshHealth, 15000);
  pollTimer = window.setInterval(() => {
    void pollRunningSessions();
  }, 500);
  void pollRunningSessions();
});

onUnmounted(() => {
  if (healthTimer) clearInterval(healthTimer);
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<template>
  <div class="app" :class="{ resizing: !!dragging }">
    <header class="top">
      <div class="brand">
        <div class="mark" aria-hidden="true"></div>
        <div>
          <h1>LumenLearn</h1>
          <p>Query Bench · 多会话可并行问数</p>
        </div>
      </div>
      <div class="status">
        <span>
          <i :class="['dot', health?.clickhouse === 'up' ? 'up' : 'down']" />
          CK {{ health?.clickhouse || "…" }}
        </span>
        <span>LLM {{ health?.llm_enabled ? "on" : "off" }}</span>
        <span v-if="health?.llm_provider">{{ health.llm_provider }}/{{ health.llm_model }}</span>
      </div>
    </header>

    <main ref="layoutEl" class="layout" :style="layoutStyle">
      <SessionList
        :sessions="sessions"
        :active-id="activeId"
        @select="selectSession"
        @create="addSession"
        @remove="removeSession"
      />

      <div
        class="splitter"
        role="separator"
        aria-orientation="vertical"
        aria-label="调整会话列表宽度"
        @pointerdown="startResize('left', $event)"
      />

      <section class="stage">
        <div v-if="active" class="stage-bar">
          <div class="stage-title">
            <strong>{{ active.title }}</strong>
            <span v-if="!canDownloadReport" class="hint">完成至少一轮分析后可整理下载（含原始证据）</span>
          </div>
          <button
            type="button"
            class="export-btn"
            :disabled="!canDownloadReport || exporting"
            :title="
              canDownloadReport
                ? '打包下载：report.md + evidence/（MD 内可点击跳转证据）'
                : '需至少完成一轮分析对话后才能整理下载'
            "
            @click="onDownloadReport"
          >
            {{ exporting ? "打包中…" : "整理并下载报告" }}
          </button>
        </div>
        <MessageList v-if="active" :messages="active.messages" />
        <Composer :disabled="activeBusy" @send="ask" />
      </section>

      <div
        class="splitter"
        role="separator"
        aria-orientation="vertical"
        aria-label="调整 Run Log 宽度"
        @pointerdown="startResize('right', $event)"
      />

      <RunLog
        v-if="active"
        :key="active.id"
        :session-id="active.id"
        :task-id="active.taskId"
        :status="active.status"
        :progress="active.progress"
      />
    </main>

    <footer class="disclaimer">
      免责声明：Agent 生成的结论与建议可能存在幻觉或口径偏差；重要分析请结合原始查询结果、固定报表及其它渠道交叉核实后再决策。
    </footer>
  </div>
</template>

<style scoped>
.app {
  height: 100%;
  display: grid;
  grid-template-rows: auto 1fr auto;
  max-width: 1600px;
  margin: 0 auto;
  padding: 16px;
  gap: 12px;
}

.app.resizing {
  cursor: col-resize;
  user-select: none;
}

.app.resizing * {
  cursor: col-resize !important;
  user-select: none !important;
}

.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 4px 14px;
  border-bottom: 1px solid var(--line);
}

.brand {
  display: flex;
  gap: 12px;
  align-items: center;
}

.mark {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background:
    linear-gradient(145deg, var(--amber) 0%, var(--amber-deep) 55%, var(--oak) 100%);
  box-shadow: var(--shadow);
}

.brand h1 {
  margin: 0;
  font-family: var(--display);
  font-size: 1.55rem;
  letter-spacing: -0.03em;
  color: var(--oak);
  line-height: 1.1;
}

.brand p {
  margin: 2px 0 0;
  color: var(--muted);
  font-size: 0.82rem;
}

.status {
  display: flex;
  gap: 14px;
  color: var(--muted);
  font-size: 0.82rem;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 6px;
  background: #b0b8a8;
}
.dot.up {
  background: var(--ok);
}
.dot.down {
  background: var(--err);
}

.layout {
  min-height: 0;
  display: grid;
  gap: 0 4px;
}

.splitter {
  width: 6px;
  margin: 0 -1px;
  border-radius: 999px;
  cursor: col-resize;
  touch-action: none;
  background: transparent;
  position: relative;
  z-index: 2;
}

.splitter::after {
  content: "";
  position: absolute;
  top: 12%;
  bottom: 12%;
  left: 2px;
  width: 2px;
  border-radius: 2px;
  background: var(--line);
  transition: background 0.15s ease, width 0.15s ease, left 0.15s ease;
}

.splitter:hover::after,
.app.resizing .splitter::after {
  left: 1px;
  width: 4px;
  background: var(--amber);
}

.stage {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto 1fr auto;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
}

.stage-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  background: #f7f8f4;
}

.stage-title {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stage-title strong {
  font-size: 0.92rem;
  color: var(--oak);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stage-title .hint {
  font-size: 0.72rem;
  color: var(--muted);
}

.export-btn {
  flex-shrink: 0;
  border: 1px solid #d7c19a;
  background: #fff8eb;
  color: var(--amber-deep);
  border-radius: 8px;
  padding: 7px 12px;
  font-size: 0.8rem;
  font-weight: 600;
}

.export-btn:hover:not(:disabled) {
  background: #ffefd2;
}

.export-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.disclaimer {
  margin: 0;
  padding: 4px 6px 2px;
  color: var(--muted);
  font-size: 0.72rem;
  line-height: 1.45;
  text-align: center;
  opacity: 0.92;
}

@media (max-width: 980px) {
  .layout {
    grid-template-columns: 1fr !important;
    grid-template-rows: auto 1fr auto;
    gap: 12px;
  }

  .splitter {
    display: none;
  }
}
</style>
