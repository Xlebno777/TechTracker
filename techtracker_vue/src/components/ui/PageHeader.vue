<template>
  <div class="tt-page-header">
    <div class="tt-page-header__text">
      <h2 class="tt-page-header__title">{{ title }}</h2>
      <p v-if="subtitle" class="tt-page-header__subtitle">{{ subtitle }}</p>
    </div>
    <div class="tt-page-header__actions">
      <Button
        v-if="hasHelp"
        icon="pi pi-question-circle"
        text
        rounded
        aria-label="Открыть справку по странице"
        @click="helpVisible = true"
      />
      <SystemHealthIndicator v-if="systemStatusIndicator" />
      <Button
        v-if="refreshable"
        icon="pi pi-refresh"
        :label="refreshLabel"
        text
        :loading="loading"
        @click="$emit('refresh')"
      />
      <slot />
    </div>
  </div>
  <Dialog
    v-model:visible="helpVisible"
    modal
    :header="resolvedHelpTitle"
    :style="{ width: 'min(760px, 96vw)' }"
  >
    <div class="tt-page-header__help">
      <p v-if="helpIntro" class="tt-page-header__help-intro">{{ helpIntro }}</p>
      <ol v-if="helpSteps.length" class="tt-page-header__help-list">
        <li v-for="(item, idx) in helpSteps" :key="`help-step-${idx}`">{{ item }}</li>
      </ol>
      <p v-if="helpNote" class="tt-page-header__help-note">{{ helpNote }}</p>
    </div>
  </Dialog>
</template>

<script setup>
import { computed, defineEmits, defineProps, ref } from 'vue';
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import SystemHealthIndicator from '@/components/ui/SystemHealthIndicator.vue';

const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  subtitle: {
    type: String,
    default: '',
  },
  refreshable: {
    type: Boolean,
    default: false,
  },
  refreshLabel: {
    type: String,
    default: 'Обновить',
  },
  loading: {
    type: Boolean,
    default: false,
  },
  showHelp: {
    type: Boolean,
    default: false,
  },
  helpTitle: {
    type: String,
    default: '',
  },
  helpIntro: {
    type: String,
    default: '',
  },
  helpSteps: {
    type: Array,
    default: () => [],
  },
  helpNote: {
    type: String,
    default: '',
  },
  systemStatusIndicator: {
    type: Boolean,
    default: true,
  },
});

defineEmits(['refresh']);

const helpVisible = ref(false);
const hasHelp = computed(() => (
  props.showHelp
  || Boolean(String(props.helpTitle || '').trim())
  || Boolean(String(props.helpIntro || '').trim())
  || props.helpSteps.length > 0
  || Boolean(String(props.helpNote || '').trim())
));
const resolvedHelpTitle = computed(() => String(props.helpTitle || '').trim() || 'Как работать с этой страницей');
</script>

<style scoped>
.tt-page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.tt-page-header__title {
  margin: 0;
  font-size: 1.5rem;
  line-height: 1.25;
  font-weight: 700;
  color: #0f172a;
}

.tt-page-header__subtitle {
  margin: 0.2rem 0 0;
  color: #64748b;
}

.tt-page-header__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.5rem;
}

.tt-page-header__help {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.tt-page-header__help-intro {
  margin: 0;
  color: #334155;
}

.tt-page-header__help-list {
  margin: 0;
  padding-left: 1.1rem;
  color: #334155;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tt-page-header__help-note {
  margin: 0;
  color: #64748b;
  font-size: 0.9rem;
}

@media (max-width: 760px) {
  .tt-page-header {
    flex-direction: column;
    align-items: stretch;
  }

  .tt-page-header__actions {
    justify-content: stretch;
  }
}
</style>
