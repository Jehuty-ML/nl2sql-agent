/** 全文美化：Markdown / JSON / SQL 自适应渲染（无第三方依赖） */

import { formatSql } from "./sqlFormat";
export { formatSql } from "./sqlFormat";

function esc(s: string): string {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function inlinePlain(s: string): string {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function safeScratchpadHref(href: string): string | null {
  const h = href.trim().replace(/\\/g, "/");
  if (/^\/download\//i.test(h)) return h;
  if (/^https?:\/\//i.test(h)) return h;
  // Markdown 里常见的 scratchpad 相对路径 → 下载接口
  let p = h;
  if (p.startsWith("./")) p = p.slice(2);
  if (p.startsWith(".scratchpad/")) p = p.slice(".scratchpad/".length);
  else if (p.startsWith("scratchpad/")) p = p.slice("scratchpad/".length);
  if (/^(reports|evidence)\//i.test(p) && !p.includes("..")) {
    return `/download/${p}`;
  }
  return null;
}

function safeHref(href: string): string | null {
  return safeScratchpadHref(href);
}

function inline(s: string): string {
  // 图片优先：![alt](url)
  const imgRe = /!\[([^\]]*)\]\(([^)]+)\)/g;
  const linkRe = /\[([^\]]+)\]\(([^)]+)\)/g;
  let out = "";
  let last = 0;
  let m: RegExpExecArray | null;
  const tokens: Array<{ start: number; end: number; html: string }> = [];

  while ((m = imgRe.exec(s))) {
    const href = safeScratchpadHref(m[2]);
    if (!href) continue;
    tokens.push({
      start: m.index,
      end: m.index + m[0].length,
      html: `<img class="md-img" src="${esc(href)}" alt="${esc(m[1] || "图表")}" loading="lazy" />`,
    });
  }
  while ((m = linkRe.exec(s))) {
    // 跳过已被图片语法吞掉的区间（![...](...) 内层也会匹配 linkRe）
    const overlaps = tokens.some((t) => m!.index >= t.start && m!.index < t.end);
    if (overlaps) continue;
    if (s[m.index - 1] === "!") continue;
    const href = safeScratchpadHref(m[2]);
    tokens.push({
      start: m.index,
      end: m.index + m[0].length,
      html: href
        ? `<a class="md-link" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(m[1])}</a>`
        : inlinePlain(m[0]),
    });
  }
  tokens.sort((a, b) => a.start - b.start);
  for (const t of tokens) {
    if (t.start < last) continue;
    out += inlinePlain(s.slice(last, t.start));
    out += t.html;
    last = t.end;
  }
  out += inlinePlain(s.slice(last));
  return out;
}

function isTableSep(cells: string[]): boolean {
  return cells.length > 0 && cells.every((c) => /^:?-{3,}:?$/.test(c));
}

function isTableLine(line: string): boolean {
  const t = line.trim();
  return t.startsWith("|") && t.includes("|", 1);
}

function splitCells(line: string): string[] {
  let t = line.trim();
  if (t.startsWith("|")) t = t.slice(1);
  if (t.endsWith("|")) t = t.slice(0, -1);
  return t.split("|").map((c) => c.trim());
}

const SQL_KW =
  /\b(SELECT|FROM|WHERE|AND|OR|NOT|IN|AS|WITH|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP|BY|ORDER|LIMIT|HAVING|UNION|ALL|DISTINCT|CASE|WHEN|THEN|ELSE|END|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|VIEW|IF|EXISTS|BETWEEN|LIKE|IS|NULL|TRUE|FALSE|COUNT|SUM|AVG|MIN|MAX|CAST|COALESCE|IFNULL|INTERVAL|DATE|DATETIME|TODATE|ADDDAYS|COUNTDISTINCT|COUNTDISTINCTIF|ARRAYJOIN|FINAL|PREWHERE|SETTINGS|FORMAT|OVER|PARTITION|ROW_NUMBER|RANK)\b/gi;

