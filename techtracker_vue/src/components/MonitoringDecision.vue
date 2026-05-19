<template>
  <div class="decision-page p-4">
    <Toast />

    <PageHeader
      title="Результаты СППР"
      :refreshable="true"
      :loading="loadingAny"
      help-title="Гайд: результаты СППР"
      help-intro="Здесь СППР выбирает действие с минимальными ожидаемыми потерями."
      :help-steps="decisionHelpSteps"
      help-note="Перед запуском рекомендации убедитесь, что по устройству уже рассчитан риск."
      @refresh="refreshAll"
    />

    <FilterPanel
      class="mb-3"
      title="1. Параметры запуска"
    >

      <div class="filters-grid">
        <div class="field-block">
          <label>Устройство</label>
          <Dropdown
            v-model="selectedDeviceId"
            :options="deviceOptions"
            optionLabel="label"
            optionValue="id"
            :loading="loadingDevices"
            class="w-full"
            placeholder="Выберите устройство"
          />
        </div>

        <div class="field-block">
          <label>Горизонт оценки</label>
          <Dropdown
            v-model="selectedHorizon"
            :options="horizonOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>

        <div class="field-block">
          <label>Режим</label>
          <Dropdown
            v-model="selectedMode"
            :options="modeOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>

        <div class="field-block">
          <label>Политика (если нужно вручную)</label>
          <Dropdown
            v-model="selectedPolicyId"
            :options="policyOptions"
            optionLabel="label"
            optionValue="id"
            class="w-full"
            :loading="loadingPolicies"
          />
        </div>
      </div>

      <div class="advanced-wrap mt-2" v-if="selectedMode === 'advanced'">
        <div class="filters-grid advanced-grid">
          <div class="field-block">
            <label>Вес Маркова в риске</label>
            <InputNumber
              v-model="overallWeightMarkov"
              :min="0"
              :max="1"
              :step="0.05"
              mode="decimal"
              :minFractionDigits="2"
              :maxFractionDigits="2"
              class="w-full"
            />
          </div>
          <div class="field-block">
            <label>Вес Bayes</label>
            <InputNumber
              v-model="bayesWeight"
              :min="0"
              :max="1"
              :step="0.05"
              mode="decimal"
              :minFractionDigits="2"
              :maxFractionDigits="2"
              class="w-full"
            />
          </div>
          <div class="field-block">
            <label>Вес AHP</label>
            <InputNumber
              v-model="ahpWeight"
              :min="0"
              :max="1"
              :step="0.05"
              mode="decimal"
              :minFractionDigits="2"
              :maxFractionDigits="2"
              class="w-full"
            />
          </div>
          <div class="field-block">
            <label>Порог риска метрики</label>
            <InputNumber
              v-model="riskMetricMinRisk"
              :min="0"
              :max="1"
              :step="0.01"
              mode="decimal"
              :minFractionDigits="2"
              :maxFractionDigits="2"
              class="w-full"
            />
          </div>
          <div class="field-block">
            <label>Порог вклада метрики</label>
            <InputNumber
              v-model="riskMetricMinContribution"
              :min="0"
              :max="1"
              :step="0.01"
              mode="decimal"
              :minFractionDigits="2"
              :maxFractionDigits="2"
              class="w-full"
            />
          </div>
        </div>

        <div class="tips-box mt-2" v-if="activeCriteriaList.length">
          <strong>Тонкая настройка критериев (по желанию):</strong>
          <span class="text-500">если оставить нули, система возьмет веса из сохраненной AHP-матрицы.</span>
          <div class="criteria-grid mt-2">
            <div v-for="criterion in activeCriteriaList" :key="criterion.id" class="field-block">
              <label>{{ criterion.name }}</label>
              <InputNumber v-model="sensitivityDraft[criterion.code]" :min="0" :max="100" :step="1" class="w-full" />
            </div>
          </div>
        </div>
      </div>

      <div class="actions-row mt-3">
        <Button
          icon="pi pi-play"
          :label="selectedMode === 'advanced' ? 'Получить расширенную рекомендацию' : 'Получить рекомендацию'"
          :loading="loadingRun"
          :disabled="!selectedDeviceId || loadingDevices"
          @click="runRecommendation"
        />
      </div>
    </FilterPanel>

    <div v-if="!runResult && !loadingRun" class="card p-3 mb-3">
      <EmptyStateCard
        icon="pi pi-lightbulb"
        title="Рекомендация еще не рассчитана"
        description="Выберите устройство и нажмите «Получить рекомендацию». После расчета появятся итог, сравнение вариантов и форма обратной связи."
      />
    </div>

    <div v-if="runResult" class="card p-3 mb-3">
      <h4 class="m-0">2. Итог</h4>
      <div class="summary-grid mt-2">
        <div class="summary-card summary-main-card">
          <span class="summary-label">Что делать сейчас</span>
          <strong>{{ runResult.recommended_action_name || '-' }}</strong>
          <span class="text-500 text-sm">{{ runResult.recommended_action_code || '' }}</span>
        </div>

        <div class="summary-card">
          <span class="summary-label">Почему выбрано</span>
          <strong>{{ recommendedReasonText }}</strong>
          <span class="text-500 text-sm">{{ runResult.mode === 'advanced' ? 'Bayes + AHP' : 'Bayes' }}</span>
        </div>

        <div class="summary-card">
          <span class="summary-label">Ожидаемые потери</span>
          <strong>{{ formatMoney(recommendedScore?.expected_loss) }}</strong>
          <span class="text-500 text-sm">Чем меньше, тем лучше</span>
        </div>

        <div class="summary-card">
          <span class="summary-label">Контекст риска</span>
          <strong>Общий: {{ formatPercent(runResult.risk_snapshot?.overall_risk) }}</strong>
          <span class="text-500 text-sm">S2: {{ formatPercent(runResult.risk_snapshot?.p_s2) }}</span>
        </div>
      </div>

      <div class="tips-box mt-3">
        <strong>Метрики, на которых основано решение:</strong>
        <div v-if="activeRiskMetrics.length" class="metric-chip-wrap">
          <Tag
            v-for="item in activeRiskMetrics"
            :key="item.metric_code"
            :value="`${metricLabel(item.metric_code)} (risk ${(Number(item.risk || 0) * 100).toFixed(1)}%)`"
            severity="info"
          />
        </div>
        <div v-else class="text-500 text-sm">Активные риск-метрики не переданы backend.</div>
      </div>
    </div>

    <div v-if="runResult" class="card p-3 mb-3">
      <div class="table-head">
        <h4 class="m-0">3. Сравнение вариантов</h4>
        <span class="text-500 text-sm">
          Чем выше score, тем предпочтительнее вариант. Строк: {{ filteredScoreRows.length }} / {{ scoreRows.length }}
        </span>
      </div>
      <div class="table-toolbar mt-2">
        <TablePresetBar
          v-model="decisionScorePreset"
          title="Пресет таблицы"
          aria-label="Пресеты таблицы сравнения"
          :presets="decisionScorePresets"
        />
      </div>

      <DataTable :value="filteredScoreRows" responsiveLayout="scroll" class="mt-2" dataKey="id" stripedRows>
        <template #empty>
          <EmptyStateCard
            icon="pi pi-list"
            title="Нет вариантов для сравнения"
            description="Проверьте политику/действия в настройках СППР и повторите расчет рекомендации."
          />
        </template>
        <Column field="rank" header="#" style="width: 56px" />
        <Column field="action_name" header="Действие" style="min-width: 220px" />
        <Column header="Доступность" style="width: 130px">
          <template #body="{ data }">
            <Tag :value="rowAllowed(data) ? 'Да' : 'Нет'" :severity="rowAllowed(data) ? 'success' : 'warn'" />
          </template>
        </Column>
        <Column header="Ожидаемые потери" style="min-width: 140px">
          <template #body="{ data }">{{ formatMoney(data.expected_loss) }}</template>
        </Column>
        <Column header="Итоговый score" style="min-width: 120px">
          <template #body="{ data }">
            <span :class="{ 'recommended-score': data.is_recommended }">{{ formatNum(data.final_score, 4) }}</span>
          </template>
        </Column>
      </DataTable>

    </div>

    <div v-if="runResult" class="card p-3">
      <div class="table-head">
        <h4 class="m-0">4. Обратная связь (по факту)</h4>
        <span class="text-500 text-sm">Помогает системе точнее рекомендовать в будущем.</span>
      </div>

      <div class="feedback-grid mt-2">
        <div class="field-block">
          <label>Что реально сделали</label>
          <Dropdown
            v-model="feedback.actual_action"
            :options="actionOptions"
            optionLabel="label"
            optionValue="id"
            class="w-full"
            placeholder="Не указано"
            showClear
          />
        </div>
        <div class="field-block">
          <label>Итоговое состояние</label>
          <Dropdown
            v-model="feedback.outcome_state"
            :options="outcomeStateOptions"
            optionLabel="label"
            optionValue="value"
            class="w-full"
          />
        </div>
        <div class="field-block">
          <label>Простой (мин.)</label>
          <InputNumber v-model="feedback.outage_minutes" :min="0" :step="1" class="w-full" />
        </div>
        <div class="field-block">
          <label>Стоимость инцидента</label>
          <InputNumber v-model="feedback.incident_cost" :min="0" :step="100" class="w-full" />
        </div>
      </div>

      <div class="field-block mt-2">
        <label>Комментарий (что пошло не так / что сработало)</label>
        <Textarea v-model="feedback.notes" class="w-full" rows="3" />
      </div>
      <div class="actions-row mt-3">
        <Button icon="pi pi-save" label="Сохранить обратную связь" :loading="savingFeedback" @click="submitFeedback" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import apiClient from '@/api';
