<template>
  <div class="tasks-page p-4">
    <Toast />

    <PageHeader
      title="Центр фоновых задач"
      :refreshable="true"
      :loading="loadingAny"
      help-title="Гайд: центр фоновых задач"
      help-intro="Здесь контролируется очередь удаленного LSTM и запуски прогнозных пайплайнов."
      :help-steps="tasksHelpSteps"
      help-note="Если задача зависла в retry/failed, проверьте токен/доступность удаленного LSTM-сервиса."
      @refresh="refreshAll"
    />

    <FilterPanel
      class="mb-3"
      title="Фильтры и обновление"
    >
      <div class="filters-grid">
        <div class="field-block">
          <label>Устройство</label>
          <Dropdown
            v-model="selectedDeviceId"
            :options="deviceOptions"
            optionLabel="label"
            optionValue="id"
            class="w-full"
            :loading="loadingDevices"
            showClear
            placeholder="Все устройства"
          />
        </div>
        <div class="field-block">
          <label>Статус очереди LSTM</label>
          <Dropdown
            v-model="queueStatusFilter"
            :options="queueStatusOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
            showClear
            placeholder="Все статусы"
          />
        </div>
        <div class="field-block">
          <label>Статус запусков</label>
          <Dropdown
            v-model="runStatusFilter"
            :options="runStatusOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
            showClear
            placeholder="Все статусы"
          />
        </div>
        <div class="field-block">
          <label>Лимит строк</label>
          <InputNumber v-model="limit" :min="20" :max="500" class="w-full" />
        </div>
        <div class="field-block">
          <label>Автообновление</label>
          <div class="switch-inline">
            <InputSwitch v-model="autoRefresh" />
            <span>{{ autoRefresh ? 'Включено' : 'Отключено' }}</span>
          </div>
        </div>
        <div class="field-block">
          <label>Интервал (сек)</label>
          <InputNumber v-model="refreshIntervalSec" :min="3" :max="120" class="w-full" :disabled="!autoRefresh" />
        </div>
      </div>
      <template #footer>
        <div class="actions-row">
          <Button icon="pi pi-sync" label="Обновить сейчас" :loading="loadingQueue || loadingRuns" @click="refreshDataOnly" />
          <span class="text-500 text-sm">Последнее обновление: {{ formatDateTime(lastUpdatedAt) }}</span>
        </div>
      </template>
    </FilterPanel>

    <div class="summary-grid mb-3">
      <div class="card summary-card">
        <span class="summary-label">Очередь: активные</span>
        <strong>{{ queueActiveCount }}</strong>
      </div>
      <div class="card summary-card">
        <span class="summary-label">Очередь: failed</span>
        <strong>{{ queueFailedCount }}</strong>
      </div>
      <div class="card summary-card">
        <span class="summary-label">Запуски: в процессе</span>
        <strong>{{ runsInProgressCount }}</strong>
      </div>
      <div class="card summary-card">
        <span class="summary-label">Запуски: failed за 24ч</span>
        <strong>{{ runsFailed24hCount }}</strong>
      </div>
    </div>

    <div v-if="queueWarnings.length" class="warning-strip mb-3">
      <span v-for="warning in queueWarnings" :key="warning" class="warning-chip">
        <i class="pi pi-exclamation-triangle" />
        {{ warning }}
      </span>
    </div>

    <div class="card p-3 mb-3">
      <div class="table-head">
        <h4 class="m-0">Очередь удаленного LSTM</h4>
        <span class="text-500 text-sm">Строк: {{ filteredQueueRows.length }} / {{ queueRows.length }}</span>
      </div>
      <div class="table-toolbar mt-2 mb-2">
        <TablePresetBar
          v-model="queuePreset"
          title="Пресет очереди"
          :presets="queuePresets"
          aria-label="Пресеты очереди"
        />
      </div>
      <DataTable
        :value="filteredQueueRows"
        dataKey="id"
        :loading="loadingQueue"
        stripedRows
        responsiveLayout="scroll"
        scrollable
        scrollHeight="22rem"
      >
        <template #empty>
          <EmptyStateCard
            icon="pi pi-inbox"
            title="Очередь пуста"
            description="По выбранным фильтрам задач нет. Запустите LSTM-прогноз на вкладке «Прогнозы и состояния»."
          />
        </template>
        <Column field="id" header="ID" style="width: 86px" />
        <Column header="Устройство" style="min-width: 220px">
          <template #body="{ data }">
            {{ data.device_name }} <span class="text-500">({{ data.device_serial }})</span>
          </template>
        </Column>
        <Column field="status" header="Статус" style="width: 140px">
          <template #body="{ data }">
            <Tag :value="String(data.status || '').toUpperCase()" :severity="queueStatusSeverity(data.status)" />
          </template>
        </Column>
        <Column field="remote_job_id" header="Remote Job ID" style="min-width: 180px" />
        <Column header="Попытки" style="width: 170px">
          <template #body="{ data }">
            submit {{ data.attempts_submit ?? 0 }} / poll {{ data.attempts_poll ?? 0 }}
          </template>
        </Column>
        <Column field="retry_count" header="Retry" style="width: 90px" />
        <Column field="next_retry_at" header="Next Retry" style="min-width: 160px">
          <template #body="{ data }">{{ formatDateTime(data.next_retry_at) }}</template>
        </Column>
        <Column field="updated_at" header="Обновлено" style="min-width: 160px">
          <template #body="{ data }">{{ formatDateTime(data.updated_at) }}</template>
        </Column>
        <Column header="Ошибка" style="min-width: 280px">
          <template #body="{ data }">
            <span class="text-600">{{ truncate(String(data.last_error || ''), 140) || '—' }}</span>
          </template>
        </Column>
      </DataTable>
    </div>

    <div class="card p-3">
      <div class="table-head">
        <h4 class="m-0">Запуски прогнозов</h4>
        <span class="text-500 text-sm">Строк: {{ filteredRunRows.length }} / {{ runRows.length }}</span>
      </div>
      <div class="table-toolbar mt-2 mb-2">
        <TablePresetBar
          v-model="runPreset"
          title="Пресет запусков"
          :presets="runPresets"
          aria-label="Пресеты запусков"
        />
      </div>
      <DataTable
        :value="filteredRunRows"
        dataKey="id"
        :loading="loadingRuns"
        stripedRows
        responsiveLayout="scroll"
        scrollable
        scrollHeight="22rem"
      >
        <template #empty>
          <EmptyStateCard
            icon="pi pi-clock"
            title="Запусков не найдено"
            description="Нет запусков по текущим фильтрам. Сгенерируйте demo-данные или запустите прогноз вручную."
          />
        </template>
        <Column field="id" header="Run ID" style="width: 94px" />
        <Column header="Устройство" style="min-width: 220px">
          <template #body="{ data }">
            {{ data.device_name }} <span class="text-500">({{ data.device_serial }})</span>
          </template>
        </Column>
        <Column field="model_kind" header="Модель" style="width: 120px">
          <template #body="{ data }">
            {{ modelKindLabel(data.model_kind) }}
          </template>
        </Column>
        <Column field="status" header="Статус" style="width: 140px">
          <template #body="{ data }">
            <Tag :value="String(data.status || '').toUpperCase()" :severity="runStatusSeverity(data.status)" />
          </template>
        </Column>
        <Column field="started_at" header="Старт" style="min-width: 160px">
          <template #body="{ data }">{{ formatDateTime(data.started_at) }}</template>
        </Column>
        <Column field="finished_at" header="Финиш" style="min-width: 160px">
          <template #body="{ data }">{{ formatDateTime(data.finished_at) }}</template>
        </Column>
        <Column header="Длительность" style="width: 130px">
          <template #body="{ data }">{{ formatDuration(data.started_at, data.finished_at) }}</template>
        </Column>
        <Column field="created_at" header="Создано" style="min-width: 160px">
          <template #body="{ data }">{{ formatDateTime(data.created_at) }}</template>
        </Column>
      </DataTable>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Dropdown from 'primevue/dropdown';
