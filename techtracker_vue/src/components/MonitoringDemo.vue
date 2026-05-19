<template>
  <div class="monitoring-demo-page p-4 page-shell">
    <Toast />

    <PageHeader
      title="Мониторинг - Демо"
      :refreshable="true"
      :loading="loadingDevices"
      help-title="Гайд: мониторинг демо"
      help-intro="Страница создает тестовые данные, чтобы проверить интерфейс и сценарии без боевых инцидентов."
      :help-steps="demoHelpSteps"
      help-note="Рекомендуется запускать demo-генерацию на отдельном тестовом устройстве."
      @refresh="loadDevices"
    />

    <FilterPanel class="mb-3" title="Контекст генерации">
      <div class="settings-grid">
        <div class="field-block field-wide">
          <label>Устройство</label>
          <Dropdown
            v-model="selectedDeviceId"
            :options="deviceOptions"
            optionLabel="label"
            optionValue="id"
            placeholder="Выберите устройство"
            class="w-full mt-2"
            :loading="loadingDevices"
          />
        </div>
      </div>
    </FilterPanel>

    <div class="card p-4 mb-3">
      <div class="block-head">
        <div>
          <h4 class="m-0">Параметры генерации</h4>
        </div>
      </div>

      <div class="settings-grid mt-3">
        <div class="field-block">
          <label>Количество demo-прогонов</label>
          <InputNumber v-model="seedRuns" :min="1" :max="20" class="w-full mt-2" />
        </div>

        <div class="field-block">
          <label>Профиль нагрузки</label>
          <Dropdown
            v-model="selectedProfileCode"
            :options="profileOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full mt-2"
          />
        </div>

        <div class="field-block">
          <label>Очистить старые demo-данные</label>
          <div class="switch-box mt-2">
            <InputSwitch v-model="seedClear" />
            <span>{{ seedClear ? 'Да, очистить' : 'Нет, сохранить' }}</span>
          </div>
        </div>

        <div class="field-block">
          <label>Создать raw history</label>
          <div class="switch-box mt-2">
            <InputSwitch v-model="seedWithRawHistory" />
            <span>{{ seedWithRawHistory ? 'Да, создать историю' : 'Нет, только прогнозы' }}</span>
          </div>
        </div>
      </div>

      <div class="schedule-card mt-3">
        <div class="schedule-head">
          <h5 class="m-0">Период и рабочий график</h5>
          <span class="text-500 text-sm">По умолчанию — офисный сервер: пн-пт, 08:30-17:30, обед 13:00-14:00, backup 21:00-23:00</span>
        </div>

        <div class="settings-grid mt-3">
          <div class="field-block">
            <label>Дата начала</label>
            <input v-model="historyStartDate" type="date" class="native-input mt-2" />
          </div>

          <div class="field-block">
            <label>Дата окончания</label>
            <input v-model="historyEndDate" type="date" class="native-input mt-2" />
          </div>

          <div class="field-block">
            <label>Начало рабочего дня</label>
            <input v-model="workdayStart" type="time" class="native-input mt-2" />
          </div>

          <div class="field-block">
            <label>Конец рабочего дня</label>
            <input v-model="workdayEnd" type="time" class="native-input mt-2" />
          </div>

          <div class="field-block">
            <label>Начало обеда</label>
            <input v-model="lunchStart" type="time" class="native-input mt-2" />
          </div>

          <div class="field-block">
            <label>Конец обеда</label>
            <input v-model="lunchEnd" type="time" class="native-input mt-2" />
          </div>

          <div class="field-block">
            <label>Начало backup-окна</label>
            <input v-model="backupStart" type="time" class="native-input mt-2" />
          </div>

          <div class="field-block">
            <label>Конец backup-окна</label>
            <input v-model="backupEnd" type="time" class="native-input mt-2" />
          </div>
        </div>

        <div class="settings-grid mt-3">
          <div class="field-block">
            <label>Рабочие дни</label>
            <div class="day-grid mt-2">
              <label v-for="day in weekdayOptions" :key="`work-${day.value}`" class="day-chip">
                <Checkbox v-model="workdays" :value="day.value" />
                <span>{{ day.label }}</span>
              </label>
            </div>
          </div>

          <div class="field-block">
            <label>Дни backup</label>
            <div class="day-grid mt-2">
              <label v-for="day in weekdayOptions" :key="`backup-${day.value}`" class="day-chip">
                <Checkbox v-model="backupDays" :value="day.value" />
                <span>{{ day.label }}</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <div class="scenario-card mt-3">
        <div class="schedule-head">
          <h5 class="m-0">Сценарий деградации</h5>
          <span class="text-500 text-sm">Без выбросов: только плавный рост и более медленное восстановление выбранных метрик.</span>
        </div>

        <div class="field-block mt-3">
          <label>Какие метрики ухудшать</label>
          <div class="day-grid mt-2">
            <label v-for="item in degradationMetricOptions" :key="item.value" class="day-chip metric-chip">
              <Checkbox v-model="degradedMetricCodes" :value="item.value" />
              <span>{{ item.label }}</span>
            </label>
          </div>
        </div>

        <div class="settings-grid mt-3">
          <div class="field-block">
            <label>Коэффициент роста</label>
            <InputNumber
              v-model="degradationStrength"
              :min="0"
              :max="3"
              :step="0.1"
              mode="decimal"
              :minFractionDigits="2"
              :maxFractionDigits="2"
              class="w-full mt-2"
            />
            <small>Плавно тянет выбранные метрики вверх. Значение 1.00 — базовый рост, 2.00 — рост примерно в 2 раза сильнее.</small>
          </div>

          <div class="field-block">
            <label>Коэффициент залипания плохого режима</label>
            <InputNumber
              v-model="badModePersistence"
              :min="0"
              :max="1"
              :step="0.05"
              mode="decimal"
              :minFractionDigits="2"
              :maxFractionDigits="2"
              class="w-full mt-2"
            />
            <small>Чем выше значение, тем медленнее выбранные метрики возвращаются к норме после нагрузки.</small>
          </div>
        </div>
      </div>

      <div class="action-row">
        <Button
          icon="pi pi-database"
          label="Сгенерировать demo-данные"
          :loading="seeding"
          @click="seedDemo"
        />
        <span class="text-500 text-sm">
          История будет создана для выбранного устройства{{ selectedDeviceLabel ? `: ${selectedDeviceLabel}` : '' }}.
        </span>
      </div>
    </div>

    <div class="card p-4" v-if="lastSeedResult">
      <div class="block-head">
        <div>
          <h4 class="m-0">Последний результат</h4>
        </div>
        <Tag value="Готово" severity="success" />
      </div>

      <div class="result-grid mt-3">
        <div class="result-card">
          <span class="result-label">Создано прогонов</span>
          <strong>{{ lastSeedResult.created_runs ?? '—' }}</strong>
        </div>
        <div class="result-card">
          <span class="result-label">Точек прогноза</span>
          <strong>{{ lastSeedResult.created_points ?? '—' }}</strong>
        </div>
        <div class="result-card">
          <span class="result-label">Оценок состояний</span>
          <strong>{{ lastSeedResult.created_states ?? '—' }}</strong>
        </div>
        <div class="result-card">
          <span class="result-label">Raw history</span>
          <strong>{{ Number(lastSeedResult.created_raw_metrics || 0) > 0 ? formatPeriod(lastSeedResult.history_start_at, lastSeedResult.history_end_at) : 'не создавалась' }}</strong>
        </div>
        <div class="result-card">
          <span class="result-label">Профиль</span>
          <strong>{{ lastSeedResult.profile_label || '—' }}</strong>
        </div>
        <div class="result-card">
          <span class="result-label">Сценарий деградации</span>
          <strong>{{ formatScenario(lastSeedResult.scenario) }}</strong>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Checkbox from 'primevue/checkbox';
