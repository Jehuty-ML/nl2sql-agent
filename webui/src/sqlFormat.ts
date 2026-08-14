/** SQL tokenizer + paren-aware pretty printer */

type SqlTok =
  | { kind: "kw"; v: string }
  | { kind: "id"; v: string }
  | { kind: "str"; v: string }
  | { kind: "num"; v: string }
  | { kind: "sym"; v: string };

const KW_RE =
  /^(SELECT|FROM|WHERE|AND|OR|NOT|IN|AS|WITH|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|ON|GROUP|BY|ORDER|LIMIT|HAVING|UNION|ALL|DISTINCT|CASE|WHEN|THEN|ELSE|END|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|VIEW|IF|EXISTS|BETWEEN|LIKE|IS|NULL|TRUE|FALSE|COUNT|SUM|AVG|MIN|MAX|CAST|COALESCE|IFNULL|INTERVAL|DATE|DATETIME|TODATE|ADDDAYS|COUNTDISTINCT|COUNTDISTINCTIF|ARRAYJOIN|FINAL|PREWHERE|SETTINGS|FORMAT|OVER|PARTITION|ROW_NUMBER|RANK)$/;

const BREAK_KWS = new Set([
  "WITH",
  "SELECT",
  "FROM",
  "WHERE",
  "AND",
  "OR",
  "JOIN",
  "LEFT",
  "RIGHT",
  "INNER",
  "FULL",
  "OUTER",
  "CROSS",
  "ON",
  "GROUP",
  "ORDER",
  "HAVING",
  "LIMIT",
  "UNION",
  "SETTINGS",
  "PREWHERE",
  "FORMAT",
]);

const FUNC_KWS = new Set([
  "COUNT",
  "SUM",
  "AVG",
  "MIN",
  "MAX",
  "CAST",
  "COALESCE",
  "IFNULL",
  "TODATE",
  "ADDDAYS",
  "COUNTDISTINCT",
  "COUNTDISTINCTIF",
  "IF",
]);

function tokenizeSql(sql: string): SqlTok[] {
  const s = sql.replace(/\r\n/g, "\n");
  const toks: SqlTok[] = [];
  let i = 0;
  while (i < s.length) {
    const ch = s[i];
    if (/\s/.test(ch)) {
      i += 1;
      continue;
    }
    if (ch === "-" && s[i + 1] === "-") {
      let j = i + 2;
      while (j < s.length && s[j] !== "\n") j += 1;
      i = j;
      continue;
    }
    if (ch === "'") {
      let j = i + 1;
      while (j < s.length) {
        if (s[j] === "'" && s[j + 1] === "'") {
          j += 2;
          continue;
        }
        if (s[j] === "'") {
          j += 1;
          break;
        }
        j += 1;
      }
      toks.push({ kind: "str", v: s.slice(i, j) });
      i = j;
      continue;
    }
    if (/[0-9]/.test(ch)) {
      let j = i + 1;
      while (j < s.length && /[0-9.]/.test(s[j])) j += 1;
      toks.push({ kind: "num", v: s.slice(i, j) });
      i = j;
      continue;
    }
    if (/[A-Za-z_\u0080-\uffff$]/.test(ch)) {
      let j = i + 1;
      while (j < s.length && /[A-Za-z0-9_\u0080-\uffff$]/.test(s[j])) j += 1;
      const raw = s.slice(i, j);
      const up = raw.toUpperCase();
      toks.push(KW_RE.test(up) ? { kind: "kw", v: up } : { kind: "id", v: raw });
      i = j;
      continue;
    }
    // multi-char ops
    if (i + 1 < s.length) {
      const pair = s.slice(i, i + 2);
      if (pair === "!=" || pair === "<>" || pair === "<=" || pair === ">=") {
        toks.push({ kind: "sym", v: pair });
        i += 2;
        continue;
      }
    }
    toks.push({ kind: "sym", v: ch });
    i += 1;
  }
  return toks;
}

function isJoinKw(v: string) {
  return (
    v === "JOIN" ||
    v === "LEFT" ||
    v === "RIGHT" ||
    v === "INNER" ||
    v === "FULL" ||
    v === "CROSS" ||
    v === "OUTER"
  );
}

/**
 * 期望风格：
 * WITH name AS (
 *   SELECT
 *     col,
 *     MIN(dt) AS x
 *   FROM t
 *   WHERE a = 1
 *     AND b != ''
 *     AND dt BETWEEN x AND y
 * )
 */
