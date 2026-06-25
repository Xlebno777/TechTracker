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
          <MonitoringSystemSettings embedded mode="installers" />

          <article class="installer-card installer-card--single">
            <div class="installer-card__icon">
              <i class="pi pi-desktop" aria-hidden="true"></i>
            </div>
            <div class="installer-card__body">
              <div class="installer-card__head">
                <strong>Инсталлятор агента</strong>
                <span :class="['installer-status', `installer-status--${agentInstallerStatusKind}`]">
                  {{ agentInstallerStatusLabel }}
                </span>
              </div>
              <div class="installer-facts">
                <div>
                  <span>Версия release</span>
                  <strong>{{ agentInstaller?.latest_version || '-' }}</strong>
                </div>
                <div>
                  <span>Asset</span>
                  <strong>{{ agentInstaller?.installer_asset_name || '-' }}</strong>
                </div>
                <div>
                  <span>Размер</span>
                  <strong>{{ formatBytes(agentInstaller?.size_bytes) }}</strong>
                </div>
                <div>
                  <span>Опубликован</span>
                  <strong>{{ formatDateTime(agentInstaller?.published_at) }}</strong>
                </div>
              </div>
              <small class="installer-source">{{ agentInstaller?.release_url || agentInstallerDefaultUrl }}</small>
              <p v-if="agentInstaller?.detail" class="installer-error">{{ agentInstaller.detail }}</p>
            </div>
            <div class="installer-actions">
              <button class="installer-download" type="button" :disabled="agentInstallerLoading" @click="loadAgentInstaller">
                <i class="pi pi-refresh" aria-hidden="true"></i>
                Проверить
              </button>
              <button class="installer-download installer-download--primary" type="button" :disabled="!agentInstaller?.download_url" @click="downloadAgentInstaller">
                <i class="pi pi-download" aria-hidden="true"></i>
                Скачать
              </button>
            </div>
          </article>
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
import apiClient, { describeApiError } from '@/api';
import { useToast } from 'primevue/usetoast';

const route = useRoute();
const router = useRouter();
const toast = useToast();
const tabsStickySentinel = ref(null);
const isTabsPinned = ref(false);
let stickyObserver = null;

const tabs = [
  {
    key: 'integrations',
    label: 'Интеграции',
    icon: 'pi pi-link',
    hint: 'LSTM и сетевые параметры',
    description: 'Настройка удалённого LSTM API, сетевых параметров сервера, базы данных и справки по первому администратору.',
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
    hint: 'Обновления и агент',
    description: 'Обновление TechTracker и проверка последнего release установщика агента из GitHub Releases.',
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
  'Интеграции: настройка удаленного LSTM API, токена, сетевых параметров и базы данных.',
  'Прогнозы и состояния: профили S0/S1/S2, пороги метрик, веса и управление alpha по метрикам.',
  'СППР: CRUD действий/критериев/политик, матрица потерь и AHP-настройки.',
  'Инсталяторы: обновление TechTracker и один актуальный установщик агента из release репозитория tracker-agent.',
  'История: сводка по данным мониторинга и очистка истории мониторингового контура.',
];

const agentInstallerDefaultUrl = 'https://api.github.com/repos/Xlebno777/tracker-agent/releases/latest';
const agentInstaller = ref(null);
const agentInstallerLoading = ref(false);

const agentInstallerStatusKind = computed(() => {
  if (agentInstallerLoading.value) return 'planned';
  if (!agentInstaller.value) return 'planned';
  if (agentInstaller.value.status === 'ok') return 'ready';
  if (agentInstaller.value.status === 'missing_asset') return 'warn';
  return 'error';
});

const agentInstallerStatusLabel = computed(() => {
  if (agentInstallerLoading.value) return 'Проверка';
  if (!agentInstaller.value) return 'Не проверено';
  if (agentInstaller.value.status === 'ok') return 'GitHub доступен';
  if (agentInstaller.value.status === 'missing_asset') return 'Asset не найден';
  return 'Нет соединения';
});

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!bytes) return '-';
  const units = ['Б', 'КБ', 'МБ', 'ГБ'];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatDateTime(value) {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString('ru-RU');
}