import InputNumber from 'primevue/inputnumber';
import InputSwitch from 'primevue/inputswitch';
import Toast from 'primevue/toast';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Tag from 'primevue/tag';
import { useToast } from 'primevue/usetoast';
import { useMonitoringDeviceStore } from '@/stores/monitoringDevice';
import PageHeader from '@/components/ui/PageHeader.vue';
import FilterPanel from '@/components/ui/FilterPanel.vue';
import TablePresetBar from '@/components/ui/TablePresetBar.vue';
import EmptyStateCard from '@/components/ui/EmptyStateCard.vue';
import { useTableFiltersState, useTablePresetState } from '@/composables/useMonitoringTableState';

const QUEUE_PRESET_KEY = 'monitoring_tasks_queue_preset';
const RUN_PRESET_KEY = 'monitoring_tasks_run_preset';
const TASK_FILTERS_KEY = 'monitoring_tasks_filters';
const tasksHelpSteps = [
  'Выберите устройство и фильтры статуса очереди/запусков.',
  'Включите автообновление, если нужно наблюдать задачу в реальном времени.',
  'Верхние карточки дают быстрый срез: активные, failed, в процессе.',
  'В таблице очереди смотрите попытки submit/poll и текст последней ошибки.',
  'В таблице запусков проверяйте статусы и длительность по каждому run.',
];

