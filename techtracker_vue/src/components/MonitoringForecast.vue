<template>
  <div class="forecast-page p-4 page-shell">
    <Toast />

    <div class="flex flex-wrap justify-content-between align-items-start gap-3 mb-4">
      <div>
        <h2 class="text-2xl font-bold m-0 text-900">Прогнозы и состояния</h2>
        <p class="text-500 m-0">SARIMA прогноз и оценка состояний S0/S1/S2</p>
      </div>
      <div class="flex align-items-center gap-2">
        <Button icon="pi pi-refresh" label="Обновить" text @click="refreshAll" :loading="loading" />
      </div>
    </div>

    <div class="card p-3 mb-3">
      <div class="filters-grid">
        <div class="field-block">
          <label>Устройство</label>
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
        <div class="field-block">
          <label>Горизонт</label>
          <Dropdown
            v-model="selectedHorizon"
            :options="horizonOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>
        <div class="field-block">
          <label>Последний запуск</label>
          <div class="run-meta">
            <Tag :value="runStatusLabel(latestRun?.status)" :severity="runStatusSeverity(latestRun?.status)" />
            <span class="text-600 text-sm">
              {{ latestRun ? `SARIMA • ${formatDateTime(latestRun.created_at)}` : 'Нет данных' }}
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
      <div class="text-700 mb-2">
        <strong>Уверенность:</strong> {{ latestState?.confidence != null ? latestState.confidence.toFixed(3) : '—' }}
      </div>
      <div v-if="topEvidence.length" class="factors-grid">
        <div v-for="item in topEvidence" :key="item.metric_code" class="factor-card">
          <div class="factor-title">{{ metricLabel(item.metric_code) }}</div>
          <div class="factor-meta">
            Прогноз: {{ formatNum(item.y_hat) }} {{ metricUnit(item.metric_code) || '' }}
          </div>
          <div class="factor-meta">
            Порог: {{ formatNum(item.threshold) }}
          </div>
          <div class="risk-track">
            <span class="risk-fill" :style="{ width: `${riskPercent(item.risk_component)}%` }"></span>
          </div>
          <div class="factor-risk">Вклад в риск: {{ riskPercent(item.risk_component).toFixed(1) }}%</div>
        </div>
      </div>
      <div v-else class="text-500">Факторы влияния пока недоступны.</div>
    </div>

    <div class="card p-3 mb-3">
      <div class="flex flex-wrap justify-content-between align-items-start gap-2 mb-2">
        <div>
          <h4 class="m-0">Разброс данных по метрике</h4>
          <p class="text-500 m-0">Исторические точки + текущие точки SARIMA-прогноза</p>
        </div>
        <span class="text-500 text-sm">Точек: {{ scatterPointCount }}</span>
      </div>

      <div class="chart-controls">
        <div class="field-block">
          <label>Метрика</label>
          <Dropdown
            v-model="selectedMetricCode"
            :options="metricOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
            placeholder="Выберите метрику"
          />
        </div>
        <div class="field-block">
          <label>Период на графике</label>
          <Dropdown
            v-model="chartWindowMinutes"
            :options="chartWindowOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>
        <div class="field-block action-button">
          <Button
            icon="pi pi-sync"
            label="Обновить график"
            severity="secondary"
            class="w-full"
            :loading="chartLoading"
            @click="loadMetricScatter"
          />
        </div>
      </div>

      <div v-if="scatterPointCount > 0" class="chart-wrap mt-2">
        <Chart type="scatter" :data="scatterChartData" :options="scatterChartOptions" class="scatter-chart" />
      </div>
      <div v-else class="text-500 mt-3">
        Нет данных для выбранной метрики и периода.
      </div>
    </div>

    <div class="card p-3 mb-3">
      <div class="actions-grid">
        <div class="field-block">
          <label>Количество demo-прогонов</label>
          <InputNumber v-model="seedRuns" :min="1" :max="20" class="w-full" />
        </div>
        <div class="field-block">
          <label>Генерировать историю (дней)</label>
          <InputNumber v-model="seedRawDays" :min="1" :max="180" class="w-full" />
        </div>
        <div class="field-block">
          <label>Очистить старые demo</label>
          <div class="switch-inline">
            <InputSwitch v-model="seedClear" />
            <span>{{ seedClear ? 'Да' : 'Нет' }}</span>
          </div>
        </div>
        <div class="field-block">
          <label>Создать raw history</label>
          <div class="switch-inline">
            <InputSwitch v-model="seedWithRawHistory" />
            <span>{{ seedWithRawHistory ? 'Да' : 'Нет' }}</span>
          </div>
        </div>
        <div class="field-block action-button">
          <Button
            icon="pi pi-database"
            label="Сгенерировать тестовые данные"
            severity="secondary"
            class="w-full"
            :loading="seeding"
            @click="seedDemo"
          />
        </div>
      </div>
    </div>

    <div class="card p-3 mb-3">
      <div class="actions-grid">
        <div class="field-block">
          <label>Период обучения (дней)</label>
          <InputNumber v-model="baselineLookbackDays" :min="1" :max="365" class="w-full" />
        </div>
        <div class="field-block">
          <label>Шаг агрегации</label>
          <Dropdown
            v-model="baselineFreq"
            :options="freqOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>
        <div class="field-block">
          <label>Сохранять STL-компоненты</label>
          <div class="switch-inline">
            <InputSwitch v-model="baselineSaveStl" />
            <span>{{ baselineSaveStl ? 'Да' : 'Нет' }}</span>
          </div>
        </div>
        <div class="field-block action-button">
          <Button
            icon="pi pi-play"
            label="Запустить SARIMA прогноз"
            class="w-full"
            :loading="runningBaseline"
            @click="runBaseline"
          />
        </div>
      </div>
    </div>

    <div class="card p-3">
      <div class="flex justify-content-between align-items-center mb-2">
        <h4 class="m-0">Точки прогноза ({{ selectedHorizon }})</h4>
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
        <Column field="metric_code" header="Метрика" sortable>
          <template #body="{ data }">
            {{ metricLabel(data.metric_code) }}
          </template>
        </Column>
        <Column field="horizon" header="Горизонт" sortable />
        <Column field="model_kind" header="Модель" sortable />
        <Column field="target_ts" header="Время цели" sortable>
          <template #body="{ data }">
            {{ formatDateTime(data.target_ts) }}
          </template>
        </Column>
        <Column field="y_hat" header="Прогноз (y_hat)" sortable>
          <template #body="{ data }">
            {{ formatNum(data.y_hat) }}
          </template>
        </Column>
        <Column field="p10" header="Нижняя граница (p10)">
          <template #body="{ data }">
            {{ formatNum(data.p10) }}
          </template>
        </Column>
        <Column field="p50" header="Середина (p50)">
          <template #body="{ data }">
            {{ formatNum(data.p50) }}
          </template>
        </Column>
        <Column field="p90" header="Верхняя граница (p90)">
          <template #body="{ data }">
            {{ formatNum(data.p90) }}
          </template>
        </Column>
        <Column field="alpha" header="Уровень интервала (alpha)">
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
import Chart from 'primevue/chart';
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
const chartLoading = ref(false);

