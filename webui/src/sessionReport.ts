import {
  columnLabel,
  downloadReportBundle,
  formatCellValue,
  scratchpadBasename,
  type ChatMessage,
  type ResultTable,
  type Session,
} from "./api";

/** 至少完成过一轮「用户提问 → 助手回复」才允许整理下载。 */
export function canExportSessionReport(session: Session | null | undefined): boolean {
  if (!session) return false;
  if (session.status === "running" || session.status === "pending") return false;
  let sawUser = false;
  for (const m of session.messages) {
    if (m.role === "user") {
      sawUser = true;
      continue;
    }
    if (sawUser && m.role === "assistant" && hasExportableAssistant(m)) {
      return true;
    }
  }
  return false;
}

function hasExportableAssistant(m: ChatMessage): boolean {
  if (m.table?.rows?.length) return true;
  if (m.evidencePath || (m.evidenceFiles && m.evidenceFiles.length)) return true;
  const text = (m.content || "").trim();
  if (!text) return false;
  if (text.startsWith("请求失败")) return false;
  if (text.includes("任务已失效")) return false;
  return true;
}

interface AnalysisTurn {
  question: string;
  answer: string;
  table?: ResultTable;
  evidenceFiles: string[];
  reportPath?: string;
}

function pairAnalysisTurns(messages: ChatMessage[]): AnalysisTurn[] {
  const turns: AnalysisTurn[] = [];
  let pendingQ: string | null = null;

  for (const m of messages) {
    if (m.role === "system") continue;
    if (m.role === "user") {
      pendingQ = m.content.trim();
      continue;
    }
    if (m.role === "assistant" && pendingQ != null && hasExportableAssistant(m)) {
      const files = [
        ...(m.evidenceFiles || []),
        ...(m.evidencePath ? [m.evidencePath] : []),
      ];
      turns.push({
        question: pendingQ,
        answer: m.content || "",
        table: m.table,
        evidenceFiles: uniquePaths(files),
        reportPath: m.reportPath,
      });
      pendingQ = null;
    }
  }
  return turns;
}

function uniquePaths(paths: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const p of paths) {
    const n = p.replace(/\\/g, "/");
    if (!n || seen.has(n)) continue;
    seen.add(n);
    out.push(n);
  }
  return out;
}

/** zip 内相对路径映射：scratchpad path → evidence/basename */
function buildEvidenceLinkMap(paths: string[]): Map<string, string> {
  const used = new Set<string>();
  const map = new Map<string, string>();
  for (const p of paths) {
    let name = scratchpadBasename(p) || "evidence.json";
    let candidate = name;
    let i = 1;
    while (used.has(candidate)) {
      const dot = name.lastIndexOf(".");
      const stem = dot > 0 ? name.slice(0, dot) : name;
      const suf = dot > 0 ? name.slice(dot) : "";
      candidate = `${stem}_${i}${suf}`;
      i += 1;
    }
    used.add(candidate);
    map.set(p, `evidence/${candidate}`);
  }
  return map;
}

