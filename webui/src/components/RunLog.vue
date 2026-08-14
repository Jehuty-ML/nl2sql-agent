<script setup lang="ts">
import type { ProgressStep } from "../api";

defineProps<{
  taskId: string | null;
  status: string;
  progress: ProgressStep[];
}>();
</script>

<template>
  <aside class="rail">
    <h2>Run Log</h2>
    <div class="head">
      <div>task {{ taskId || "—" }}</div>
      <div class="st">{{ status || "idle" }}</div>
    </div>
    <div v-if="!progress?.length" class="empty">等待执行步骤…</div>
    <ol v-else>
      <li v-for="(p, i) in progress" :key="i">
        <strong>{{ p.step }}</strong>
        <span>{{ p.detail }}</span>
      </li>
    </ol>
  </aside>
</template>

<style scoped>
.rail {
  background: rgba(251, 252, 249, 0.92);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px;
  min-height: 0;
  overflow: auto;
  box-shadow: var(--shadow);
}

h2 {
  margin: 0 0 10px;
  font-family: var(--display);
  font-size: 1.15rem;
  color: var(--oak);
}

.head {
  font-size: 0.78rem;
  color: var(--muted);
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--line);
}

.st {
  margin-top: 2px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--amber-deep);
  font-weight: 600;
}

.empty {
  color: var(--muted);
  font-style: italic;
  font-size: 0.85rem;
}

ol {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 10px;
}

li {
  font-size: 0.82rem;
  color: var(--muted);
}

li strong {
  display: block;
  color: var(--ink);
  font-weight: 600;
  margin-bottom: 2px;
}
</style>