import Dropdown from 'primevue/dropdown';
import InputNumber from 'primevue/inputnumber';
import InputSwitch from 'primevue/inputswitch';
import Tag from 'primevue/tag';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';
import { useMonitoringDeviceStore } from '@/stores/monitoringDevice';
import PageHeader from '@/components/ui/PageHeader.vue';
import FilterPanel from '@/components/ui/FilterPanel.vue';

const toast = useToast();
const demoHelpSteps = [
  'Выберите устройство, для которого нужно создать тестовую историю.',
  'Задайте период истории датами, а не количеством дней.',
  'Выберите профиль нагрузки и при необходимости подправьте рабочий график, обед и backup-окно.',
  'Если нужно показать деградацию, выберите проблемные метрики и задайте коэффициенты плавного роста и залипания плохого режима.',
  'Опция очистки удаляет старые demo-записи перед созданием новых.',
  'Нажмите «Сгенерировать demo-данные» и дождитесь успешного завершения.',
  'После генерации проверьте Forecast/Risk/Decision — данные сразу доступны для демонстрации.',
];
const monitoringDeviceStore = useMonitoringDeviceStore();
monitoringDeviceStore.hydrate();

const devices = ref([]);
const loadingDevices = ref(false);
const selectedDeviceId = computed({
  get: () => monitoringDeviceStore.selectedDeviceId,
  set: (value) => monitoringDeviceStore.setSelectedDeviceId(value),
});
const seeding = ref(false);
const lastSeedResult = ref(null);