const toast = useToast();
const monitoringDeviceStore = useMonitoringDeviceStore();
monitoringDeviceStore.hydrate();

const devices = ref([]);
const queueRows = ref([]);
const runRows = ref([]);
const selectedDeviceId = computed({
  get: () => monitoringDeviceStore.selectedDeviceId,
  set: (value) => monitoringDeviceStore.setSelectedDeviceId(value),
});

const { state: filterState } = useTableFiltersState(TASK_FILTERS_KEY, {
  queueStatusFilter: null,
  runStatusFilter: null,
  autoRefresh: true,
  refreshIntervalSec: 10,
  limit: 120,
});
const queueStatusFilter = computed({
  get: () => filterState.queueStatusFilter,
  set: (value) => { filterState.queueStatusFilter = value || null; },
});
const runStatusFilter = computed({
  get: () => filterState.runStatusFilter,
  set: (value) => { filterState.runStatusFilter = value || null; },
});
const autoRefresh = computed({
  get: () => Boolean(filterState.autoRefresh),
  set: (value) => { filterState.autoRefresh = Boolean(value); },
});
const refreshIntervalSec = computed({
  get: () => Number(filterState.refreshIntervalSec || 10),
  set: (value) => { filterState.refreshIntervalSec = Math.max(3, Math.min(120, Number(value) || 10)); },
});
const limit = computed({
  get: () => Number(filterState.limit || 120),
  set: (value) => { filterState.limit = Math.max(20, Math.min(500, Number(value) || 120)); },
});
const queuePreset = useTablePresetState(QUEUE_PRESET_KEY, 'active', ['active', 'all', 'failed']);
const runPreset = useTablePresetState(RUN_PRESET_KEY, 'in_progress', ['in_progress', 'all', 'failed_24h']);

const loadingDevices = ref(false);
const loadingQueue = ref(false);
const loadingRuns = ref(false);
const lastUpdatedAt = ref(null);
let refreshTimer = null;

const queueStatusOptions = [
  { label: 'Queued', value: 'queued' },
  { label: 'Submitting', value: 'submitting' },
  { label: 'Submitted', value: 'submitted' },
  { label: 'Polling', value: 'polling' },
  { label: 'Retry wait', value: 'retry_wait' },
  { label: 'Success', value: 'success' },
  { label: 'Failed', value: 'failed' },
];

const runStatusOptions = [
  { label: 'Pending', value: 'pending' },
  { label: 'Running', value: 'running' },
  { label: 'Success', value: 'success' },
  { label: 'Failed', value: 'failed' },
];

const queuePresets = [
  { value: 'active', label: 'Активные', description: 'Очередь в работе: queued/submitting/submitted/polling/retry_wait.' },
  { value: 'all', label: 'Все', description: 'Полная картина по очереди независимо от статуса.' },
  { value: 'failed', label: 'Ошибки', description: 'Только задачи очереди с ошибочным завершением.' },
];

const runPresets = [
  { value: 'in_progress', label: 'В процессе', description: 'Показывает pending/running для оперативного контроля.' },
  { value: 'all', label: 'Все', description: 'Все доступные запуски прогнозов.' },
  { value: 'failed_24h', label: 'Failed 24ч', description: 'Только failed-запуски за последние сутки.' },
];

const loadingAny = computed(() => (
  loadingDevices.value || loadingQueue.value || loadingRuns.value
));

const deviceOptions = computed(() => (
  devices.value.map((d) => ({
    id: d.id,
    label: d.serial_number ? `${d.name} (${d.serial_number})` : d.name,
  }))
));

