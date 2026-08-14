<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import type { ChatMessage } from "../api";

const props = defineProps<{ messages: ChatMessage[] }>();
const box = ref<HTMLElement | null>(null);

watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    if (box.value) box.value.scrollTop = box.value.scrollHeight;
  }
);
</script>

<template>
  <div ref="box" class="msgs">
    <article
      v-for="m in messages"
      :key="m.id"
      class="msg"
      :class="m.role"
    >
      <span class="who">{{ m.role === "user" ? "You" : m.role === "assistant" ? "Agent" : "Guide" }}</span>
      <pre>{{ m.content }}</pre>
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
  max-width: min(720px, 92%);
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
</style>
