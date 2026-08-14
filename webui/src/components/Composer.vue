<script setup lang="ts">
import { ref } from "vue";

defineProps<{ disabled?: boolean }>();
const emit = defineEmits<{ send: [query: string] }>();

const text = ref("");
const hints = [
  { label: "/dau 日活", q: "/dau" },
  { label: "/funnel 漏斗", q: "/funnel" },
  { label: "/retention 留存", q: "/retention" },
  { label: "/channel 渠道", q: "/channel" },
  { label: "/overview 概览", q: "/overview" },
  { label: "/help", q: "/help" },
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
        @click="emit('send', h.q)"
      >
        {{ h.label }}
      </button>
    </div>
    <div class="row">
      <textarea
        v-model="text"
        rows="3"
        placeholder="描述你想看的指标或对比…"
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
  padding: 4px 12px;
  font-size: 0.8rem;
  font-weight: 500;
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
