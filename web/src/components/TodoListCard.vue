<script setup>
defineProps({
  item: { type: Object, required: true },
});

const statusGlyph = {
  pending: "○",
  in_progress: "◉",
  completed: "✓",
  cancelled: "–",
};
</script>

<template>
  <div class="todo-card" role="status" aria-label="Agent todos">
    <div class="todo-head">
      <span class="todo-title">Todos</span>
      <span class="todo-meta">{{ (item.items || []).length }}</span>
    </div>
    <ul class="todo-list">
      <li
        v-for="row in item.items || []"
        :key="row.id || row.content"
        class="todo-row"
        :data-status="row.status"
      >
        <span class="todo-glyph" aria-hidden="true">{{ statusGlyph[row.status] || "○" }}</span>
        <span class="todo-text">{{ row.content }}</span>
      </li>
    </ul>
  </div>
</template>
