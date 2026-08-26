<script setup lang="ts">
import { ref } from "vue";

defineProps<{ disabled?: boolean }>();
const emit = defineEmits<{ send: [query: string] }>();

const text = ref("");
const hints = [
  { label: "/dau", q: "/dau", tip: "日活" },
  { label: "/funnel", q: "/funnel", tip: "学习漏斗" },
  { label: "/retention", q: "/retention", tip: "注册留存" },
  { label: "/channel", q: "/channel", tip: "渠道完课" },
  { label: "/overview", q: "/overview", tip: "学习概览" },
  { label: "/help", q: "/help", tip: "指令帮助" },
];

function submit() {
  const q = text.value.trim();
  if (!q) return;
  emit("send", q);
  text.value = "";
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submit();
  }
}
</script>

<template>
  <div class="composer">
    <div class="hints">
      <button
        v-for="h in hints"
        :key="h.label"
        type="button"
        :disabled="disabled"
        :title="h.tip"
        @click="emit('send', h.q)"
      >
        <code>{{ h.label }}</code>
        <small>{{ h.tip }}</small>
      </button>
    </div>
    <div class="row">
      <textarea
        v-model="text"
        rows="3"
        :placeholder="
          disabled
            ? '本会话生成中…可切换左侧其它会话继续提问'
            : '描述你想看的指标或对比…'
        "
        :disabled="disabled"
        @keydown="onKey"
      />
      <button class="send" type="button" :disabled="disabled" @click="submit">
        {{ disabled ? "分析中" : "发送" }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.composer {
  border-top: 1px solid var(--line);
  padding: 12px;
  background: #f7f8f4;
  display: grid;
  gap: 10px;
}

.hints {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.hints button {
  border: 1px solid #d7c19a;
  background: #fff8eb;
  color: var(--amber-deep);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 0.8rem;
  font-weight: 500;
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  line-height: 1.2;
}

.hints button code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.86rem;
  font-weight: 700;
  color: var(--oak);
}

.hints button small {
  color: var(--muted);
  font-size: 0.68rem;
  font-weight: 400;
}

.hints button:hover:not(:disabled) {
  background: #ffefd2;
}

.row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: end;
}

textarea {
  width: 100%;
  resize: vertical;
  min-height: 72px;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
  background: #fff;
}

textarea:focus {
  outline: 2px solid rgba(201, 132, 44, 0.28);
  border-color: var(--amber);
}

.send {
  border: none;
  background: var(--oak);
  color: #f7faf5;
  border-radius: 10px;
  padding: 12px 16px;
  font-weight: 600;
  min-width: 88px;
}

.send:hover:not(:disabled) {
  filter: brightness(1.08);
}

.send:disabled,
.hints button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
</style>
