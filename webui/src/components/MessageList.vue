<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { columnLabel, formatCellValue, type ChatMessage } from "../api";
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
  props.messages.map((m) => ({
    ...m,
    html: m.role === "assistant" ? renderMarkdown(m.content) : "",
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