export function formatSql(sql: string): string {
  const toks = tokenizeSql(sql.trim());
  if (!toks.length) return sql.trim();

  const lines: string[] = [];
  let depth = 0;
  let buf: string[] = [];
  let inlineParen = 0;
  let inSelectList = false;
  /** WHERE / HAVING / ON：后续 AND/OR 多缩进一级 */
  let boolClause = false;
  let prevTok: SqlTok | null = null;

  const indentOf = (extra = 0) => "  ".repeat(Math.max(0, depth + extra));

  const flushBuf = () => {
    if (!buf.length) return;
    const text = buf.join("").replace(/ +/g, " ").trim();
    const extra = boolClause && /^(AND|OR)\b/.test(text) ? 1 : 0;
    lines.push(indentOf(extra) + text);
    buf = [];
  };

  const pushTok = (t: SqlTok, glue = false) => {
    const cur = t.v;
    if (!buf.length) {
      buf.push(cur);
      return;
    }
    const prev = buf[buf.length - 1];
    const noSpace =
      glue ||
      cur === "," ||
      cur === ")" ||
      cur === ";" ||
      cur === "." ||
      prev.endsWith("(") ||
      prev.endsWith(".") ||
      prev.endsWith("!");
    buf.push(noSpace ? cur : " " + cur);
  };

  const endSelectListIfNeeded = () => {
    if (inSelectList) {
      depth = Math.max(0, depth - 1);
      inSelectList = false;
    }
  };

  const endBoolClause = () => {
    boolClause = false;
  };

  for (let i = 0; i < toks.length; i++) {
    const t = toks[i];

    if (t.kind === "sym" && t.v === "(") {
      const isFunc =
        !!prevTok &&
        (prevTok.kind === "id" || (prevTok.kind === "kw" && FUNC_KWS.has(prevTok.v)));
      if (isFunc) {
        pushTok(t, true);
        inlineParen += 1;
      } else {
        pushTok(t);
        flushBuf();
        depth += 1;
      }
      prevTok = t;
      continue;
    }

    if (t.kind === "sym" && t.v === ")") {
      if (inlineParen > 0) {
        pushTok(t);
        inlineParen -= 1;
        prevTok = t;
        continue;
      }
      flushBuf();
      depth = Math.max(0, depth - 1);
      let trail = ")";
      while (i + 1 < toks.length && toks[i + 1].kind === "sym" && toks[i + 1].v === ")") {
        i += 1;
        depth = Math.max(0, depth - 1);
        trail += ")";
      }
      if (i + 1 < toks.length && toks[i + 1].kind === "sym" && toks[i + 1].v === ",") {
        i += 1;
        trail += ",";
      }
      lines.push(indentOf() + trail);
      prevTok = t;
      continue;
    }

    if (t.kind === "sym" && t.v === "," && inlineParen === 0) {
      pushTok(t);
      flushBuf();
      prevTok = t;
      continue;
    }

    if (t.kind === "kw" && BREAK_KWS.has(t.v) && inlineParen === 0) {
      // BETWEEN x AND y：不要在 BETWEEN 右侧的 AND 处断行
      if (t.v === "AND" || t.v === "OR") {
        const joined = buf.join("");
        if (/\bBETWEEN\b/i.test(joined) && !/\bBETWEEN\b[\s\S]*\bAND\b/i.test(joined)) {
          pushTok(t);
          prevTok = t;
          continue;
        }
      }

      if (t.v === "WITH") {
        flushBuf();
        endBoolClause();
        pushTok(t);
        prevTok = t;
        continue;
      }

      if (isJoinKw(t.v) && t.v !== "JOIN") {
        flushBuf();
        endSelectListIfNeeded();
        endBoolClause();
        const parts = [t.v];
        let j = i + 1;
        while (j < toks.length && toks[j].kind === "kw" && isJoinKw(toks[j].v)) {
          parts.push(toks[j].v);
          j += 1;
        }
        if (j < toks.length && toks[j].kind === "kw" && toks[j].v === "JOIN") {
          parts.push("JOIN");
          j += 1;
        }
        i = j - 1;
        pushTok({ kind: "kw", v: parts.join(" ") });
        prevTok = t;
        continue;
      }

      if (t.v === "SELECT") {
        flushBuf();
        endBoolClause();
        let text = "SELECT";
        if (i + 1 < toks.length && toks[i + 1].kind === "kw" && toks[i + 1].v === "DISTINCT") {
          text += " DISTINCT";
          i += 1;
        }
        lines.push(indentOf() + text);
        depth += 1;
        inSelectList = true;
        prevTok = t;
        continue;
      }

      if (t.v === "FROM" || t.v === "WHERE" || t.v === "ON" || t.v === "HAVING" || t.v === "LIMIT") {
        flushBuf();
        endSelectListIfNeeded();
        endBoolClause();
        if (t.v === "WHERE" || t.v === "ON" || t.v === "HAVING") boolClause = true;
        pushTok(t);
        prevTok = t;
        continue;
      }

      if (t.v === "AND" || t.v === "OR") {
        flushBuf();
        pushTok(t);
        prevTok = t;
        continue;
      }

      if (t.v === "GROUP" || t.v === "ORDER") {
        flushBuf();
        endSelectListIfNeeded();
        endBoolClause();
        let text = t.v;
        if (i + 1 < toks.length && toks[i + 1].kind === "kw" && toks[i + 1].v === "BY") {
          text += " BY";
          i += 1;
        }
        pushTok({ kind: "kw", v: text });
        prevTok = t;
        continue;
      }

      if (t.v === "UNION") {
        flushBuf();
        endSelectListIfNeeded();
        endBoolClause();
        let text = "UNION";
        if (i + 1 < toks.length && toks[i + 1].kind === "kw" && toks[i + 1].v === "ALL") {
          text += " ALL";
          i += 1;
        }
        lines.push(indentOf() + text);
        prevTok = t;
        continue;
      }

      flushBuf();
      pushTok(t);
      prevTok = t;
      continue;
    }

    pushTok(t);
    prevTok = t;
  }

  flushBuf();
  return lines.join("\n");
}
