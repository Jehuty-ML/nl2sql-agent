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

const STORAGE_KEY = "lumen_query_bench_sessions_v2";

const sessions = ref<Session[]>([]);
const activeId = ref("");
const health = ref<HealthInfo | null>(null);
let healthTimer: number | undefined;
let pollTimer: number | undefined;
const inflightPolls = new Set<string>();

const active = computed(() => sessions.value.find((s) => s.id === activeId.value) || null);
/** 仅锁定当前会话的输入；其它会话可并行提问 */
const activeBusy = computed(() => active.value?.status === "running");

function sessionById(id: string): Session | undefined {
  return sessions.value.find((s) => s.id === id);
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
      // 刷新后无法续订旧轮询；若仍有 taskId，下面 poll 会再拉一次终态
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

/** 后台统一轮询：不因前端超时丢答案；多会话可并行 */
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
        s.messages.push(newMessage("assistant", formatResult(task.final_result)));
        s.deliveredTaskId = taskId;
        s.status = task.status;
      } else {
        s.status = "running";
      }
      persist();
    } catch (e: any) {
      // 服务重启后内存任务消失：停止空转轮询
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
  if (s.title === "新分析") s.title = q.slice(0, 18);
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
    // 立即拉一次，固定分析几乎秒回
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
  <div class="app">
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

    <main class="layout">
      <SessionList
        :sessions="sessions"
        :active-id="activeId"
        @select="selectSession"
        @create="addSession"
        @remove="removeSession"
      />

      <section class="stage">
        <MessageList v-if="active" :messages="active.messages" />
        <Composer :disabled="activeBusy" @send="ask" />
      </section>

      <RunLog
        v-if="active"
        :task-id="active.taskId"
        :status="active.status"
        :progress="active.progress"
      />
    </main>
  </div>
</template>

<style scoped>
.app {
  height: 100%;
  display: grid;
  grid-template-rows: auto 1fr;
  max-width: 1280px;
  margin: 0 auto;
  padding: 16px;
  gap: 12px;
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
  grid-template-columns: var(--sidebar) 1fr var(--rail);
  gap: 12px;
}

.stage {
  min-height: 0;
  display: grid;
  grid-template-rows: 1fr auto;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
}

@media (max-width: 980px) {
  .layout {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr auto;
  }
}
</style>
