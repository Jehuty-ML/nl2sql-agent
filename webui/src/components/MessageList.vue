<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import {
  columnLabel,
  downloadScratchpadPath,
  formatCellValue,
  scratchpadBasename,
  type ChatMessage,
} from "../api";
import { renderMarkdown } from "../markdown";

const props = defineProps<{ messages: ChatMessage[] }>();
const box = ref<HTMLElement | null>(null);

watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    if (box.value) box.value.scrollTop = box.value.scrollHeight;
  }
);

const rendered = computed(() =>
  props.messages.map((m) => {
    let content = m.content;
    // 横幅已展示 deliveryNotice 时，正文去掉重复前缀，避免双份提示
    if (m.role === "assistant" && m.deliveryNotice) {
      const n = m.deliveryNotice.trim();
      if (content.trimStart().startsWith(n)) {
        content = content.trimStart().slice(n.length).replace(/^\n+/, "");
      }
    }
    return {
      ...m,
      html: m.role === "assistant" ? renderMarkdown(content) : "",
      evidenceList: uniqueEvidence(m),
    };
  })
);

function uniqueEvidence(m: ChatMessage): string[] {
  const raw = [...(m.evidenceFiles || []), ...(m.evidencePath ? [m.evidencePath] : [])];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const p of raw) {
    const n = p.replace(/\\/g, "/");
    if (!n || seen.has(n)) continue;
    seen.add(n);
    out.push(n);
  }
  return out;
}
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
      <div
        v-if="m.role === 'assistant' && m.deliveryNotice"
        class="delivery-banner"
        :class="{ partial: m.deliveryStatus === 'partial' }"
      >
        {{ m.deliveryNotice }}
      </div>
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
      <div
        v-if="m.role === 'assistant' && (m.evidenceList.length || m.reportPath)"
        class="artifacts"
      >
        <span class="artifacts-label">产物</span>
        <button
          v-for="ev in m.evidenceList"
          :key="ev"
          type="button"
          class="art-btn"
          :title="ev"
          @click="downloadScratchpadPath(ev)"
        >
          下载证据 · {{ scratchpadBasename(ev) }}
        </button>
        <button
          v-if="m.reportPath"
          type="button"
          class="art-btn art-btn-report"
          :title="m.reportPath"
          @click="downloadScratchpadPath(m.reportPath!)"
        >
          下载单次报告 · {{ scratchpadBasename(m.reportPath) }}
        </button>
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

.delivery-banner {
  margin: 0 0 8px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #e0c48a;
  background: #fff8eb;
  color: #6a4a12;
  font-size: 0.82rem;
  line-height: 1.45;
}

.delivery-banner.partial {
  border-color: #e0c48a;
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

.rich :deep(.md-link) {
  color: var(--amber-deep);
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.rich :deep(.md-link:hover) {
  color: var(--oak);
}

.rich :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.82em;
  background: #f1f3ee;
  padding: 1px 5px;
  border-radius: 4px;
}

.rich :deep(.code-block) {
  margin: 8px 0 12px;
  border: 1px solid #d8d3c8;
  border-radius: 10px;
  overflow: hidden;
  background: #1e2420;
}

.rich :deep(.code-bar) {
  padding: 5px 10px;
  background: #2a322c;
  color: #c5d0c4;
  font-size: 0.68rem;
  font-weight: 650;
  letter-spacing: 0.06em;
}

.rich :deep(.code) {
  margin: 0;
  padding: 10px 12px;
  overflow: auto;
  max-height: 360px;
  font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  font-size: 0.78rem;
  line-height: 1.55;
  color: #e7eee6;
  white-space: pre;
}

.rich :deep(.code.wrap),
.rich :deep(.code-block[data-lang="sql"] .code) {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.rich :deep(.tok-kw) { color: #7ec8ff; font-weight: 650; }
.rich :deep(.tok-str) { color: #c6e59a; }
.rich :deep(.tok-key) { color: #9fd0ff; }
.rich :deep(.tok-num) { color: #f0c674; }
.rich :deep(.tok-bool) { color: #e8a0c8; }
.rich :deep(.tok-cmt) { color: #8a9688; font-style: italic; }
.rich :deep(.tok-punc) { color: #aeb8ac; }

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

.artifacts {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.artifacts-label {
  font-size: 0.7rem;
  font-weight: 650;
  letter-spacing: 0.04em;
  color: var(--muted);
  text-transform: uppercase;
  margin-right: 2px;
}

.art-btn {
  border: 1px solid #d7c19a;
  background: #fff8eb;
  color: var(--amber-deep);
  border-radius: 7px;
  padding: 4px 9px;
  font-size: 0.74rem;
  font-weight: 600;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.art-btn-report {
  background: #eef3ea;
  border-color: #c5d0bc;
  color: var(--oak);
}

.art-btn:hover {
  filter: brightness(0.97);
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
