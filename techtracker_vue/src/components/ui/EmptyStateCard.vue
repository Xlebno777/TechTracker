<template>
  <div class="tt-empty-state">
    <i :class="['tt-empty-state__icon', icon]"></i>
    <div class="tt-empty-state__content">
      <div class="tt-empty-state__title">{{ title }}</div>
      <div v-if="description" class="tt-empty-state__description">{{ description }}</div>
      <div v-if="$slots.actions" class="tt-empty-state__actions">
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { defineProps } from 'vue';

defineProps({
  icon: {
    type: String,
    default: 'pi pi-inbox',
  },
  title: {
    type: String,
    default: 'Нет данных',
  },
  description: {
    type: String,
    default: '',
  },
});
</script>

<style scoped>
.tt-empty-state {
  display: flex;
  align-items: flex-start;
  gap: 0.7rem;
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  background: #f8fafc;
  padding: 0.9rem;
}

.tt-empty-state__icon {
  color: #64748b;
  font-size: 1rem;
  margin-top: 0.08rem;
}

.tt-empty-state__content {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.tt-empty-state__title {
  color: #0f172a;
  font-size: 0.88rem;
  font-weight: 700;
}

.tt-empty-state__description {
  color: #64748b;
  font-size: 0.8rem;
  line-height: 1.4;
}

.tt-empty-state__actions {
  margin-top: 0.25rem;
}
</style>
