export type ChatRole = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: number;
}

export interface ProgressStep {
  step: string;
  detail?: string;
  ts?: number;
}

export interface Session {
  id: string;
  title: string;
  messages: ChatMessage[];
  taskId: string | null;
  /** 已写入对话的 task，避免轮询重复追加答案 */
  deliveredTaskId?: string | null;
  status: string;
  progress: ProgressStep[];
  updatedAt: number;
}

export interface HealthInfo {
  status: string;
  clickhouse: string;
  llm_enabled: boolean;
  llm_provider?: string;
  llm_model?: string;
  service?: string;
}

export interface TaskPayload {
  task_id: string;
  status: string;
  progress?: ProgressStep[];
  final_result?: {
    answer?: string;
    evidence_path?: string;
    report?: { path?: string };
    data?: { rows?: unknown[]; name?: string; analysis_key?: string };
    mode?: string;
    error?: string;
  };
}

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

export async function fetchHealth(): Promise<HealthInfo> {
  const r = await fetch("/health");
  if (!r.ok) throw new Error("health failed");
  return r.json();
}

export async function startChat(query: string): Promise<{ task_id: string }> {
  const r = await fetch("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, sync: false }),
  });
  if (!r.ok) throw new Error("chat failed");
  return r.json();
}

export async function fetchTask(taskId: string): Promise<TaskPayload> {
  const r = await fetch(`/api/v1/task/${taskId}`);
  if (r.status === 404) {
    const err = new Error("task not found");
    (err as Error & { code?: string }).code = "TASK_NOT_FOUND";
    throw err;
  }
  if (!r.ok) throw new Error("task failed");
  return r.json();
}

export function formatResult(result: TaskPayload["final_result"]): string {
  if (!result) return "(无结果)";
  const mode = result.mode || "unknown";
  const lines: string[] = [];
  if (mode === "fixed_slash") {
    lines.push("【固定分析 · 未走大模型】");
  } else if (mode === "agent_loop") {
    lines.push("【自然语言 Agent】");
  } else if (mode === "error" || result.error) {
    lines.push("【执行失败】");
  }
  lines.push(result.answer || "");
  if (result.data?.rows) {
    lines.push("\n— 数据摘要 —\n" + JSON.stringify(result.data.rows.slice(0, 6), null, 2));
  }
  if (result.report?.path) lines.push(`\n报告: ${result.report.path}`);
  if (result.evidence_path) lines.push(`证据: ${result.evidence_path}`);
  return lines.join("\n").trim();
}

export function createSession(title = "新分析"): Session {
  const now = Date.now();
  return {
    id: uid(),
    title,
    messages: [
      {
        id: uid(),
        role: "system",
        content:
          "固定分析请点下方 slash 按钮（会发送 /dau、/funnel 等）。只有以 / 开头的指令才走固定 SQL、不经大模型；输入中文会进入自然语言 Agent。",
        createdAt: now,
      },
    ],
    taskId: null,
    status: "idle",
    progress: [],
    updatedAt: now,
  };
}

export function newMessage(role: ChatRole, content: string): ChatMessage {
  return { id: uid(), role, content, createdAt: Date.now() };
}
