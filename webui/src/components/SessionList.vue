<script setup lang="ts">
import type { Session } from "../api";

defineProps<{
  sessions: Session[];
  activeId: string;
}>();

defineEmits<{
  select: [id: string];
  create: [];
  remove: [id: string];
}>();
</script>

<template>
  <aside class="side">
    <button class="new" type="button" @click="$emit('create')">＋ 新分析</button>
    <div class="list">
      <button
        v-for="s in sessions"
        :key="s.id"
        type="button"
        class="item"
        :class="{ active: s.id === activeId }"
        @click="$emit('select', s.id)"
      >
        <span class="title">{{ s.title }}</span>
        <span class="meta" :class="{ running: s.status === 'running' }">
          {{ s.status === "running" ? "生成中…" : s.status }}
        </span>
        <button
          class="x"
          type="button"
          title="删除"
          @click.stop="$emit('remove', s.id)"
        >
          ×
        </button>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.side {
  background: rgba(251, 252, 249, 0.9);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 10px;
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 10px;
  min-height: 0;
  box-shadow: var(--shadow);
}

.new {
  border: 1px solid var(--amber-deep);
  background: linear-gradient(180deg, #f0b35a, var(--amber));
  color: #1a1206;
  border-radius: 8px;
  padding: 10px 12px;
  font-weight: 600;
}

.new:hover {
  filter: brightness(1.03);
}

.list {
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.item {
  position: relative;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 8px;
  padding: 10px 28px 10px 10px;
  color: var(--ink);
}

.item:hover {
  background: #f1f4ee;
}

.item.active {
  background: #fff7ea;
  border-color: #e6c48a;
  box-shadow: inset 3px 0 0 var(--amber);
}

.title {
  display: block;
  font-size: 0.9rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.meta {
  display: block;
  margin-top: 3px;
  font-size: 0.72rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.meta.running {
  color: var(--amber-deep);
  text-transform: none;
  letter-spacing: 0;
  font-weight: 600;
}

.x {
  position: absolute;
  right: 6px;
  top: 8px;
  border: none;
  background: transparent;
  color: var(--muted);
  font-size: 1rem;
  line-height: 1;
  padding: 2px 6px;
}

.x:hover {
  color: var(--err);
}
</style>