const activeQueueStatuses = ['queued', 'submitting', 'submitted', 'polling', 'retry_wait'];

const filteredQueueRows = computed(() => {
  let rows = queueRows.value.slice();
  if (queuePreset.value === 'active') {
    rows = rows.filter((row) => activeQueueStatuses.includes(String(row.status || '').toLowerCase()));
  } else if (queuePreset.value === 'failed') {
    rows = rows.filter((row) => String(row.status || '').toLowerCase() === 'failed');
  }
  return rows;
});

const filteredRunRows = computed(() => {
  let rows = runRows.value.slice();
  if (runPreset.value === 'in_progress') {
    rows = rows.filter((row) => ['pending', 'running'].includes(String(row.status || '').toLowerCase()));
  } else if (runPreset.value === 'failed_24h') {
    const minTs = Date.now() - (24 * 3600 * 1000);
    rows = rows.filter((row) => {
      const isFailed = String(row.status || '').toLowerCase() === 'failed';
      const createdTs = Number(new Date(row.created_at).getTime());
      return isFailed && Number.isFinite(createdTs) && createdTs >= minTs;
    });
  }
  return rows;
});

const queueActiveCount = computed(() => (
  queueRows.value.filter((row) => activeQueueStatuses.includes(String(row.status || '').toLowerCase())).length
));
const queueFailedCount = computed(() => (
  queueRows.value.filter((row) => String(row.status || '').toLowerCase() === 'failed').length
));
const runsInProgressCount = computed(() => (
  runRows.value.filter((row) => ['pending', 'running'].includes(String(row.status || '').toLowerCase())).length
));
const runsFailed24hCount = computed(() => {
  const minTs = Date.now() - (24 * 3600 * 1000);
  return runRows.value.filter((row) => {
    if (String(row.status || '').toLowerCase() !== 'failed') return false;
    const createdTs = Number(new Date(row.created_at).getTime());
    return Number.isFinite(createdTs) && createdTs >= minTs;
  }).length;
});

const oldestActiveQueueAgeMinutes = computed(() => {
  const ages = queueRows.value
    .filter((row) => activeQueueStatuses.includes(String(row.status || '').toLowerCase()))
    .map((row) => {
      const createdTs = Number(new Date(row.created_at).getTime());
      if (!Number.isFinite(createdTs)) return null;
      return Math.max(0, Math.round((Date.now() - createdTs) / 60000));
    })
    .filter((value) => Number.isFinite(value));
  if (!ages.length) return 0;
  return Math.max(...ages);
});

const queueWarnings = computed(() => {
  const warnings = [];
  const activeCount = queueActiveCount.value;
  const oldestAge = oldestActiveQueueAgeMinutes.value;
  if (activeCount >= 5 || oldestAge >= 10) {
    warnings.push(`Очередь LSTM растёт: активных задач ${activeCount}, старейшая ожидает ${oldestAge} мин.`);
  }
  if (runsInProgressCount.value > 0) {
    const longRuns = runRows.value.filter((row) => {
      if (!['pending', 'running'].includes(String(row.status || '').toLowerCase())) return false;
      const startedTs = Number(new Date(row.started_at || row.created_at).getTime());
      return Number.isFinite(startedTs) && Date.now() - startedTs >= 30 * 60000;
    }).length;
    if (longRuns > 0) warnings.push(`Оценка прогноза выполняется долго или forecast-run завис: долгих запусков ${longRuns}.`);
  }
  return warnings;
});

const unwrap = (res) => (Array.isArray(res.data) ? res.data : (res.data?.results || []));

function queueStatusSeverity(status) {
  const value = String(status || '').toLowerCase();
  if (value === 'success') return 'success';
  if (value === 'failed') return 'danger';
  if (value === 'retry_wait') return 'warning';
  if (value === 'queued' || value === 'submitting' || value === 'submitted' || value === 'polling') return 'info';
  return 'secondary';
}

function runStatusSeverity(status) {
  const value = String(status || '').toLowerCase();
  if (value === 'success') return 'success';
  if (value === 'failed') return 'danger';
  if (value === 'pending' || value === 'running') return 'warning';
  return 'secondary';
}

function modelKindLabel(value) {
  if (value === 'ensemble') return 'Оркестр';
  if (value === 'lstm') return 'LSTM';
  if (value === 'sarima') return 'SARIMA';
  return value || '-';
}