import { useToast } from 'primevue/usetoast';
import Toast from 'primevue/toast';
import Button from 'primevue/button';
import Dropdown from 'primevue/dropdown';
import InputNumber from 'primevue/inputnumber';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Tag from 'primevue/tag';
import Textarea from 'primevue/textarea';
import PageHeader from '@/components/ui/PageHeader.vue';
import FilterPanel from '@/components/ui/FilterPanel.vue';
import EmptyStateCard from '@/components/ui/EmptyStateCard.vue';
import TablePresetBar from '@/components/ui/TablePresetBar.vue';
import { useTableFiltersState, useTablePresetState } from '@/composables/useMonitoringTableState';

const toast = useToast();
const DECISION_FILTERS_KEY = 'monitoring_decision_filters';
const DECISION_SCORE_PRESET_KEY = 'monitoring_decision_score_preset';
const decisionHelpSteps = [
  'В верхнем блоке выберите устройство, горизонт и режим расчета.',
  'Нажмите «Получить рекомендацию» и дождитесь завершения.',
  'В карточках «Итог» смотрите, что делать сейчас и какие ожидаемые потери.',
  'В таблице сравнения переключайте пресет, чтобы быстро отфильтровать варианты.',
  'После выполнения действия сохраните обратную связь, чтобы СППР улучшала будущие рекомендации.',
];