const seedRuns = ref(1);
const seedClear = ref(true);
const seedWithRawHistory = ref(true);
const seedRawDays = ref(30);

const baselineLookbackDays = ref(60);
const baselineFreq = ref('1h');
const baselineSaveStl = ref(true);

const selectedMetricCode = ref('cpu_load_total');
const chartWindowMinutes = ref(7 * 24 * 60);
const rawScatterPoints = ref([]);

const horizonOptions = [
  { label: '24 часа', value: '24h' },
  { label: '7 дней', value: '7d' },
  { label: '30 дней', value: '30d' },
];

const freqOptions = [
  { label: '1 час', value: '1h' },
  { label: '30 минут', value: '30min' },
  { label: '15 минут', value: '15min' },
];

const chartWindowOptions = [
  { label: '24 часа', value: 24 * 60 },
  { label: '7 дней', value: 7 * 24 * 60 },
  { label: '30 дней', value: 30 * 24 * 60 },
  { label: '90 дней', value: 90 * 24 * 60 },
];

const metricOptions = [
  { label: 'Загрузка CPU', value: 'cpu_load_total', unit: '%' },
  { label: 'Использование памяти', value: 'mem_usage_percent', unit: '%' },
  { label: 'Трафик исходящий', value: 'net_bytes_sent', unit: 'KB/s' },
  { label: 'Трафик входящий', value: 'net_bytes_recv', unit: 'KB/s' },
  { label: 'Ping до шлюза', value: 'ping_latency_gateway', unit: 'ms' },
  { label: 'Температура системы', value: 'system_temperature', unit: 'C' },
  { label: 'Температура диска RAID', value: 'storcli_drive_temperature', unit: 'C' },
  { label: 'Predictive Failure Count', value: 'storcli_predictive_failure_count', unit: 'count' },
];

