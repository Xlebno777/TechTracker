<template>
  <div class="monitoring-settings-page p-4">
    <PageHeader
      title="Настройки"
      :refreshable="false"
      help-title="Гайд: единый экран настроек"
      help-intro="На странице собраны все настройки мониторингового контура в одном месте."
      :help-steps="helpSteps"
      help-note="Используйте вкладки сверху: интеграции, модель состояния/прогнозов, СППР и история."
    />

    <div class="card settings-shell">
      <div ref="tabsStickySentinel" class="settings-tabs-sentinel" aria-hidden="true"></div>
      <div class="settings-tabs-sticky" :class="{ 'settings-tabs-sticky--pinned': isTabsPinned }">
        <div class="settings-tabs-grid" role="tablist" aria-label="Вкладки настроек">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            type="button"
            class="settings-tab-btn"
            :class="{ 'settings-tab-btn--active': activeTabKey === tab.key }"
            role="tab"
            :aria-selected="activeTabKey === tab.key"
            @click="activeTabKey = tab.key"
          >
            <div class="settings-tab-btn__head">
              <i :class="tab.icon" aria-hidden="true"></i>
              <span class="settings-tab-btn__title">{{ tab.label }}</span>
            </div>
            <span class="settings-tab-btn__hint">{{ tab.hint }}</span>
          </button>
        </div>
      </div>

      <div class="settings-tab-summary">
        <strong>{{ currentTab.label }}</strong>
        <span>{{ currentTab.description }}</span>
      </div>

      <div class="settings-tab-content" role="tabpanel">
        <MonitoringSystemSettings v-if="activeTabKey === 'integrations'" embedded mode="integrations" />
        <MonitoringStateSettings v-else-if="activeTabKey === 'forecast-state'" embedded />
        <MonitoringDecisionSettings v-else-if="activeTabKey === 'decision'" embedded />
        <MonitoringSystemSettings v-else embedded mode="history" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import PageHeader from '@/components/ui/PageHeader.vue';
import MonitoringSystemSettings from '@/components/MonitoringSystemSettings.vue';
import MonitoringStateSettings from '@/components/MonitoringStateSettings.vue';
import MonitoringDecisionSettings from '@/components/MonitoringDecisionSettings.vue';

const route = useRoute();
const router = useRouter();
const tabsStickySentinel = ref(null);
const isTabsPinned = ref(false);
let stickyObserver = null;

const tabs = [
  {
    key: 'integrations',
    label: 'Интеграции',
    icon: 'pi pi-link',
    hint: 'LSTM и обновления приложения',
    description: 'Настройка удалённого LSTM API, версии приложения, manifest релиза и запуска обновлений на Windows Server.',
  },
  {
    key: 'forecast-state',
    label: 'Прогнозы и состояния',
    icon: 'pi pi-chart-scatter',
    hint: 'Пороги S0/S1/S2 и веса модели',
    description: 'Профили состояния, пороги метрик, коэффициенты softmax и участие SARIMA/LSTM по метрикам.',
  },
  {
    key: 'decision',
    label: 'СППР',
    icon: 'pi pi-lightbulb',
    hint: 'Действия, критерии и политики',
    description: 'Полное управление модулем СППР: действия, критерии, матрица потерь и AHP-настройки.',
  },
  {
    key: 'history',
    label: 'История',
    icon: 'pi pi-database',
    hint: 'Сводка и очистка данных',
    description: 'Объёмы данных мониторинга и безопасная очистка истории расчётов без удаления конфигураций.',
  },
];

const helpSteps = [
  'Интеграции: настройка удаленного LSTM API, токена, сетевых параметров и обновлений приложения.',
  'Прогнозы и состояния: профили S0/S1/S2, пороги метрик, веса и управление alpha по метрикам.',
  'СППР: CRUD действий/критериев/политик, матрица потерь и AHP-настройки.',
  'История: сводка по данным мониторинга и очистка истории мониторингового контура.',
];

function normalizeTabKey(key) {
  const raw = String(key || '').trim().toLowerCase();
  const found = tabs.find((item) => item.key === raw);
  return found ? found.key : tabs[0].key;
}

const activeTabKey = ref(normalizeTabKey(route.query.tab));
const currentTab = computed(() => (
  tabs.find((item) => item.key === activeTabKey.value) || tabs[0]
));