const loadingDevices = ref(false);
const loadingPolicies = ref(false);
const loadingCriteria = ref(false);
const loadingActions = ref(false);
const loadingRun = ref(false);
const savingFeedback = ref(false);

const devices = ref([]);
const policies = ref([]);
const criteriaList = ref([]);
const actionsList = ref([]);

const selectedDeviceId = ref(null);
const { state: filterState } = useTableFiltersState(DECISION_FILTERS_KEY, {
  selectedHorizon: '30d',
  selectedMode: 'bayes',
  selectedPolicyId: null,
  overallWeightMarkov: 0.65,
  bayesWeight: 0.5,
  ahpWeight: 0.5,
  riskMetricMinRisk: 0.08,
  riskMetricMinContribution: 0.03,
});
const selectedHorizon = computed({
  get: () => String(filterState.selectedHorizon || '30d'),
  set: (value) => { filterState.selectedHorizon = String(value || '30d'); },
});
const selectedMode = computed({
  get: () => String(filterState.selectedMode || 'bayes'),
  set: (value) => { filterState.selectedMode = String(value || 'bayes'); },
});
const selectedPolicyId = computed({
  get: () => (filterState.selectedPolicyId == null ? null : Number(filterState.selectedPolicyId)),
  set: (value) => { filterState.selectedPolicyId = value == null ? null : Number(value); },
});
const overallWeightMarkov = computed({
  get: () => Number(filterState.overallWeightMarkov ?? 0.65),
  set: (value) => { filterState.overallWeightMarkov = Number(value ?? 0.65); },
});
const bayesWeight = computed({
  get: () => Number(filterState.bayesWeight ?? 0.5),
  set: (value) => { filterState.bayesWeight = Number(value ?? 0.5); },
});
const ahpWeight = computed({
  get: () => Number(filterState.ahpWeight ?? 0.5),
  set: (value) => { filterState.ahpWeight = Number(value ?? 0.5); },
});
const riskMetricMinRisk = computed({
  get: () => Number(filterState.riskMetricMinRisk ?? 0.08),
  set: (value) => { filterState.riskMetricMinRisk = Number(value ?? 0.08); },
});
const riskMetricMinContribution = computed({
  get: () => Number(filterState.riskMetricMinContribution ?? 0.03),
  set: (value) => { filterState.riskMetricMinContribution = Number(value ?? 0.03); },
});
const decisionScorePreset = useTablePresetState(DECISION_SCORE_PRESET_KEY, 'recommended', ['recommended', 'allowed', 'all']);