const seedRuns = ref(1);
const seedClear = ref(true);
const seedWithRawHistory = ref(true);

const profileDefaults = {
  office_weekday: {
    workdayStart: '08:30',
    workdayEnd: '17:30',
    lunchStart: '13:00',
    lunchEnd: '14:00',
    workdays: [0, 1, 2, 3, 4],
    backupStart: '21:00',
    backupEnd: '23:00',
    backupDays: [0, 1, 2, 3, 4],
  },
  always_on: {
    workdayStart: '00:00',
    workdayEnd: '23:59',
    lunchStart: '00:00',
    lunchEnd: '00:00',
    workdays: [0, 1, 2, 3, 4, 5, 6],
    backupStart: '02:00',
    backupEnd: '04:00',
    backupDays: [0, 1, 2, 3, 4, 5, 6],
  },
};
const profileOptions = [
  { value: 'office_weekday', label: 'Офисный сервер' },
  { value: 'always_on', label: 'Круглосуточный сервис' },
];
const weekdayOptions = [
  { value: 0, label: 'Пн' },
  { value: 1, label: 'Вт' },
  { value: 2, label: 'Ср' },
  { value: 3, label: 'Чт' },
  { value: 4, label: 'Пт' },
  { value: 5, label: 'Сб' },
  { value: 6, label: 'Вс' },
];
const degradationMetricOptions = [
  { value: 'cpu_load_total', label: 'Загрузка CPU' },
  { value: 'mem_usage_percent', label: 'Использование памяти' },
  { value: 'net_bytes_sent', label: 'Трафик исходящий' },
  { value: 'net_bytes_recv', label: 'Трафик входящий' },
  { value: 'ping_latency_gateway', label: 'Ping до шлюза' },
  { value: 'system_temperature', label: 'Температура системы' },
  { value: 'storcli_drive_temperature', label: 'Температура диска RAID' },
  { value: 'storcli_predictive_failure_count', label: 'Predictive Failure Count' },
];

const selectedProfileCode = ref('office_weekday');
const historyStartDate = ref('');
const historyEndDate = ref('');
const workdayStart = ref(profileDefaults.office_weekday.workdayStart);
const workdayEnd = ref(profileDefaults.office_weekday.workdayEnd);
const lunchStart = ref(profileDefaults.office_weekday.lunchStart);
const lunchEnd = ref(profileDefaults.office_weekday.lunchEnd);
const backupStart = ref(profileDefaults.office_weekday.backupStart);
const backupEnd = ref(profileDefaults.office_weekday.backupEnd);
const workdays = ref([...profileDefaults.office_weekday.workdays]);
const backupDays = ref([...profileDefaults.office_weekday.backupDays]);
const degradedMetricCodes = ref([]);
const degradationStrength = ref(0);
const badModePersistence = ref(0);

const unwrap = (res) => (Array.isArray(res.data) ? res.data : (res.data?.results || []));

const deviceOptions = computed(() => (
  devices.value.map((device) => ({
    id: device.id,
    label: device.serial_number ? `${device.name} (${device.serial_number})` : device.name,
  }))
));

const selectedDeviceLabel = computed(() => (
  deviceOptions.value.find((item) => item.id === selectedDeviceId.value)?.label || ''
));

const selectedSerial = computed(() => {
  const device = devices.value.find((item) => item.id === selectedDeviceId.value);
  return device?.serial_number || '';
});

const applyProfileDefaults = (code) => {
  const preset = profileDefaults[code] || profileDefaults.office_weekday;
  workdayStart.value = preset.workdayStart;
  workdayEnd.value = preset.workdayEnd;
  lunchStart.value = preset.lunchStart;
  lunchEnd.value = preset.lunchEnd;
  backupStart.value = preset.backupStart;
  backupEnd.value = preset.backupEnd;
  workdays.value = [...preset.workdays];
  backupDays.value = [...preset.backupDays];
};

const setDefaultPeriod = () => {
  const now = new Date();
  const end = now.toISOString().slice(0, 10);
  const start = new Date(now);
  start.setMonth(start.getMonth() - 2);
  historyStartDate.value = start.toISOString().slice(0, 10);
  historyEndDate.value = end;
};

const loadDevices = async () => {
  loadingDevices.value = true;
  try {
    const res = await apiClient.get('devices/?ordering=name');
    devices.value = unwrap(res);
    monitoringDeviceStore.syncWithAvailableIds(devices.value.map((device) => device.id));
  } catch {
    devices.value = [];
    monitoringDeviceStore.setSelectedDeviceId(null);
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить список устройств', life: 3500 });
  } finally {
    loadingDevices.value = false;
  }
};

