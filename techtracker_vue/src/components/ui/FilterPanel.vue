<template>
  <section class="card p-3 tt-filter-panel">
    <header v-if="hasHeader" class="tt-filter-panel__head">
      <div>
        <h4 v-if="title" class="tt-filter-panel__title">{{ title }}</h4>
        <p v-if="description" class="tt-filter-panel__description">{{ description }}</p>
        <slot name="head" />
      </div>
      <div v-if="$slots.actions" class="tt-filter-panel__actions">
        <slot name="actions" />
      </div>
    </header>
    <div class="tt-filter-panel__body">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="tt-filter-panel__footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<script setup>
import { computed, defineProps, useSlots } from 'vue';

const props = defineProps({
  title: {
    type: String,
    default: '',
  },
  description: {
    type: String,
    default: '',
  },
});

const slots = useSlots();
const hasHeader = computed(() => (
  !!slots.actions
  || !!slots.head
  || !!String(props.title || '').trim()
  || !!String(props.description || '').trim()
));
</script>

<style scoped>
.tt-filter-panel {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
}

.tt-filter-panel__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  margin-bottom: 0.85rem;
}

.tt-filter-panel__title {
  margin: 0;
  color: #0f172a;
  font-size: 1.05rem;
  font-weight: 700;
}

.tt-filter-panel__description {
  margin: 0.25rem 0 0;
  color: #64748b;
  font-size: 0.9rem;
}

.tt-filter-panel__actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.tt-filter-panel__body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.tt-filter-panel__footer {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid #e2e8f0;
}

@media (max-width: 760px) {
  .tt-filter-panel__head {
    flex-direction: column;
  }
}
</style>