const runResult = ref(null);
const sensitivityDraft = reactive({});

const feedback = reactive({
  actual_action: null,
  outcome_state: 'unknown',
  outage_minutes: 0,
  incident_cost: 0,
  notes: '',
});

const horizonOptions = [
  { label: '24 часа', value: '24h' },
  { label: '7 дней', value: '7d' },
  { label: '30 дней', value: '30d' },
];

const modeOptions = [
  { label: 'Базовый (Bayes)', value: 'bayes' },
  { label: 'Точный (Bayes + AHP)', value: 'advanced' },
];

const outcomeStateOptions = [
  { label: 'S0 (норма)', value: 's0' },
  { label: 'S1 (деградация)', value: 's1' },
  { label: 'S2 (предаварийное)', value: 's2' },
  { label: 'Unknown', value: 'unknown' },
];

const METRIC_LABELS = {
  cpu_load_total: 'Загрузка CPU',
  mem_usage_percent: 'Использование памяти',
  ping_latency_gateway: 'Сетевая задержка до шлюза',
  net_bytes_sent: 'Трафик исходящий',
  net_bytes_recv: 'Трафик входящий',
  system_temperature: 'Температура системы',
  storcli_drive_temperature: 'Температура диска RAID',
  storcli_predictive_failure_count: 'Predictive failure (RAID)',
  storcli_drive_wear_percent: 'Износ диска RAID',
};

const loadingAny = computed(() => (
  loadingDevices.value || loadingPolicies.value || loadingCriteria.value || loadingActions.value || loadingRun.value
));

const deviceOptions = computed(() => (
  devices.value.map((d) => ({ id: d.id, label: `${d.name} (${d.serial_number})` }))
));

const policyOptions = computed(() => {
  const opts = [{ id: null, label: 'Авто (рекомендовано)' }];
  for (const p of policies.value) {
    const scope = p.scope || 'global';
    opts.push({ id: p.id, label: `${p.name} v${p.version} [${scope}]` });
  }
  return opts;
});

const actionOptions = computed(() => (
  actionsList.value.map((a) => ({ id: a.id, label: `${a.name} (${a.code})` }))
));

const activeCriteriaList = computed(() => criteriaList.value.filter((row) => row.is_active));