const metricMap = metricOptions.reduce((acc, item) => {
  acc[item.value] = item;
  return acc;
}, {});

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

const selectedMetricMeta = computed(() => metricMap[selectedMetricCode.value] || null);
const selectedMetricUnit = computed(() => selectedMetricMeta.value?.unit || '');

const topEvidence = computed(() => {
  const items = latestState.value?.evidence?.top_components;
  return Array.isArray(items) ? items : [];
});

const stateCards = computed(() => {
  const state = latestState.value || {};
  return [
    { key: 's0', title: 'S0 — Норма', desc: 'Сервер работает в штатном режиме.', value: state.p_s0, severity: 'success' },
    { key: 's1', title: 'S1 — Деградация', desc: 'Есть признаки ухудшения, нужен контроль.', value: state.p_s1, severity: 'warning' },
    { key: 's2', title: 'S2 — Предаварийное', desc: 'Высокий риск, нужна реакция.', value: state.p_s2, severity: 'danger' },
  ];
});

const forecastScatterPoints = computed(() => (
  forecastPoints.value
    .filter((row) => row.metric_code === selectedMetricCode.value)
    .map((row) => ({
      x: Number(new Date(row.target_ts).getTime()),
      y: Number(row.y_hat),
    }))
    .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
));

const scatterPointCount = computed(() => rawScatterPoints.value.length);

const scatterChartData = computed(() => ({
  datasets: [
    {
      label: 'Исторические точки',
      data: rawScatterPoints.value,
      borderColor: 'rgba(14, 165, 233, 0.9)',
      backgroundColor: 'rgba(14, 165, 233, 0.45)',
      pointRadius: 2.4,
      pointHoverRadius: 4,
      showLine: false,
    },
    {
      label: 'SARIMA-прогноз',
      data: forecastScatterPoints.value,
      borderColor: 'rgba(249, 115, 22, 1)',
      backgroundColor: 'rgba(249, 115, 22, 0.95)',
      pointRadius: 4.2,
      pointHoverRadius: 5.5,
      pointStyle: 'triangle',
      showLine: false,
    },
  ],
}));

const scatterChartOptions = computed(() => ({
  maintainAspectRatio: false,
  animation: false,
  parsing: false,
  interaction: {
    mode: 'nearest',
    intersect: false,
  },
  plugins: {
    legend: {
      display: true,
      labels: {
        boxWidth: 16,
      },
    },
    tooltip: {
      callbacks: {
        title: (items) => (items.length ? formatDateTime(items[0].parsed.x) : ''),
        label: (ctx) => {
          const unit = selectedMetricUnit.value ? ` ${selectedMetricUnit.value}` : '';
          return `${ctx.dataset.label}: ${formatNum(ctx.parsed.y)}${unit}`;
        },
      },
    },
  },
  scales: {
    x: {
      type: 'linear',
      grid: { color: 'rgba(148, 163, 184, 0.2)' },
      ticks: {
        maxTicksLimit: 9,
        callback: (value) => formatAxisTick(Number(value)),
      },
      title: {
        display: true,
        text: 'Время',
      },
    },
    y: {
      beginAtZero: true,
      max: selectedMetricUnit.value === '%' ? 100 : undefined,
      grid: { color: 'rgba(148, 163, 184, 0.2)' },
      title: {
        display: true,
        text: selectedMetricUnit.value ? `Значение (${selectedMetricUnit.value})` : 'Значение',
      },
    },
  },
}));

const formatDateTime = (value) => {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
  } catch {
    return String(value);
  }
};

const formatAxisTick = (value) => {
  if (!Number.isFinite(value)) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

const formatNum = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
};

const formatPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
};

const riskPercent = (value) => {
  const n = Number(value);
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(100, n * 100));
};

const runStatusLabel = (value) => {
  if (value === 'success') return 'Успешно';
  if (value === 'failed') return 'Ошибка';
  if (value === 'running') return 'Выполняется';
  if (value === 'pending') return 'В очереди';
  return 'Нет данных';
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
  return 'Неизвестно';
};