function highlightSql(src: string): string {
  let s = esc(src);
  s = s.replace(/(--.*?$)/gm, '<span class="tok-cmt">$1</span>');
  s = s.replace(/('(?:\\'|[^'])*')/g, '<span class="tok-str">$1</span>');
  s = s.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="tok-num">$1</span>');
  s = s.replace(SQL_KW, (m) => `<span class="tok-kw">${m.toUpperCase()}</span>`);
  return s;
}

function highlightJson(src: string): string {
  // tokenize roughly: string | number | true/false/null | punct
  const re =
    /("(?:\\.|[^"\\])*")\s*:|("(?:\\.|[^"\\])*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b|([{}\[\]:,])/g;
  let out = "";
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src))) {
    out += esc(src.slice(last, m.index));
    if (m[1] != null) {
      out += `<span class="tok-key">${esc(m[1])}</span><span class="tok-punc">:</span>`;
    } else if (m[2] != null) {
      out += `<span class="tok-str">${esc(m[2])}</span>`;
    } else if (m[3] != null) {
      out += `<span class="tok-num">${esc(m[3])}</span>`;
    } else if (m[4] != null) {
      out += `<span class="tok-bool">${esc(m[4])}</span>`;
    } else if (m[5] != null) {
      out += `<span class="tok-punc">${esc(m[5])}</span>`;
    }
    last = m.index + m[0].length;
  }
  out += esc(src.slice(last));
  return out;
}

/** 行首缩进改为 &nbsp;，避免外层 white-space 被覆盖时丢缩进 */
function lockLeadingIndent(html: string): string {
  return html.replace(/^( +)/gm, (m) => "&nbsp;".repeat(m.length));
}

function normalizeSqlText(sql: string): string {
  let s = sql.trim();
  // 若正文几乎没有真实换行、却含字面 \\n，则还原为换行（避免 JSON 源码感）
  const realNl = (s.match(/\n/g) || []).length;
  const escapedNl = (s.match(/\\n/g) || []).length;
  if (escapedNl > 0 && realNl < 2) {
    s = s.replace(/\\n/g, "\n").replace(/\\t/g, "\t");
  }
  return s;
}

function codeBlock(code: string, lang: string, label?: string): string {
  const prepared =
    lang === "sql" ? formatSql(normalizeSqlText(code)) : code;
  const body =
    lang === "sql"
      ? lockLeadingIndent(highlightSql(prepared))
      : lang === "json"
        ? highlightJson(prepared)
        : esc(prepared);
  const tag = label || lang.toUpperCase();
  const wrapClass = lang === "sql" ? "code wrap" : "code";
  return (
    `<div class="code-block" data-lang="${esc(lang)}">` +
    `<div class="code-bar"><span>${esc(tag)}</span></div>` +
    `<pre class="${wrapClass}"><code>${body}</code></pre></div>`
  );
}