const scoreRows = computed(() => {
  const rows = runResult.value?.scores || [];
  return [...rows].sort((a, b) => (a.rank || 0) - (b.rank || 0));
});
const decisionScorePresets = [
  { value: 'recommended', label: 'Рекомендованный', description: 'Показывает только вариант, выбранный системой.' },
  { value: 'allowed', label: 'Только доступные', description: 'Скрывает варианты, недоступные по ограничениям.' },
  { value: 'all', label: 'Все', description: 'Полный список вариантов для сравнения.' },
];
const filteredScoreRows = computed(() => {
  if (decisionScorePreset.value === 'recommended') {
    return scoreRows.value.filter((row) => Boolean(row.is_recommended));
  }
  if (decisionScorePreset.value === 'allowed') {
    return scoreRows.value.filter((row) => rowAllowed(row));
  }
  return scoreRows.value;
});

const recommendedScore = computed(() => scoreRows.value.find((x) => x.is_recommended) || null);
const activeRiskMetrics = computed(() => runResult.value?.explanation?.risk_context?.active_metrics || []);

const recommendedReasonText = computed(() => {
  if (!recommendedScore.value) return '-';
  if (recommendedScore.value?.explanation?.allowed === false) return 'Вариант ограничен условиями';
  return 'Минимальные ожидаемые потери и лучший итоговый score';
});

function formatNum(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return n.toFixed(digits);
}

function formatMoney(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return `${n.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽`;
}

function formatPercent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return `${(n * 100).toFixed(1)}%`;
}

function metricLabel(code) {
  const key = String(code || '').trim().toLowerCase();
  return METRIC_LABELS[key] || key || 'Метрика';
}

function rowAllowed(row) {
  return Boolean(row?.explanation?.allowed ?? true);
}

function getResponseRows(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
}

function buildSensitivityPayload() {
  const out = {};
  for (const criterion of activeCriteriaList.value) {
    const raw = Number(sensitivityDraft[criterion.code]);
    if (Number.isFinite(raw) && raw > 0) {
      out[criterion.code] = raw;
    }
  }
  return out;
}

function resetFeedbackDefaults() {
  feedback.actual_action = runResult.value?.recommended_action || null;
  feedback.outcome_state = 'unknown';
  feedback.outage_minutes = 0;
  feedback.incident_cost = 0;
  feedback.notes = '';
}

async function fetchDevices() {
  loadingDevices.value = true;
  try {
    const res = await apiClient.get('devices/?ordering=name');
    devices.value = getResponseRows(res.data);
    if (!selectedDeviceId.value && devices.value.length) {
      selectedDeviceId.value = devices.value[0].id;
    }
  } finally {
    loadingDevices.value = false;
  }
}

async function fetchPolicies() {
  loadingPolicies.value = true;
  try {
    const params = new URLSearchParams();
    params.set('ordering', '-updated_at');
    params.set('is_active', 'true');
    params.set('horizon', selectedHorizon.value);
    const res = await apiClient.get(`decision-policies/?${params.toString()}`);
    policies.value = getResponseRows(res.data);
    if (selectedPolicyId.value && !policies.value.some((p) => p.id === selectedPolicyId.value)) {
      selectedPolicyId.value = null;
    }
  } finally {
    loadingPolicies.value = false;
  }
}

async function fetchCriteria() {
  loadingCriteria.value = true;
  try {
    const res = await apiClient.get('decision-criteria/?is_active=true&ordering=name');
    criteriaList.value = getResponseRows(res.data);
    for (const criterion of criteriaList.value) {
      if (typeof sensitivityDraft[criterion.code] === 'undefined') {
        sensitivityDraft[criterion.code] = 0;
      }
    }
  } finally {
    loadingCriteria.value = false;
  }
}

async function fetchActions() {
  loadingActions.value = true;
  try {
    const res = await apiClient.get('decision-actions/?is_active=true&ordering=name');
    actionsList.value = getResponseRows(res.data);
  } finally {
    loadingActions.value = false;
  }
}

