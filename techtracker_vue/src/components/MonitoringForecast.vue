<template>
  <div class="forecast-page p-4 page-shell">
    <Toast />

    <div class="flex flex-wrap justify-content-between align-items-start gap-3 mb-4">
      <div>
        <h2 class="text-2xl font-bold m-0 text-900">Прогнозы и состояния</h2>
        <p class="text-500 m-0">SARIMA baseline и оценка состояний S0/S1/S2</p>
      </div>
      <div class="flex align-items-center gap-2">
        <Button icon="pi pi-refresh" label="Обновить" text @click="refreshAll" :loading="loading" />
      </div>
    </div>

    <div class="card p-3 mb-3">
      <div class="grid">
        <div class="col-12 md:col-5">
          <label class="block mb-2">Устройство</label>
          <Dropdown
            v-model="selectedDeviceId"
            :options="deviceOptions"
            optionLabel="label"
            optionValue="id"
            placeholder="Выберите устройство"
            class="w-full"
            :loading="loadingDevices"
          />
        </div>
        <div class="col-12 md:col-3">
          <label class="block mb-2">Горизонт</label>
          <Dropdown v-model="selectedHorizon" :options="horizonOptions" optionLabel="label" optionValue="value" class="w-full" />
        </div>
        <div class="col-12 md:col-4">
          <label class="block mb-2">Последний запуск</label>
          <div class="run-meta">
            <Tag :value="runStatusLabel(latestRun?.status)" :severity="runStatusSeverity(latestRun?.status)" />
            <span class="text-600 text-sm">
              {{ latestRun ? `${(latestRun.model_kind || '').toUpperCase()} • ${formatDateTime(latestRun.created_at)}` : 'нет данных' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="grid mb-1">
      <div v-for="card in stateCards" :key="card.key" class="col-12 md:col-4">
        <div class="card p-3 state-card" :class="{ active: latestState?.state === card.key }">
          <div class="state-title-row">
            <div class="state-title">{{ card.title }}</div>
            <Tag :value="formatPercent(card.value)" :severity="card.severity" />
          </div>
          <div class="state-text text-600">
            {{ card.desc }}
          </div>
        </div>
      </div>
    </div>

    <div class="card p-3 mb-3">
      <div class="flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
        <h4 class="m-0">Оценка состояния</h4>
        <div class="text-600 text-sm">
          Состояние:
          <Tag :value="stateLabel(latestState?.state)" :severity="stateSeverity(latestState?.state)" />
          <span class="ml-2">Обновлено: {{ formatDateTime(latestState?.timestamp) }}</span>
        </div>
      </div>
      <div class="text-700">
        <strong>Confidence:</strong> {{ latestState?.confidence != null ? latestState.confidence.toFixed(3) : '—' }}
      </div>
      <div class="text-600 mt-2" v-if="latestState?.evidence">
        <strong>Evidence:</strong>
        <pre class="evidence-pre">{{ prettyJson(latestState.evidence) }}</pre>
      </div>
      <div v-else class="text-500">Данные по состоянию отсутствуют.</div>
    </div>

    <div class="card p-3 mb-3">
      <div class="flex flex-wrap align-items-end gap-3">
        <div>
          <label class="block mb-2">Demo runs</label>
          <InputNumber v-model="seedRuns" :min="1" :max="20" class="w-7rem" />
        </div>
        <div class="flex align-items-center gap-2">
          <InputSwitch v-model="seedClear" />
          <span class="text-600">Очистить старые demo</span>
        </div>
        <div class="flex align-items-center gap-2">
          <InputSwitch v-model="seedWithRawHistory" />
          <span class="text-600">Создать raw history</span>
        </div>
        <div>
          <label class="block mb-2">Raw history (days)</label>
          <InputNumber v-model="seedRawDays" :min="1" :max="180" class="w-8rem" />
        </div>
        <Button
          icon="pi pi-database"
          label="Сгенерировать тестовые данные"
          severity="secondary"
          :loading="seeding"
          @click="seedDemo"
        />
      </div>
    </div>

    <div class="card p-3 mb-3">
      <div class="flex flex-wrap align-items-end gap-3">
        <div>
          <label class="block mb-2">Lookback (days)</label>
          <InputNumber v-model="baselineLookbackDays" :min="1" :max="365" class="w-8rem" />
        </div>
        <div>
          <label class="block mb-2">Freq</label>
          <Dropdown v-model="baselineFreq" :options="freqOptions" optionLabel="label" optionValue="value" class="w-8rem" />
        </div>
        <div class="flex align-items-center gap-2">
          <InputSwitch v-model="baselineSaveStl" />
          <span class="text-600">Сохранять STL components</span>
        </div>
        <Button
          icon="pi pi-play"
          label="Запустить baseline прогноз"
          :loading="runningBaseline"
          @click="runBaseline"
        />
      </div>
    </div>

    <div class="card p-3">
      <div class="flex justify-content-between align-items-center mb-2">
        <h4 class="m-0">Forecast points ({{ selectedHorizon }})</h4>
        <span class="text-500 text-sm">Строк: {{ forecastPoints.length }}</span>
      </div>
      <DataTable
        :value="forecastPoints"
        dataKey="id"
        :loading="loading"
        paginator
        :rows="15"
        stripedRows
        responsiveLayout="scroll"
        class="table-compact"
      >
        <Column field="metric_code" header="Metric" sortable />
        <Column field="horizon" header="Horizon" sortable />
        <Column field="model_kind" header="Model" sortable />
        <Column field="target_ts" header="Target time" sortable>
          <template #body="{ data }">
            {{ formatDateTime(data.target_ts) }}
          </template>
        </Column>
        <Column field="y_hat" header="y_hat" sortable>
          <template #body="{ data }">
            {{ formatNum(data.y_hat) }}
          </template>
        </Column>
        <Column field="p10" header="p10">
          <template #body="{ data }">
            {{ formatNum(data.p10) }}
          </template>
        </Column>
        <Column field="p50" header="p50">
          <template #body="{ data }">
            {{ formatNum(data.p50) }}
          </template>
        </Column>
        <Column field="p90" header="p90">
          <template #body="{ data }">
            {{ formatNum(data.p90) }}
          </template>
        </Column>
        <Column field="alpha" header="alpha">
          <template #body="{ data }">
            {{ formatNum(data.alpha, 3) }}
          </template>
        </Column>
      </DataTable>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Dropdown from 'primevue/dropdown';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Tag from 'primevue/tag';
import Toast from 'primevue/toast';
import InputNumber from 'primevue/inputnumber';
import InputSwitch from 'primevue/inputswitch';
import { useToast } from 'primevue/usetoast';

const toast = useToast();

const DEVICE_STORAGE_KEY = 'forecast_selected_device_id';

const devices = ref([]);
const loadingDevices = ref(false);
const selectedDeviceId = ref(null);
const selectedHorizon = ref('24h');

const latestRun = ref(null);
const latestState = ref(null);
const forecastPoints = ref([]);

const loading = ref(false);
const seeding = ref(false);
const runningBaseline = ref(false);

const seedRuns = ref(1);
const seedClear = ref(true);
const seedWithRawHistory = ref(true);
const seedRawDays = ref(30);

const baselineLookbackDays = ref(60);
const baselineFreq = ref('1h');
const baselineSaveStl = ref(true);

const horizonOptions = [
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
  { label: '30d', value: '30d' },
];

const freqOptions = [
  { label: '1h', value: '1h' },
  { label: '30min', value: '30min' },
  { label: '15min', value: '15min' },
];

const unwrap = (res) => (Array.isArray(res.data) ? res.data : (res.data?.results || []));

const deviceOptions = computed(() => (
  devices.value.map((d) => ({
    id: d.id,
    label: d.serial_number ? `${d.name} (${d.serial_number})` : d.name,
    serial: d.serial_number || '',
    name: d.name || '',
  }))
));

const selectedDevice = computed(() => (
  deviceOptions.value.find((item) => item.id === selectedDeviceId.value) || null
));

const selectedSerial = computed(() => selectedDevice.value?.serial || '');

const stateCards = computed(() => {
  const state = latestState.value || {};
  return [
    { key: 's0', title: 'S0 — Норма', desc: 'Сервер работает в штатном режиме.', value: state.p_s0, severity: 'success' },
    { key: 's1', title: 'S1 — Деградация', desc: 'Есть признаки ухудшения, нужен контроль.', value: state.p_s1, severity: 'warning' },
    { key: 's2', title: 'S2 — Предаварийное', desc: 'Высокий риск, нужна реакция.', value: state.p_s2, severity: 'danger' },
  ];
});

const formatDateTime = (value) => {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
  } catch {
    return value;
  }
};

const formatNum = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
};

const formatPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
};

const prettyJson = (value) => {
  try {
    return JSON.stringify(value || {}, null, 2);
  } catch {
    return String(value);
  }
};

const runStatusLabel = (value) => {
  if (value === 'success') return 'Success';
  if (value === 'failed') return 'Failed';
  if (value === 'running') return 'Running';
  if (value === 'pending') return 'Pending';
  return 'N/A';
};

const runStatusSeverity = (value) => {
  if (value === 'success') return 'success';
  if (value === 'failed') return 'danger';
  if (value === 'running') return 'warning';
  return 'secondary';
};

const stateLabel = (value) => {
  if (value === 's0') return 'S0';
  if (value === 's1') return 'S1';
  if (value === 's2') return 'S2';
  return 'Unknown';
};

const stateSeverity = (value) => {
  if (value === 's0') return 'success';
  if (value === 's1') return 'warning';
  if (value === 's2') return 'danger';
  return 'secondary';
};

const loadDevices = async () => {
  loadingDevices.value = true;
  try {
    const res = await apiClient.get('devices/?ordering=name');
    devices.value = unwrap(res);
    const saved = Number(localStorage.getItem(DEVICE_STORAGE_KEY));
    if (saved && devices.value.some((d) => d.id === saved)) {
      selectedDeviceId.value = saved;
    } else if (devices.value.length && !selectedDeviceId.value) {
      selectedDeviceId.value = devices.value[0].id;
    } else if (!devices.value.length) {
      selectedDeviceId.value = null;
    }
  } catch (e) {
    devices.value = [];
    selectedDeviceId.value = null;
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить список устройств', life: 3500 });
  } finally {
    loadingDevices.value = false;
  }
};