watch(
  () => route.query.tab,
  (value) => {
    const nextKey = normalizeTabKey(value);
    if (nextKey !== activeTabKey.value) {
      activeTabKey.value = nextKey;
    }
  },
);

watch(activeTabKey, (value) => {
  const current = String(route.query.tab || '').trim().toLowerCase();
  if (current === value) return;
  router.replace({
    name: 'Settings',
    query: {
      ...route.query,
      tab: value,
    },
  });
});

onMounted(() => {
  if (typeof window === 'undefined' || !('IntersectionObserver' in window)) return;
  if (!tabsStickySentinel.value) return;
  stickyObserver = new IntersectionObserver(
    ([entry]) => {
      isTabsPinned.value = entry.intersectionRatio === 0;
    },
    {
      root: null,
      threshold: [0, 1],
      rootMargin: '-10px 0px 0px 0px',
    },
  );
  stickyObserver.observe(tabsStickySentinel.value);
});

onBeforeUnmount(() => {
  if (stickyObserver) {
    stickyObserver.disconnect();
    stickyObserver = null;
  }
});
</script>

<style scoped>
.monitoring-settings-page {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.settings-shell {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  padding: 0.75rem;
  min-width: 0;
}

.settings-tabs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr));
  gap: 0.6rem;
}

.settings-tabs-sentinel {
  height: 1px;
}

.settings-tabs-sticky {
  position: sticky;
  top: 0.6rem;
  z-index: 25;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 0.55rem;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.settings-tabs-sticky--pinned {
  border-color: #cbd5e1;
  box-shadow:
    0 8px 24px rgba(15, 23, 42, 0.08),
    0 2px 8px rgba(15, 23, 42, 0.06);
}

.settings-tab-btn {
  border: 1px solid #dbe3ef;
  background: #f8fafc;
  color: #334155;
  border-radius: 12px;
  padding: 0.8rem;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
  min-width: 0;
}

.settings-tab-btn:hover {
  border-color: #7dd3fc;
}

.settings-tab-btn--active {
  border-color: #22c55e;
  background: #f0fdf4;
  box-shadow: inset 0 0 0 1px #bbf7d0;
}

.settings-tab-btn__head {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  min-width: 0;
}

.settings-tab-btn__head i {
  color: #0ea5e9;
}

.settings-tab-btn--active .settings-tab-btn__head i {
  color: #16a34a;
}

.settings-tab-btn__title {
  font-size: 1rem;
  font-weight: 700;
  color: #0f172a;
}

.settings-tab-btn__hint {
  font-size: 0.84rem;
  color: #64748b;
}

.settings-tab-summary {
  display: flex;
  flex-direction: column;
  gap: 0.18rem;
  border: 1px solid #e2e8f0;
  background: #fff;
  border-radius: 12px;
  padding: 0.7rem 0.8rem;
}

.settings-tab-summary strong {
  color: #0f172a;
  font-size: 0.98rem;
}

.settings-tab-summary span {
  color: #475569;
  font-size: 0.87rem;
  line-height: 1.4;
}

.settings-tab-content {
  min-width: 0;
}

.settings-tab-content :deep(.card),
.settings-tab-content :deep(.tt-filter-panel),
.settings-tab-content :deep(.manage-card),
.settings-tab-content :deep(.summary-card),
.settings-tab-content :deep(.coeff-group-card) {
  min-width: 0;
}

.settings-tab-content :deep(.p-datatable-wrapper) {
  overflow: auto;
  max-width: 100%;
}

.settings-tab-content :deep(.p-datatable-table) {
  min-width: 620px;
}

.settings-tab-content :deep(.p-inputtext),
.settings-tab-content :deep(.p-inputnumber),
.settings-tab-content :deep(.p-inputnumber-input),
.settings-tab-content :deep(.p-inputtextarea),
.settings-tab-content :deep(.p-dropdown),
.settings-tab-content :deep(.p-multiselect) {
  width: 100%;
  min-width: 0;
}

@media (max-width: 900px) {
  .settings-shell {
    padding: 0.55rem;
  }

  .settings-tabs-sticky {
    top: 0.4rem;
    padding: 0.45rem;
  }

  .settings-tabs-grid {
    grid-template-columns: 1fr 1fr;
  }

  .settings-tab-content :deep(.p-datatable-table) {
    min-width: 560px;
  }
}

@media (max-width: 640px) {
  .settings-tabs-grid {
    grid-template-columns: 1fr;
  }
}
</style>