function truncate(text, limitChars = 140) {
  const src = String(text || '');
  if (src.length <= limitChars) return src;
  return `${src.slice(0, limitChars - 1)}…`;
}

function formatDateTime(value) {
  if (!value) return '—';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return String(value);
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(dt);
}

function formatDuration(startedAt, finishedAt) {
  const s = Number(new Date(startedAt).getTime());
  if (!Number.isFinite(s)) return '—';
  const f = Number(new Date(finishedAt).getTime());
  const end = Number.isFinite(f) ? f : Date.now();
  const sec = Math.max(0, Math.round((end - s) / 1000));
  if (sec < 60) return `${sec} сек`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  return `${min}м ${rem}с`;
}

async function loadDevices() {
  loadingDevices.value = true;
  try {
    const res = await apiClient.get('devices/?ordering=name');
    devices.value = unwrap(res);
    monitoringDeviceStore.syncWithAvailableIds(devices.value.map((device) => device.id));
  } catch (err) {
    devices.value = [];
    monitoringDeviceStore.setSelectedDeviceId(null);
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить устройства', life: 3500 });
  } finally {
    loadingDevices.value = false;
  }
}

async function loadQueueRows() {
  loadingQueue.value = true;
  try {
    const params = new URLSearchParams();
    params.set('ordering', '-created_at');
    params.set('limit', String(Number(limit.value) || 120));
    if (selectedDeviceId.value) params.set('device', String(selectedDeviceId.value));
    if (queueStatusFilter.value) params.set('status', String(queueStatusFilter.value));
    const res = await apiClient.get(`forecast-queue-jobs/?${params.toString()}`);
    queueRows.value = unwrap(res);
  } catch (err) {
    queueRows.value = [];
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить очередь LSTM', life: 3500 });
  } finally {
    loadingQueue.value = false;
  }
}

async function loadRunRows() {
  loadingRuns.value = true;
  try {
    const params = new URLSearchParams();
    params.set('ordering', '-created_at');
    params.set('limit', String(Number(limit.value) || 120));
    if (selectedDeviceId.value) params.set('device', String(selectedDeviceId.value));
    if (runStatusFilter.value) params.set('status', String(runStatusFilter.value));
    const res = await apiClient.get(`forecast-runs/?${params.toString()}`);
    runRows.value = unwrap(res);
  } catch (err) {
    runRows.value = [];
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить запуски прогнозов', life: 3500 });
  } finally {
    loadingRuns.value = false;
  }
}

async function refreshDataOnly() {
  await Promise.all([loadQueueRows(), loadRunRows()]);
  lastUpdatedAt.value = new Date().toISOString();
}

async function refreshAll() {
  await loadDevices();
  await refreshDataOnly();
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

function syncAutoRefresh() {
  stopAutoRefresh();
  if (!autoRefresh.value) return;
  const everyMs = Math.max(3, Number(refreshIntervalSec.value) || 10) * 1000;
  refreshTimer = setInterval(() => {
    refreshDataOnly();
  }, everyMs);
}

watch([autoRefresh, refreshIntervalSec], () => {
  syncAutoRefresh();
});

watch([selectedDeviceId, queueStatusFilter, runStatusFilter, limit], () => {
  refreshDataOnly();
});

onMounted(async () => {
  await refreshAll();
  syncAutoRefresh();
});

onUnmounted(() => {
  stopAutoRefresh();
});
</script>

<style scoped>
.tasks-page {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.filters-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 0.8rem;
  align-items: end;
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.field-block label {
  color: #475569;
  font-size: 0.84rem;
  font-weight: 600;
}

.switch-inline {
  min-height: 2.6rem;
  border: 1px solid #d9e2ec;
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0.65rem;
  color: #334155;
  background: #fff;
}

.actions-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 0.7rem;
}

.summary-card {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.summary-label {
  color: #64748b;
  font-size: 0.8rem;
}

.summary-card strong {
  color: #0f172a;
  font-size: 1.3rem;
}

.warning-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.warning-chip {
  border: 1px solid #fbbf24;
  border-radius: 999px;
  background: #fffbeb;
  color: #92400e;
  padding: 0.45rem 0.7rem;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.9rem;
  font-weight: 700;
}

.table-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  flex-wrap: wrap;
}
</style>
