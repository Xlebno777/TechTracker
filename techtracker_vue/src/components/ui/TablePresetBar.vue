<template>
  <div class="tt-preset-bar">
    <div class="tt-preset-bar__head">
      <span class="tt-preset-bar__title">{{ title }}</span>
      <div class="tt-preset-bar__buttons" role="group" :aria-label="ariaLabel">
        <Button
          v-for="preset in presets"
          :key="preset.value"
          size="small"
          :label="preset.label"
          :outlined="modelValue !== preset.value"
          :severity="modelValue === preset.value ? 'primary' : 'secondary'"
          @click="$emit('update:modelValue', preset.value)"
        />
      </div>
    </div>
    <div v-if="activeDescription" class="tt-preset-bar__desc">
      <i class="pi pi-info-circle"></i>
      <span>{{ activeDescription }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, defineEmits, defineProps } from 'vue';
import Button from 'primevue/button';

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    default: 'Пресет таблицы',
  },
  ariaLabel: {
    type: String,
    default: 'Пресеты таблицы',
  },
  presets: {
    type: Array,
    default: () => [],
  },
});

defineEmits(['update:modelValue']);

const activeDescription = computed(() => {
  const current = props.presets.find((item) => item.value === props.modelValue);
  return String(current?.description || '').trim();
});
</script>

<style scoped>
.tt-preset-bar {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.tt-preset-bar__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
}

.tt-preset-bar__title {
  color: #334155;
  font-size: 0.8rem;
  font-weight: 700;
}

.tt-preset-bar__buttons {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
}

.tt-preset-bar__desc {
  display: inline-flex;
  align-items: flex-start;
  gap: 0.4rem;
  color: #64748b;
  font-size: 0.76rem;
  line-height: 1.35;
}
</style>
