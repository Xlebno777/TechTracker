<template>
  <div class="tt-mode-switch">
    <div class="tt-mode-switch__buttons" role="group" :aria-label="ariaLabel">
      <Button
        :label="basicLabel"
        size="small"
        :outlined="modelValue !== 'basic'"
        :severity="modelValue === 'basic' ? 'primary' : 'secondary'"
        @click="$emit('update:modelValue', 'basic')"
      />
      <Button
        :label="expertLabel"
        size="small"
        :outlined="modelValue !== 'expert'"
        :severity="modelValue === 'expert' ? 'primary' : 'secondary'"
        @click="$emit('update:modelValue', 'expert')"
      />
    </div>

    <div v-if="showBasicHint && isBasic && hiddenItems.length" class="tt-mode-switch__hint">
      <i class="pi pi-info-circle"></i>
      <span>{{ basicHintPrefix }} {{ hiddenItems.join(', ') }}.</span>
    </div>
  </div>
</template>

<script setup>
import { computed, defineEmits, defineProps } from 'vue';
import Button from 'primevue/button';

const props = defineProps({
  modelValue: {
    type: String,
    default: 'basic',
  },
  basicLabel: {
    type: String,
    default: 'Базовый',
  },
  expertLabel: {
    type: String,
    default: 'Экспертный',
  },
  ariaLabel: {
    type: String,
    default: 'Режим интерфейса',
  },
  hiddenItems: {
    type: Array,
    default: () => [],
  },
  showBasicHint: {
    type: Boolean,
    default: false,
  },
  basicHintPrefix: {
    type: String,
    default: 'В базовом режиме скрыто:',
  },
});

defineEmits(['update:modelValue']);

const isBasic = computed(() => props.modelValue !== 'expert');
</script>

<style scoped>
.tt-mode-switch {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
  min-width: 0;
  max-width: 100%;
}

.tt-mode-switch__buttons {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.45rem;
  max-width: 100%;
}

.tt-mode-switch__hint {
  display: inline-flex;
  align-items: flex-start;
  gap: 0.4rem;
  color: #64748b;
  font-size: 0.76rem;
  line-height: 1.35;
  max-width: 28rem;
}

@media (max-width: 640px) {
  .tt-mode-switch {
    width: 100%;
  }

  .tt-mode-switch__buttons {
    width: 100%;
  }
}
</style>