const stateSeverity = (value) => {
  if (value === 's0') return 'success';
  if (value === 's1') return 'warning';
  if (value === 's2') return 'danger';
  return 'secondary';
};

const metricLabel = (code) => metricMap[code]?.label || code;
const metricUnit = (code) => metricMap[code]?.unit || '';

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
  } catch {
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
    const res = await apiClient.get(`forecast-runs/latest/?serial=${encodeURIComponent(selectedSerial.value)}&model_kind=sarima`);
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

const loadMetricScatter = async () => {
  rawScatterPoints.value = [];
  if (!selectedDeviceId.value || !selectedMetricCode.value) return;
  chartLoading.value = true;
  try {
    const params = new URLSearchParams();
    params.set('device', String(selectedDeviceId.value));
    params.set('code', selectedMetricCode.value);
    params.set('since_minutes', String(chartWindowMinutes.value));
    params.set('ordering', 'timestamp');
    params.set('limit', '5000');
    const res = await apiClient.get(`metrics-raw/?${params.toString()}`);
    rawScatterPoints.value = unwrap(res)
      .map((row) => ({
        x: Number(new Date(row.timestamp).getTime()),
        y: Number(row.value),
      }))
      .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
  } catch {
    rawScatterPoints.value = [];
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить точки для графика', life: 3500 });
  } finally {
    chartLoading.value = false;
  }
};

const loadAll = async () => {
  loading.value = true;
  try {
    await loadLatestRun();
    await Promise.all([loadLatestState(), loadForecastPoints(), loadMetricScatter()]);
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
    toast.add({
      severity: 'success',
      summary: 'Готово',
      detail: `Тестовые данные созданы (${res.data.created_points || 0} точек прогноза)`,
      life: 3200,
    });
    await refreshAll();
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось сгенерировать тестовые данные';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4200 });
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
    const failed = Number(res?.data?.failed_runs || 0);
    if (failed > 0) {
      toast.add({
        severity: 'warn',
        summary: 'Внимание',
        detail: `SARIMA прогноз завершен с ошибками: ${failed}`,
        life: 3800,
      });
    } else {
      toast.add({ severity: 'success', summary: 'Готово', detail: 'SARIMA прогноз выполнен', life: 3000 });
    }
    await loadAll();
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось выполнить SARIMA прогноз';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    runningBaseline.value = false;
  }
};

watch(selectedDeviceId, () => {
  if (selectedDeviceId.value) localStorage.setItem(DEVICE_STORAGE_KEY, String(selectedDeviceId.value));
  else localStorage.removeItem(DEVICE_STORAGE_KEY);
  loadAll();
});

watch(selectedHorizon, () => {
  loadAll();
});

watch([selectedMetricCode, chartWindowMinutes], () => {
  loadMetricScatter();
});

onMounted(async () => {
  await loadDevices();
  await loadAll();
});
</script>

<style scoped>
.filters-grid {
  display: grid;
  grid-template-columns: minmax(260px, 2fr) minmax(180px, 1fr) minmax(250px, 1.3fr);
  gap: 1rem;
  align-items: end;
}

.actions-grid,
.chart-controls {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 0.9rem;
  align-items: end;
}

.field-block label {
  display: block;
  margin-bottom: 0.35rem;
  color: #475569;
  font-size: 0.86rem;
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

.action-button {
  display: flex;
  align-items: end;
}

.run-meta {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  min-height: 2.25rem;
}

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

.factors-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.8rem;
}

.factor-card {
  border: 1px solid #dbe6f2;
  border-radius: 10px;
  background: #f8fbff;
  padding: 0.7rem;
}

.factor-title {
  font-size: 0.92rem;
  font-weight: 700;
  color: #0f172a;
}

.factor-meta {
  font-size: 0.82rem;
  color: #475569;
  margin-top: 0.2rem;
}

.risk-track {
  margin-top: 0.45rem;
  height: 7px;
  border-radius: 999px;
  background: #dbeafe;
  overflow: hidden;
}

.risk-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #22c55e, #f59e0b, #ef4444);
}

.factor-risk {
  margin-top: 0.35rem;
  font-size: 0.77rem;
  color: #64748b;
}

.chart-wrap {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #ffffff;
  padding: 0.7rem;
}

.scatter-chart {
  height: 21rem;
}

@media (max-width: 1180px) {
  .filters-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .scatter-chart {
    height: 16rem;
  }
}
</style>