async function loadAgentInstaller() {
  agentInstallerLoading.value = true;
  try {
    const response = await apiClient.get('agent-installer/');
    agentInstaller.value = response.data || null;
    if (agentInstaller.value?.status && agentInstaller.value.status !== 'ok') {
      const detail = [
        agentInstaller.value.detail || 'GitHub Releases агента ответил с ошибкой.',
        `Release URL: ${agentInstaller.value.release_url || agentInstallerDefaultUrl}`,
        `Ожидаемый asset: ${agentInstaller.value.installer_asset_name || 'TechTrackerAgentInstaller.exe'}`,
      ].filter(Boolean).join(' ');
      toast.add({
        severity: agentInstaller.value.status === 'missing_asset' ? 'warn' : 'error',
        summary: 'Проблема GitHub Releases агента',
        detail,
        life: 10000,
      });
    } else if (agentInstaller.value?.detail) {
      toast.add({
        severity: 'warn',
        summary: 'GitHub Releases агента',
        detail: agentInstaller.value.detail,
        life: 9000,
      });
    }
  } catch (error) {
    const primaryDetail = describeApiError(error, 'Не удалось проверить GitHub Releases агента через /api/agent-installer/');
    let detail = primaryDetail;
    try {
      const fallbackResponse = await apiClient.get('application-updates/agent-installer/');
      agentInstaller.value = fallbackResponse.data || null;
      return;
    } catch (fallbackError) {
      detail = `${primaryDetail}. Резервный endpoint тоже не ответил: ${describeApiError(fallbackError, 'GET /api/application-updates/agent-installer/')}`;
    }
    agentInstaller.value = {
      status: 'error',
      connected: false,
      release_url: agentInstallerDefaultUrl,
      detail,
    };
    toast.add({ severity: 'error', summary: 'Ошибка инсталлятора агента', detail, life: 10000 });
  } finally {
    agentInstallerLoading.value = false;
  }
}

function downloadAgentInstaller() {
  const url = agentInstaller.value?.download_url;
  if (!url) return;
  window.open(url, '_blank', 'noopener');
}

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
  if (value === 'installers' && !agentInstaller.value) {
    loadAgentInstaller();
  }
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
  if (activeTabKey.value === 'installers') {
    loadAgentInstaller();
  }
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

.installer-card--single {
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
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

.installer-status--warn {
  background: #fef3c7;
  color: #92400e;
}

.installer-status--error {
  background: #fee2e2;
  color: #991b1b;
}

.installer-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr));
  gap: 0.6rem;
}

.installer-facts div {
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
  min-width: 0;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 0.55rem;
  background: #f8fafc;
}

.installer-facts span {
  color: #64748b;
  font-size: 0.76rem;
  font-weight: 700;
}

.installer-facts strong {
  color: #0f172a;
  overflow-wrap: anywhere;
}

.installer-source {
  color: #64748b;
  overflow-wrap: anywhere;
}

.installer-error {
  border: 1px solid #fecaca;
  border-radius: 10px;
  padding: 0.55rem;
  background: #fef2f2;
  color: #991b1b;
  font-weight: 700;
}

.installer-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.55rem;
  min-width: 0;
}

.installer-download {
  min-height: 2.35rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 0.55rem 0.75rem;
  background: #f8fafc;
  color: #334155;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.installer-download:hover:not(:disabled) {
  border-color: #94a3b8;
  background: #ffffff;
}

.installer-download:disabled {
  color: #94a3b8;
  cursor: not-allowed;
}

.installer-download--primary {
  border-color: #2563eb;
  background: #2563eb;
  color: #ffffff;
}

.installer-download--primary:hover:not(:disabled) {
  border-color: #1d4ed8;
  background: #1d4ed8;
}

.installer-download--primary:disabled {
  border-color: #cbd5e1;
  background: #e2e8f0;
  color: #94a3b8;
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

  .installer-card--single {
    grid-template-columns: 1fr;
  }

  .installer-card__icon {
    width: 2.25rem;
    height: 2.25rem;
  }

  .installer-actions {
    justify-content: stretch;
  }

  .installer-download {
    width: 100%;
  }
}
</style>
