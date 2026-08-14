<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { columnLabel, formatCellValue, type ChatMessage } from "../api";

const props = defineProps<{ messages: ChatMessage[] }>();
const box = ref<HTMLElement | null>(null);

watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    if (box.value) box.value.scrollTop = box.value.scrollHeight;
  }
);

/** 轻量 Markdown：标题 / 加粗 / 列表；表格仍优先用结构化 table */
function renderRich(text: string): string {
  const esc = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const lines = text.split("\n");
  const out: string[] = [];
  let inMdTable = false;
  let mdTableRows: string[][] = [];

  const flushMdTable = () => {
    if (!mdTableRows.length) return;
    const header = mdTableRows[0];
    const body = mdTableRows.slice(2); // skip separator
    out.push('<div class="table-scroll"><table>');
    out.push(
      "<thead><tr>" +
        header.map((c) => `<th>${esc(c.trim())}</th>`).join("") +
        "</tr></thead><tbody>"
    );
    for (const row of body) {
      out.push(
        "<tr>" + row.map((c) => `<td>${esc(c.trim())}</td>`).join("") + "</tr>"
      );
    }
    out.push("</tbody></table></div>");
    mdTableRows = [];
    inMdTable = false;
  };

  const inline = (s: string) =>
    esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  for (const raw of lines) {
    const line = raw;
    if (/^\|(.+)\|$/.test(line.trim())) {
      const cells = line
        .trim()
        .slice(1, -1)
        .split("|")
        .map((c) => c.trim());
      if (/^\|?\s*:?-{3,}/.test(line.trim()) || cells.every((c) => /^:?-{3,}:?$/.test(c))) {
        inMdTable = true;
        mdTableRows.push(cells);
        continue;
      }
      inMdTable = true;
      mdTableRows.push(cells);
      continue;
    }
    if (inMdTable) flushMdTable();

    if (/^###\s+/.test(line)) {
      out.push(`<h3 class="md-h3">${inline(line.replace(/^###\s+/, ""))}</h3>`);
    } else if (/^##\s+/.test(line)) {
      out.push(`<h3 class="md-h3">${inline(line.replace(/^##\s+/, ""))}</h3>`);
    } else if (/^\d+\.\s+/.test(line)) {
      out.push(`<p class="md-li">${inline(line)}</p>`);
    } else if (/^[-*]\s+/.test(line)) {
      out.push(`<p class="md-li">${inline(line.replace(/^[-*]\s+/, "• "))}</p>`);
    } else if (!line.trim()) {
      out.push("<br/>");
    } else {
      out.push(`<p class="md-p">${inline(line)}</p>`);
    }
  }
  if (inMdTable) flushMdTable();
  return out.join("");
}

const rendered = computed(() =>
  props.messages.map((m) => ({
    ...m,
    html: m.role === "assistant" ? renderRich(m.content) : "",
  }))
);
</script>

<template>
  <div ref="box" class="msgs">
    <article
      v-for="m in rendered"
      :key="m.id"
      class="msg"
      :class="m.role"
    >
      <span class="who">{{ m.role === "user" ? "You" : m.role === "assistant" ? "Agent" : "Guide" }}</span>
      <div v-if="m.role === 'assistant'" class="rich" v-html="m.html" />
      <pre v-else>{{ m.content }}</pre>
      <div v-if="m.table?.rows?.length" class="table-wrap">
        <div class="table-caption">支撑数据（{{ m.table.rows.length }} 行）</div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th v-for="col in m.table.columns" :key="col">{{ columnLabel(col) }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in m.table.rows" :key="i">
                <td v-for="col in m.table.columns" :key="col">
                  {{ formatCellValue(col, row[col]) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </article>
  </div>
</template>

<style scoped>
.msgs {
  overflow: auto;
  padding: 18px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.55), transparent 80px),
    var(--panel);
}

.msg {
  max-width: min(760px, 94%);
  border-radius: 12px;
  padding: 10px 12px;
  border: 1px solid var(--line);
}

.msg.user {
  align-self: flex-end;
  background: var(--user-bg);
  color: #f4f7f2;
  border-color: #1d241c;
}

.msg.assistant {
  align-self: flex-start;
  background: #fff;
  border-left: 3px solid var(--amber);
}

.msg.system {
  align-self: center;
  max-width: 560px;
  background: #f3f6f0;
  color: var(--muted);
  border-style: dashed;
  font-size: 0.88rem;
}

.who {
  display: block;
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  opacity: 0.75;
  margin-bottom: 4px;
  font-weight: 600;
}

pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font);
  font-size: 0.92rem;
  line-height: 1.5;
}

.rich {
  font-size: 0.92rem;
  line-height: 1.55;
  word-break: break-word;
}

.rich :deep(.md-h3) {
  margin: 12px 0 6px;
  font-size: 0.98rem;
  font-weight: 650;
  color: #1f2a22;
}

.rich :deep(.md-h3:first-child) {
  margin-top: 0;
}

.rich :deep(.md-p),
.rich :deep(.md-li) {
  margin: 0 0 4px;
}

.rich :deep(strong) {
  font-weight: 650;
}

.rich :deep(.table-scroll) {
  margin: 8px 0 10px;
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

.table-wrap {
  margin-top: 10px;
}

.table-caption {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
  letter-spacing: 0.04em;
  margin-bottom: 6px;
}

.table-scroll {
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.84rem;
  line-height: 1.35;
  min-width: 320px;
}

th,
td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}

th {
  background: #f4f6f1;
  font-weight: 600;
  color: #2a332c;
  position: sticky;
  top: 0;
}

tbody tr:last-child td {
  border-bottom: none;
}

tbody tr:nth-child(even) {
  background: #fafbf8;
}
</style>