async function runRecommendation() {
  if (!selectedDeviceId.value) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Выберите устройство', life: 2200 });
    return;
  }

  loadingRun.value = true;
  try {
    const payload = {
      device: selectedDeviceId.value,
      horizon: selectedHorizon.value,
      policy_id: selectedPolicyId.value || undefined,
      overall_weight_markov: Number(overallWeightMarkov.value ?? 0.65),
      risk_metric_min_risk: Number(riskMetricMinRisk.value ?? 0.08),
      risk_metric_min_contribution: Number(riskMetricMinContribution.value ?? 0.03),
      risk_metric_top_k_fallback: 3,
    };

    let endpoint = 'decision-runs/recommend/';
    if (selectedMode.value === 'advanced') {
      endpoint = 'decision-runs/recommend_advanced/';
      payload.bayes_weight = Number(bayesWeight.value ?? 0.5);
      payload.ahp_weight = Number(ahpWeight.value ?? 0.5);
      payload.sensitivity_weights = buildSensitivityPayload();
    }

    const res = await apiClient.post(endpoint, payload);
    runResult.value = res.data;
    resetFeedbackDefaults();

    if (runResult.value?.policy && selectedPolicyId.value !== runResult.value.policy) {
      selectedPolicyId.value = runResult.value.policy;
    }

    toast.add({ severity: 'success', summary: 'Готово', detail: 'Рекомендация рассчитана', life: 2200 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Расчет рекомендации не выполнен';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    loadingRun.value = false;
  }
}

async function submitFeedback() {
  if (!runResult.value?.id) return;

  savingFeedback.value = true;
  try {
    const res = await apiClient.post(`decision-runs/${runResult.value.id}/feedback/`, {
      actual_action: feedback.actual_action,
      outcome_state: feedback.outcome_state,
      outage_minutes: Number(feedback.outage_minutes || 0),
      incident_cost: Number(feedback.incident_cost || 0),
      notes: feedback.notes || '',
    });
    runResult.value = res.data;
    toast.add({ severity: 'success', summary: 'Сохранено', detail: 'Обратная связь сохранена', life: 2200 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось сохранить обратную связь';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    savingFeedback.value = false;
  }
}

async function refreshAll() {
  await Promise.all([fetchDevices(), fetchPolicies(), fetchCriteria(), fetchActions()]);
}

watch(selectedHorizon, async () => {
  await fetchPolicies();
});

onMounted(async () => {
  await refreshAll();
});
</script>

<style scoped>
.decision-page {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.filters-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(200px, 1fr));
  gap: 0.75rem 1rem;
}

.advanced-grid {
  grid-template-columns: repeat(3, minmax(180px, 1fr));
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.field-block label {
  font-size: 0.82rem;
  color: #64748b;
  font-weight: 600;
}

.actions-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(180px, 1fr));
  gap: 0.75rem;
}

.summary-card {
  border: 1px solid #e6edf5;
  border-radius: 10px;
  padding: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.summary-main-card {
  border-color: #99f6e4;
  background: #f0fdfa;
}

.summary-label {
  color: #64748b;
  font-size: 0.83rem;
}

.table-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.recommended-score {
  color: #059669;
  font-weight: 700;
}

.feedback-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(180px, 1fr));
  gap: 0.75rem 1rem;
}

.tips-box {
  border: 1px solid #dbe5ef;
  border-radius: 8px;
  padding: 0.75rem;
  background: #fbfdff;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.criteria-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
  gap: 0.6rem;
}

.metric-chip-wrap {
  margin-top: 0.4rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.help-list {
  margin: 0;
  padding-left: 1.1rem;
  color: #334155;
}

@media (max-width: 1200px) {
  .filters-grid,
  .summary-grid,
  .feedback-grid,
  .criteria-grid {
    grid-template-columns: repeat(2, minmax(180px, 1fr));
  }

  .advanced-grid {
    grid-template-columns: repeat(2, minmax(160px, 1fr));
  }
}

@media (max-width: 760px) {
  .table-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .filters-grid,
  .advanced-grid,
  .summary-grid,
  .feedback-grid,
  .criteria-grid {
    grid-template-columns: 1fr;
  }
}
</style>
