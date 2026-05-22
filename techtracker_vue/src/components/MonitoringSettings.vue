<template>
  <div class="monitoring-settings-page p-4">
    <PageHeader
      title="Настройки"
      :refreshable="false"
      help-title="Гайд: единый экран настроек"
      help-intro="На странице собраны все настройки мониторингового контура в одном месте."
      :help-steps="helpSteps"
      help-note="Используйте вкладки сверху: интеграции, модель состояния/прогнозов, СППР, инсталяторы и история."
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
        <section v-else-if="activeTabKey === 'installers'" class="installers-panel">
          <div class="installers-hero">
            <div>
              <span class="installers-kicker">Подготовлено под релизы</span>
              <h3>Инсталяторы TechTracker</h3>
              <p>
                Здесь будут отображаться установочные пакеты, которые прикреплены к обновлениям:
                серверный пакет Windows, пакет LSTM-ПК и будущие агенты сбора метрик.
              </p>
            </div>
            <span class="installers-badge">Заглушка</span>
          </div>

          <div class="installers-grid">
            <article
              v-for="installer in installerPlaceholders"
              :key="installer.key"
              class="installer-card"
            >
              <div class="installer-card__icon">
                <i :class="installer.icon" aria-hidden="true"></i>
              </div>
              <div class="installer-card__body">
                <div class="installer-card__head">
                  <strong>{{ installer.title }}</strong>
                  <span :class="['installer-status', `installer-status--${installer.statusKind}`]">
                    {{ installer.status }}
                  </span>
                </div>
                <p>{{ installer.description }}</p>
                <small>{{ installer.source }}</small>
              </div>
              <button class="installer-download" type="button" disabled>
                <i class="pi pi-download" aria-hidden="true"></i>
                Скачать
              </button>
            </article>
          </div>

          <div class="installers-note">
            <strong>Следующий шаг:</strong>
            подключить чтение assets из GitHub Releases, чтобы эта вкладка автоматически показывала
            доступные ZIP/MSI/архивы и позволяла скачать нужный инсталятор из интерфейса.
          </div>
        </section>
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
    key: 'installers',
    label: 'Инсталяторы',
    icon: 'pi pi-box',
    hint: 'Пакеты установки из релизов',
    description: 'Будущий каталог установочных пакетов: Windows Server, LSTM-ПК и агенты мониторинга.',
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
  'Инсталяторы: место для скачивания установочных пакетов из опубликованных релизов.',
  'История: сводка по данным мониторинга и очистка истории мониторингового контура.',
];

const installerPlaceholders = [
  {
    key: 'windows-server',
    title: 'Windows Server пакет',
    status: 'Готовится',
    statusKind: 'ready',
    icon: 'pi pi-server',
    description: 'Основной установочный пакет backend, frontend, WinSW-служб и скриптов обновления.',
    source: 'Источник: assets текущего GitHub Release.',
  },
  {
    key: 'lstm-pc',
    title: 'LSTM-ПК сервис',
    status: 'Планируется',
    statusKind: 'planned',
    icon: 'pi pi-bolt',
    description: 'Отдельный пакет для удалённого нейросетевого узла, который выполняет LSTM-прогноз.',
    source: 'Будет использоваться для установки на выделенный ПК/GPU-узел.',
  },
  {
    key: 'monitoring-agent',
    title: 'Агент сбора метрик',
    status: 'Планируется',
    statusKind: 'planned',
    icon: 'pi pi-desktop',
    description: 'Будущий агент для установки на серверы, с которых нужно собирать телеметрию.',
    source: 'Будет добавлен после выделения агентской части проекта.',
  },
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

.installers-panel {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  min-width: 0;
}

.installers-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 1rem;
  align-items: start;
  border: 1px solid #dbeafe;
  border-radius: 16px;
  padding: 1rem;
  background: linear-gradient(135deg, #f8fafc 0%, #eff6ff 100%);
  min-width: 0;
}

.installers-kicker {
  display: inline-flex;
  width: fit-content;
  border-radius: 999px;
  padding: 0.25rem 0.6rem;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.installers-hero h3 {
  margin: 0.55rem 0 0.35rem;
  color: #0f172a;
  font-size: 1.2rem;
}

.installers-hero p {
  margin: 0;
  max-width: 760px;
  color: #475569;
  line-height: 1.45;
}

.installers-badge {
  border-radius: 999px;
  padding: 0.35rem 0.75rem;
  background: #fef3c7;
  color: #92400e;
  font-weight: 800;
  white-space: nowrap;
}

.installers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
  gap: 0.8rem;
  min-width: 0;
}

.installer-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 0.85rem;
  align-items: start;
  border: 1px solid #dbe3ef;
  border-radius: 16px;
  padding: 0.95rem;
  background: #fff;
  min-width: 0;
}

.installer-card__icon {
  display: grid;
  place-items: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 14px;
  background: #ecfdf5;
  color: #059669;
  font-size: 1.15rem;
}

.installer-card__body {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  min-width: 0;
}

.installer-card__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.installer-card__head strong {
  color: #0f172a;
  overflow-wrap: anywhere;
}

.installer-card p {
  margin: 0;
  color: #475569;
  line-height: 1.35;
}

.installer-card small {
  color: #64748b;
  overflow-wrap: anywhere;
}

.installer-status {
  border-radius: 999px;
  padding: 0.22rem 0.55rem;
  font-size: 0.76rem;
  font-weight: 800;
  white-space: nowrap;
}

.installer-status--ready {
  background: #dcfce7;
  color: #166534;
}

.installer-status--planned {
  background: #e2e8f0;
  color: #334155;
}

.installer-download {
  grid-column: 1 / -1;
  width: fit-content;
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 0.55rem 0.75rem;
  background: #f8fafc;
  color: #64748b;
  font-weight: 700;
  cursor: not-allowed;
}

.installers-note {
  border: 1px dashed #bfdbfe;
  border-radius: 14px;
  padding: 0.85rem;
  background: #f8fafc;
  color: #334155;
  line-height: 1.4;
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

  .installers-hero {
    grid-template-columns: 1fr;
  }

  .installers-badge {
    width: fit-content;
  }
}
</style>