function looksLikeSql(text: string): boolean {
  const t = text.trim().replace(/^SQL\s*[:：]\s*/i, "");
  if (t.length < 8) return false;
  if (/^[\[{]/.test(t)) return false;
  return /^\s*(WITH|SELECT|INSERT|UPDATE|DELETE|CREATE|EXPLAIN|DESCRIBE|SHOW)\b/i.test(t);
}

function stripSqlPrefix(text: string): string {
  return text.replace(/^SQL\s*[:：]\s*/i, "").trim();
}

function tryParseJson(text: string): unknown | undefined {
  const t = text.trim();
  const attempt = (s: string) => {
    try {
      return JSON.parse(s);
    } catch {
      return undefined;
    }
  };
  // Python json.dumps(allow_nan=True) 可能产出 NaN/Infinity，浏览器无法解析
  const repairPyNan = (s: string) =>
    s.replace(/\bNaN\b/g, "null").replace(/-?\bInfinity\b/g, "null");

  if (t.startsWith("{") || t.startsWith("[")) {
    const direct = attempt(t) ?? attempt(repairPyNan(t));
    if (direct !== undefined) return direct;
  }
  const startObj = t.indexOf("{");
  const startArr = t.indexOf("[");
  let start = -1;
  if (startObj >= 0 && (startArr < 0 || startObj < startArr)) start = startObj;
  else if (startArr >= 0) start = startArr;
  if (start < 0) return undefined;
  const end = Math.max(t.lastIndexOf("}"), t.lastIndexOf("]"));
  if (end <= start) return undefined;
  const slice = t.slice(start, end + 1);
  return attempt(slice) ?? attempt(repairPyNan(slice));
}

function formatCell(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "number") {
    if (!Number.isInteger(v) && Math.abs(v) <= 1) return `${(v * 100).toFixed(2)}%`;
    if (!Number.isInteger(v)) return Number(v.toPrecision(6)).toString();
    return String(v);
  }
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function rowsToHtmlTable(rows: Record<string, unknown>[]): string {
  if (!rows.length) return '<p class="md-p">（无行数据）</p>';
  const cols = Object.keys(rows[0]);
  const head =
    "<thead><tr>" + cols.map((c) => `<th>${esc(c)}</th>`).join("") + "</tr></thead>";
  const body =
    "<tbody>" +
    rows
      .slice(0, 50)
      .map(
        (r) =>
          "<tr>" +
          cols.map((c) => `<td>${esc(formatCell(r[c]))}</td>`).join("") +
          "</tr>"
      )
      .join("") +
    "</tbody>";
  const more =
    rows.length > 50
      ? `<p class="md-muted">仅展示前 50 / ${rows.length} 行</p>`
      : "";
  return `<div class="table-scroll"><table>${head}${body}</table></div>${more}`;
}

function renderToolPayload(obj: Record<string, unknown>): string {
  const parts: string[] = [];
  const chips: string[] = [];
  if ("ok" in obj) chips.push(obj.ok ? "ok" : "fail");
  if (obj.name) chips.push(String(obj.name));
  if (obj.analysis_key) chips.push(String(obj.analysis_key));
  if (obj.row_count != null) chips.push(`${obj.row_count} 行`);
  if (obj.start_date || obj.end_date) {
    chips.push(`${obj.start_date || "?"} ~ ${obj.end_date || "?"}`);
  }
  if (chips.length) {
    parts.push(
      `<div class="meta-chips">${chips
        .map((c) => `<span class="chip">${esc(c)}</span>`)
        .join("")}</div>`
    );
  }
  if (obj.error) {
    parts.push(`<div class="callout err"><strong>错误</strong> ${esc(String(obj.error))}</div>`);
  }
  if (obj.hint) {
    parts.push(`<div class="callout hint"><strong>提示</strong> ${esc(String(obj.hint))}</div>`);
  }
  if (typeof obj.sql === "string" && obj.sql.trim()) {
    parts.push('<h4 class="md-h4">SQL</h4>');
    parts.push(codeBlock(obj.sql.trim(), "sql", "SQL"));
  }
  const rows = obj.rows;
  if (Array.isArray(rows) && rows.length && typeof rows[0] === "object" && rows[0]) {
    parts.push('<h4 class="md-h4">结果表</h4>');
    parts.push(rowsToHtmlTable(rows as Record<string, unknown>[]));
  } else if (Array.isArray(rows) && rows.length === 0) {
    parts.push('<p class="md-muted">查询成功，但结果为 0 行</p>');
  }
  // 其它字段；已展示 SQL/表时绝不整包回退 raw JSON（否则 SQL 里会出现字面 \\n）
  const rest = { ...obj };
  delete rest.sql;
  delete rest.rows;
  const skip = new Set([
    "ok",
    "name",
    "analysis_key",
    "row_count",
    "start_date",
    "end_date",
    "error",
    "hint",
    "columns",
    "readonly",
    "description",
  ]);
  const interesting = Object.keys(rest).filter((k) => !skip.has(k));
  if (interesting.length) {
    const slim: Record<string, unknown> = {};
    for (const k of interesting) slim[k] = rest[k];
    parts.push('<h4 class="md-h4">其它字段</h4>');
    parts.push(codeBlock(JSON.stringify(slim, null, 2), "json", "JSON"));
  }
  if (!parts.length) {
    parts.push(codeBlock(JSON.stringify(obj, null, 2), "json", "JSON"));
  }
  return parts.join("");
}

function renderMarkdownBody(text: string): string {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const out: string[] = [];
  let mdTableRows: string[][] = [];
  let inFence: string | null = null;
  let fenceBuf: string[] = [];

  const flushMdTable = () => {
    if (!mdTableRows.length) return;
    const header = mdTableRows[0];
    const maybeSep = mdTableRows[1];
    const body = maybeSep && isTableSep(maybeSep) ? mdTableRows.slice(2) : mdTableRows.slice(1);
    out.push('<div class="table-scroll"><table>');
    out.push(
      "<thead><tr>" + header.map((c) => `<th>${esc(c)}</th>`).join("") + "</tr></thead><tbody>"
    );
    for (const row of body) {
      const cells = [...row];
      while (cells.length < header.length) cells.push("");
      out.push(
        "<tr>" +
          header.map((_, i) => `<td>${esc(cells[i] || "")}</td>`).join("") +
          "</tr>"
      );
    }
    out.push("</tbody></table></div>");
    mdTableRows = [];
  };

  const flushFence = () => {
    const lang = (inFence || "text").toLowerCase();
    const code = fenceBuf.join("\n");
    out.push(codeBlock(code, lang === "sql" || lang === "json" ? lang : lang || "text", lang.toUpperCase() || "CODE"));
    inFence = null;
    fenceBuf = [];
  };

  for (const line of lines) {
    const fence = line.match(/^```(\w+)?\s*$/);
    if (fence) {
      if (inFence != null) {
        flushFence();
      } else {
        if (mdTableRows.length) flushMdTable();
        inFence = fence[1] || "text";
        fenceBuf = [];
      }
      continue;
    }
    if (inFence != null) {
      fenceBuf.push(line);
      continue;
    }

    if (isTableLine(line)) {
      mdTableRows.push(splitCells(line));
      continue;
    }
    if (mdTableRows.length) flushMdTable();

    const t = line.trim();
    if (/^---+$/.test(t) || /^\*\*\*+$/.test(t)) {
      out.push('<hr class="md-hr"/>');
    } else if (/^####\s+/.test(line)) {
      out.push(`<h4 class="md-h4">${inline(line.replace(/^####\s+/, ""))}</h4>`);
    } else if (/^###\s+/.test(line)) {
      out.push(`<h3 class="md-h3">${inline(line.replace(/^###\s+/, ""))}</h3>`);
    } else if (/^##\s+/.test(line)) {
      out.push(`<h3 class="md-h3">${inline(line.replace(/^##\s+/, ""))}</h3>`);
    } else if (/^#\s+/.test(line)) {
      out.push(`<h3 class="md-h3">${inline(line.replace(/^#\s+/, ""))}</h3>`);
    } else if (/^\d+\.\s+/.test(t)) {
      out.push(`<p class="md-li">${inline(t)}</p>`);
    } else if (/^[-*]\s+/.test(t)) {
      out.push(`<p class="md-li">${inline(t.replace(/^[-*]\s+/, "• "))}</p>`);
    } else if (!t) {
      out.push("<br/>");
    } else {
      out.push(`<p class="md-p">${inline(line)}</p>`);
    }
  }
  if (inFence != null) flushFence();
  if (mdTableRows.length) flushMdTable();
  return out.join("");
}

/** 对话气泡：Markdown（含代码围栏） */
export function renderMarkdown(text: string): string {
  return renderMarkdownBody(text);
}

/**
 * Run Log 全文：按内容自适应
 * - 工具 JSON（含 rows/sql）→ 元信息 + 表 + SQL 高亮
 * - 纯 JSON / SQL → 代码块高亮
 * - LLM 思考 / Markdown → 结构化排版
 */
export function renderFullContent(text: string, stepHint = ""): string {
  const raw = String(text || "").trim();
  if (!raw) return "";

  const parsed = tryParseJson(raw);
  if (parsed !== undefined) {
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const obj = parsed as Record<string, unknown>;
      if (
        "rows" in obj ||
        "sql" in obj ||
        "analysis_key" in obj ||
        "ok" in obj ||
        "columns" in obj ||
        "row_count" in obj ||
        /工具返回|观察|固定分析|动态\s*SQL|db_query/i.test(stepHint)
      ) {
        return `<div class="doc-json">${renderToolPayload(obj)}</div>`;
      }
    }
    return codeBlock(JSON.stringify(parsed, null, 2), "json", "JSON");
  }

  const sqlCandidate = stripSqlPrefix(raw);
  if (
    /sql|动态\s*SQL|db_query|调用工具/i.test(stepHint) ||
    looksLikeSql(raw) ||
    looksLikeSql(sqlCandidate)
  ) {
    if (looksLikeSql(sqlCandidate)) {
      return codeBlock(sqlCandidate, "sql", "SQL");
    }
  }

  const md = renderMarkdownBody(raw);
  const isThink = /思考|想法|结论|决策|LLM/i.test(stepHint);
  if (isThink) {
    return `<div class="doc-md doc-think">${md}</div>`;
  }
  return `<div class="doc-md">${md}</div>`;
}