const loadLatestRun = async () => {
  latestRun.value = null;
  if (!selectedSerial.value) return;
  try {
    const res = await apiClient.get(`forecast-runs/latest/?serial=${encodeURIComponent(selectedSerial.value)}`);
    latestRun.value = res.data;
  } catch {
    latestRun.value = null;
  }
};

const loadLatestState = async () => {
  latestState.value = null;
  if (!selectedSerial.value) return;
  try {
    const url = `state-estimates/latest/?serial=${encodeURIComponent(selectedSerial.value)}&horizon=${encodeURIComponent(selectedHorizon.value)}`;
    const res = await apiClient.get(url);
    latestState.value = res.data;
  } catch {
    latestState.value = null;
  }
};

const loadForecastPoints = async () => {
  forecastPoints.value = [];
  if (!selectedDeviceId.value) return;
  try {
    const params = new URLSearchParams();
    params.set('device', String(selectedDeviceId.value));
    params.set('horizon', selectedHorizon.value);
    params.set('ordering', '-target_ts');
    if (latestRun.value?.id) {
      params.set('run', String(latestRun.value.id));
    }
    const res = await apiClient.get(`forecast-points/?${params.toString()}`);
    forecastPoints.value = unwrap(res);
  } catch {
    forecastPoints.value = [];
  }
};

const loadAll = async () => {
  loading.value = true;
  try {
    await loadLatestRun();
    await Promise.all([loadLatestState(), loadForecastPoints()]);
  } finally {
    loading.value = false;
  }
};

const refreshAll = async () => {
  await loadDevices();
  await loadAll();
};

const seedDemo = async () => {
  seeding.value = true;
  try {
    const payload = {
      runs: seedRuns.value,
      clear: seedClear.value,
      with_raw_history: seedWithRawHistory.value,
      raw_history_days: seedRawDays.value,
    };
    if (selectedSerial.value) payload.serial = selectedSerial.value;
    const res = await apiClient.post('forecast-runs/seed_demo/', payload);
    toast.add({ severity: 'success', summary: 'Готово', detail: `Тестовые данные созданы (${res.data.created_points || 0} points)`, life: 3000 });
    await refreshAll();
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось сгенерировать тестовые данные';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  } finally {
    seeding.value = false;
  }
};

const runBaseline = async () => {
  runningBaseline.value = true;
  try {
    const payload = {
      lookback_days: baselineLookbackDays.value,
      freq: baselineFreq.value,
      horizons: '24h,7d,30d',
      save_stl_components: baselineSaveStl.value,
    };
    if (selectedSerial.value) payload.serial = selectedSerial.value;
    const res = await apiClient.post('forecast-runs/run_baseline/', payload);
    const failed = res?.data?.failed_runs || 0;
    if (failed > 0) {
      toast.add({ severity: 'warn', summary: 'Внимание', detail: `Baseline завершён с ошибками: ${failed}`, life: 3500 });
    } else {
      toast.add({ severity: 'success', summary: 'Готово', detail: 'Baseline прогноз выполнен', life: 3000 });
    }
    await loadAll();
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось выполнить baseline прогноз';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    runningBaseline.value = false;
  }
};

watch(selectedDeviceId, (value) => {
  if (value) localStorage.setItem(DEVICE_STORAGE_KEY, String(value));
  else localStorage.removeItem(DEVICE_STORAGE_KEY);
  loadAll();
});

watch(selectedHorizon, () => {
  loadAll();
});

onMounted(async () => {
  await loadDevices();
  await loadAll();
});
</script>

<style scoped>
.state-card {
  border: 1px solid #e2e8f0;
  min-height: 8rem;
}
.state-card.active {
  border-color: #0ea5e9;
  box-shadow: 0 0 0 1px rgba(14, 165, 233, 0.2);
}
.state-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.4rem;
}
.state-title {
  font-weight: 700;
  color: #0f172a;
}
.state-text {
  font-size: 0.9rem;
}
.run-meta {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  min-height: 2.25rem;
}
.evidence-pre {
  margin: 0.35rem 0 0;
  padding: 0.65rem;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  max-height: 14rem;
  overflow: auto;
  white-space: pre-wrap;
  font-size: 0.82rem;
}
</style>