/** 将本会话整理为 Markdown；证据链接使用打包内相对路径 ./evidence/... */
export function buildSessionReportMarkdown(
  session: Session,
  linkMap?: Map<string, string>
): { markdown: string; evidencePaths: string[] } {
  const generatedAt = formatLocalTime(new Date());
  const turns = pairAnalysisTurns(session.messages);
  const allEvidence = uniquePaths(turns.flatMap((t) => t.evidenceFiles));
  const map = linkMap || buildEvidenceLinkMap(allEvidence);

  const lines: string[] = [
    `# ${session.title || "分析报告"}`,
    "",
    `- 产品：LumenLearn Query Bench`,
    `- 生成时间：${generatedAt}`,
    `- 对话轮次：${turns.length}`,
    `- 原始证据：${allEvidence.length} 个文件（见各轮「原始证据」；解压后可点击相对链接打开）`,
    "",
    "> 本报告由当前会话整理。结论与执行结果表见正文；原始查数 / 工具返回 JSON 在同目录 `evidence/` 下，Markdown 链接可直接跳转。",
    "",
  ];

  if (!turns.length) {
    lines.push("_暂无可整理的分析内容。_");
    return { markdown: lines.join("\n"), evidencePaths: allEvidence };
  }

  turns.forEach((turn, i) => {
    const n = i + 1;
    lines.push(`## ${n}. ${clipHeading(turn.question)}`);
    lines.push("");
    lines.push("### 问题");
    lines.push("");
    lines.push(turn.question);
    lines.push("");
    lines.push("### 分析结论");
    lines.push("");
    lines.push(cleanAssistantBody(turn.answer) || "_（无正文）_");
    lines.push("");
    if (turn.table?.rows?.length) {
      lines.push("### 执行结果");
      lines.push("");
      lines.push(tableToMarkdown(turn.table));
      lines.push("");
      if (turn.table.rows.length >= 20) {
        lines.push("_注：结果表按界面展示上限截取前若干行；完整行数以原始证据为准。_");
        lines.push("");
      }
    } else if (!hasMarkdownTable(turn.answer)) {
      lines.push("### 执行结果");
      lines.push("");
      lines.push("_本次回复未附带结构化结果表（可能为说明类回答，或表格已写在结论 Markdown 中）。_");
      lines.push("");
    }

    if (turn.evidenceFiles.length) {
      lines.push("### 原始证据");
      lines.push("");
      for (const p of turn.evidenceFiles) {
        const rel = map.get(p) || `evidence/${scratchpadBasename(p)}`;
        lines.push(`- [${scratchpadBasename(p)}](./${rel})`);
      }
      lines.push("");
    }
  });

  if (allEvidence.length) {
    lines.push("## 证据索引");
    lines.push("");
    for (const p of allEvidence) {
      const rel = map.get(p) || `evidence/${scratchpadBasename(p)}`;
      lines.push(`- [${scratchpadBasename(p)}](./${rel})`);
    }
    lines.push("");
  }

  lines.push("---");
  lines.push("");
  lines.push(
    "_免责声明：Agent 生成的结论与建议可能存在幻觉或口径偏差；重要分析请结合原始证据交叉核实。_"
  );
  lines.push("");
  return { markdown: lines.join("\n"), evidencePaths: allEvidence };
}

export async function downloadSessionReport(session: Session): Promise<void> {
  const allEvidence = uniquePaths(
    pairAnalysisTurns(session.messages).flatMap((t) => t.evidenceFiles)
  );
  const linkMap = buildEvidenceLinkMap(allEvidence);
  const { markdown, evidencePaths } = buildSessionReportMarkdown(session, linkMap);
  const stamp = stampForFile();
  const base = `${safeFilename(session.title || "分析报告")}_${stamp}`;

  if (!evidencePaths.length) {
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${base}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    return;
  }

  await downloadReportBundle({
    title: session.title || "分析报告",
    markdown,
    paths: evidencePaths,
    filenameHint: `${base}_bundle.zip`,
  });
}

function cleanAssistantBody(content: string): string {
  return content
    .split("\n")
    .filter((line) => !/^\s*(报告|证据):\s*/.test(line))
    .join("\n")
    .trim();
}

function hasMarkdownTable(text: string): boolean {
  return /\|\s*---/.test(text || "");
}

function tableToMarkdown(table: ResultTable): string {
  const cols = table.columns.length
    ? table.columns
    : Object.keys(table.rows[0] || {});
  if (!cols.length) return "_空结果_";
  const header = `| ${cols.map((c) => escapeCell(columnLabel(c))).join(" | ")} |`;
  const sep = `| ${cols.map(() => "---").join(" | ")} |`;
  const body = table.rows.map(
    (row) =>
      `| ${cols.map((c) => escapeCell(formatCellValue(c, row[c]))).join(" | ")} |`
  );
  return [header, sep, ...body].join("\n");
}

function escapeCell(text: string): string {
  return String(text).replace(/\|/g, "\\|").replace(/\n/g, " ");
}

function clipHeading(text: string, max = 42): string {
  const one = text.replace(/\s+/g, " ").trim();
  if (one.length <= max) return one || "分析";
  return `${one.slice(0, max - 1)}…`;
}

function safeFilename(name: string): string {
  const cleaned = name.replace(/[\\/:*?"<>|]+/g, "_").replace(/\s+/g, "_").trim();
  return cleaned.slice(0, 48) || "分析报告";
}

function stampForFile(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`;
}

function formatLocalTime(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
