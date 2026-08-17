/** 与后端 slash_router.SLASH_FIXED_COMMANDS 对齐的可读标题 */
const SLASH_TITLES: Record<string, string> = {
  "/overview": "学习概览",
  "/dau": "日活 DAU",
  "/retention": "注册留存",
  "/funnel": "学习漏斗",
  "/channel": "渠道完课对比",
  "/help": "指令帮助",
};

/** 与后端 SLASH_ALIASES 对齐 */
const SLASH_ALIASES: Record<string, string> = {
  "/today_dashboard": "/overview",
  "/daily_dashboard": "/overview",
  "/留存": "/retention",
  "/日活": "/dau",
  "/漏斗": "/funnel",
  "/概览": "/overview",
  "/渠道": "/channel",
};

function firstToken(text: string): string {
  return text.trim().split(/\s+/)[0] ?? "";
}

/** 折叠空白，并在字数上限处尽量落在空格/标点后 */
export function clipTitle(text: string, maxLen = 18): string {
  const s = text.replace(/\s+/g, " ").trim();
  if (!s) return "";
  if (s.length <= maxLen) return s;

  const head = s.slice(0, maxLen);
  const softBreaks = [" ", "，", "。", "、", "？", "?", "！", "!", "：", ":", "；", ";", "—", "-", "·"];
  let breakAt = -1;
  for (const ch of softBreaks) {
    const i = head.lastIndexOf(ch);
    if (i > breakAt) breakAt = i;
  }
  const minKeep = Math.floor(maxLen * 0.45);
  const cut = breakAt >= minKeep ? breakAt : maxLen;
  return `${s.slice(0, cut).trimEnd()}…`;
}

/**
 * 首条用户输入 → 侧栏会话标题（纯规则，无 LLM）。
 * slash 用固定中文名；自然语言压缩空白后截断。
 */
export function deriveSessionTitle(query: string, maxLen = 18): string {
  const q = query.trim();
  if (!q) return "新分析";

  if (q.startsWith("/")) {
    const token = firstToken(q).toLowerCase();
    const cmd = SLASH_ALIASES[token] ?? token;
    const named = SLASH_TITLES[cmd];
    if (named) return named;
    return clipTitle(`未知 ${cmd || token}`, maxLen);
  }

  return clipTitle(q, maxLen) || "新分析";
}