const seedDemo = async () => {
  seeding.value = true;
  try {
    if (!historyStartDate.value || !historyEndDate.value) {
      toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Укажите период генерации целиком', life: 3200 });
      return;
    }
    if (historyStartDate.value > historyEndDate.value) {
      toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Дата начала должна быть раньше даты окончания', life: 3200 });
      return;
    }
    if (!workdays.value.length) {
      toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Выберите хотя бы один рабочий день', life: 3200 });
      return;
    }

    const payload = {
      runs: seedRuns.value,
      clear: seedClear.value,
      with_raw_history: seedWithRawHistory.value,
      history_start_date: historyStartDate.value,
      history_end_date: historyEndDate.value,
      profile_code: selectedProfileCode.value,
      workday_start: workdayStart.value,
      workday_end: workdayEnd.value,
      lunch_start: lunchStart.value,
      lunch_end: lunchEnd.value,
      workdays: workdays.value,
      backup_start: backupStart.value,
      backup_end: backupEnd.value,
      backup_days: backupDays.value,
      degraded_metric_codes: degradedMetricCodes.value,
      degradation_strength: degradationStrength.value,
      bad_mode_persistence: badModePersistence.value,
    };
    if (selectedSerial.value) payload.serial = selectedSerial.value;

    const res = await apiClient.post('forecast-runs/seed_demo/', payload);
    lastSeedResult.value = res.data || {};
    toast.add({
      severity: 'success',
      summary: 'Готово',
      detail: `Demo-данные созданы (${res.data?.created_points || 0} точек прогноза)`,
      life: 3200,
    });
  } catch (error) {
    const detail = error?.response?.data?.detail || 'Не удалось сгенерировать demo-данные';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4200 });
  } finally {
    seeding.value = false;
  }
};

function formatDate(value) {
  if (!value) return '-';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return String(value);
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  }).format(dt);
}

function formatPeriod(startValue, endValue) {
  if (!startValue || !endValue) return '—';
  return `${formatDate(startValue)} - ${formatDate(endValue)}`;
}

function formatScenario(scenario) {
  if (!scenario || typeof scenario !== 'object') return 'не задан';
  const metrics = Array.isArray(scenario.degraded_metric_codes) ? scenario.degraded_metric_codes : [];
  if (!metrics.length) return 'ровный профиль';
  const labels = metrics
    .map((code) => degradationMetricOptions.find((item) => item.value === code)?.label || code)
    .join(', ');
  return `${labels}; рост=${Number(scenario.degradation_strength || 0).toFixed(2)}, залипание=${Number(scenario.bad_mode_persistence || 0).toFixed(2)}`;
}

watch(selectedProfileCode, (value) => {
  applyProfileDefaults(value);
});

onMounted(() => {
  setDefaultPeriod();
  loadDevices();
});
</script>

<style scoped>
.block-head,
.action-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.schedule-card {
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  padding: 1rem 1.1rem;
}

.scenario-card {
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #fffaf5 100%);
  padding: 1rem 1.1rem;
}

.schedule-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1rem;
}

.field-wide {
  grid-column: span 2;
}

.field-block label {
  display: block;
  margin-bottom: 0.35rem;
  color: #334155;
  font-size: 0.9rem;
  font-weight: 700;
}

.field-block small {
  color: #64748b;
  line-height: 1.45;
}

.hint-panel {
  border-radius: 18px;
  padding: 1rem 1.1rem;
  background: linear-gradient(135deg, #f8fafc 0%, #eef6ff 100%);
  border: 1px solid #dbeafe;
}

.hint-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 0.5rem;
}

.hint-line {
  color: #475569;
  line-height: 1.55;
}

.switch-box {
  min-height: 2.9rem;
  border: 1px solid #d9e2ec;
  border-radius: 14px;
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.7rem 0.85rem;
  background: #fff;
  color: #334155;
}

.native-input {
  width: 100%;
  min-height: 2.9rem;
  border: 1px solid #d9e2ec;
  border-radius: 14px;
  padding: 0.7rem 0.85rem;
  background: #fff;
  color: #334155;
  font: inherit;
}

.day-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.day-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.55rem 0.75rem;
  border: 1px solid #dbe3ee;
  border-radius: 999px;
  background: #f8fafc;
  color: #334155;
}

.metric-chip {
  min-height: 2.6rem;
}

.action-row {
  margin-top: 1.25rem;
  align-items: center;
  flex-wrap: wrap;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.85rem;
}

.result-card {
  border-radius: 16px;
  padding: 0.95rem 1rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.result-label {
  color: #64748b;
  font-size: 0.8rem;
}

@media (max-width: 900px) {
  .field-wide {
    grid-column: span 1;
  }
}

@media (max-width: 640px) {
  .block-head,
  .action-row,
  .schedule-head {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
