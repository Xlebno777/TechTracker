<template>
  <div :class="['decision-settings-page', isEmbedded ? 'p-0' : 'p-4']">
    <Toast />

    <PageHeader
      v-if="!isEmbedded"
      title="Настройки СППР"
      :refreshable="true"
      :loading="loadingAny"
      help-title="Гайд: настройки СППР"
      help-intro="Здесь задаются действия, критерии и политики, по которым система формирует рекомендации."
      :help-steps="decisionSettingsHelpSteps"
      help-note="Если начинаете с нуля, сначала нажмите «Инициализировать базовые настройки»."
      @refresh="refreshAll"
    />

    <FilterPanel class="mb-3 help-card" title="Быстрые действия">
      <template #actions>
        <ModeSwitch
          v-model="settingsUiMode"
          aria-label="Режим настроек СППР"
          :hidden-items="decisionSettingsBasicHidden"
          :show-basic-hint="false"
        />
      </template>
      <div class="actions-row mt-2">
        <Button icon="pi pi-cog" label="Инициализировать базовые настройки" :loading="loadingBootstrap" @click="bootstrapDefaults" />
      </div>
    </FilterPanel>

    <div class="manage-grid mb-3">
      <div class="card p-3 manage-card">
        <h4 class="m-0">Действия (альтернативы)</h4>
        <p class="text-500 mt-1 mb-2">Примеры: «заменить диск», «перенести нагрузку», «ничего не делать».</p>

        <div class="field-block">
          <label>Код действия</label>
          <InputText v-model.trim="actionForm.code" class="w-full" placeholder="replace_ssd_now" />
        </div>
        <div class="field-block mt-2">
          <label>Название для пользователя</label>
          <InputText v-model.trim="actionForm.name" class="w-full" />
        </div>
        <div class="field-block mt-2">
          <label>Описание</label>
          <Textarea v-model="actionForm.description" class="w-full" rows="2" />
        </div>
        <div class="field-block mt-2">
          <label>Связанные метрики (через запятую)</label>
          <InputText
            v-model.trim="actionForm.metric_codes_text"
            class="w-full"
            placeholder="mem_usage_percent, storcli_drive_temperature"
          />
          <small class="text-500">Если указано, действие будет участвовать только когда эти метрики реально вносят риск.</small>
        </div>
        <div v-if="isDecisionSettingsExpert" class="field-block mt-2">
          <label>Группы метрик (опционально)</label>
          <InputText
            v-model.trim="actionForm.metric_groups_text"
            class="w-full"
            placeholder="memory, disk, network, cpu, temperature, degradation"
          />
        </div>
        <div v-if="isDecisionSettingsExpert" class="field-block mt-2">
          <label>Источники прогноза (опционально)</label>
          <InputText
            v-model.trim="actionForm.source_models_text"
            class="w-full"
            placeholder="sarima,lstm,ensemble"
          />
        </div>
        <div v-if="isDecisionSettingsExpert" class="field-block mt-2">
          <label>Нужен резервный хост</label>
          <InputSwitch v-model="actionForm.requires_reserve_host" />
        </div>
        <div v-if="isDecisionSettingsExpert" class="field-block mt-2">
          <label>Только в окно обслуживания</label>
          <InputSwitch v-model="actionForm.requires_maintenance_window" />
        </div>
        <div v-if="isDecisionSettingsExpert && actionForm.requires_maintenance_window" class="form-inline mt-2">
          <div class="field-block">
            <label>Начало окна (час)</label>
            <InputNumber v-model="actionForm.maintenance_start_hour" :min="0" :max="23" class="w-full" />
          </div>
          <div class="field-block">
            <label>Конец окна (час)</label>
            <InputNumber v-model="actionForm.maintenance_end_hour" :min="0" :max="23" class="w-full" />
          </div>
        </div>
        <div v-if="isDecisionSettingsExpert" class="field-block mt-2">
          <label>Доп. JSON (опционально)</label>
          <Textarea v-model="actionForm.extra_constraints_json_text" class="w-full" rows="2" />
          <small class="text-500">Для редких спец-правил. Можно оставить пустым.</small>
        </div>
        <div class="field-block mt-2">
          <label>Активно</label>
          <InputSwitch v-model="actionForm.is_active" />
        </div>

        <div class="actions-row mt-2">
          <Button icon="pi pi-save" label="Сохранить" size="small" :loading="savingAction" @click="saveAction" />
          <Button icon="pi pi-plus" label="Новая" size="small" text @click="resetActionForm" />
          <Button icon="pi pi-trash" label="Удалить" size="small" severity="danger" text :disabled="!actionForm.id" @click="deleteAction" />
        </div>

        <DataTable
          :value="actionsList"
          class="mt-2"
          dataKey="id"
          stripedRows
          selectionMode="single"
          :selection="selectedActionRow"
          @rowSelect="onActionRowSelect"
        >
          <Column field="code" header="Код" />
          <Column field="name" header="Название" />
          <Column header="Статус">
            <template #body="{ data }">
              <Tag :value="data.is_active ? 'active' : 'off'" :severity="data.is_active ? 'success' : 'secondary'" />
            </template>
          </Column>
        </DataTable>
      </div>

      <div class="card p-3 manage-card">
        <h4 class="m-0">Критерии</h4>
        <p class="text-500 mt-1 mb-2">Критерии используются в расширенном режиме Bayes + AHP.</p>

        <div class="field-block">
          <label>Код критерия</label>
          <InputText v-model.trim="criterionForm.code" class="w-full" placeholder="reliability" />
        </div>
        <div class="field-block mt-2">
          <label>Название</label>
          <InputText v-model.trim="criterionForm.name" class="w-full" />
        </div>
        <div class="field-block mt-2">
          <label>Описание</label>
          <Textarea v-model="criterionForm.description" class="w-full" rows="2" />
        </div>
        <div class="field-block mt-2">
          <label>Активно</label>
          <InputSwitch v-model="criterionForm.is_active" />
        </div>

        <div class="actions-row mt-2">
          <Button icon="pi pi-save" label="Сохранить" size="small" :loading="savingCriterion" @click="saveCriterion" />
          <Button icon="pi pi-plus" label="Новый" size="small" text @click="resetCriterionForm" />
          <Button icon="pi pi-trash" label="Удалить" size="small" severity="danger" text :disabled="!criterionForm.id" @click="deleteCriterion" />
        </div>

        <DataTable
          :value="criteriaList"
          class="mt-2"
          dataKey="id"
          stripedRows
          selectionMode="single"
          :selection="selectedCriterionRow"
          @rowSelect="onCriterionRowSelect"
        >
          <Column field="code" header="Код" />
          <Column field="name" header="Название" />
          <Column header="Статус">
            <template #body="{ data }">
              <Tag :value="data.is_active ? 'active' : 'off'" :severity="data.is_active ? 'success' : 'secondary'" />
            </template>
          </Column>
        </DataTable>
      </div>
    </div>

    <div class="manage-grid mb-3">
      <div class="card p-3 manage-card">
        <h4 class="m-0">Политики</h4>
        <p class="text-500 mt-1 mb-2">Политика задает контекст: горизонт, scope и матрицу потерь.</p>

        <div class="field-block">
          <label>Название политики</label>
          <InputText v-model.trim="policyForm.name" class="w-full" />
        </div>

        <div class="form-inline mt-2">
          <div class="field-block">
            <label>Версия</label>
            <InputNumber v-model="policyForm.version" :min="1" class="w-full" />
          </div>
          <div class="field-block">
            <label>Горизонт</label>
            <Dropdown v-model="policyForm.horizon" :options="horizonOptions" optionLabel="label" optionValue="value" class="w-full" />
          </div>
          <div v-if="isDecisionSettingsExpert" class="field-block">
            <label>Scope</label>
            <Dropdown v-model="policyForm.scope" :options="scopeOptions" optionLabel="label" optionValue="value" class="w-full" />
          </div>
        </div>

        <div class="form-inline mt-2">
          <div v-if="isDecisionSettingsExpert" class="field-block">
            <label>Тип устройства (для scope=device_type)</label>
            <Dropdown
              v-model="policyForm.device_type"
              :options="deviceTypeOptions"
              optionLabel="label"
              optionValue="id"
              class="w-full"
              :disabled="policyForm.scope !== 'device_type'"
              showClear
            />
          </div>
          <div v-if="isDecisionSettingsExpert" class="field-block">
            <label>Устройство (для scope=device)</label>
            <Dropdown
              v-model="policyForm.device"
              :options="deviceOptions"
              optionLabel="label"
              optionValue="id"
              class="w-full"
              :disabled="policyForm.scope !== 'device'"
              showClear
            />
          </div>
          <div class="field-block">
            <label>Активно</label>
            <InputSwitch v-model="policyForm.is_active" />
          </div>
        </div>

        <div v-if="isDecisionSettingsExpert" class="field-block mt-2">
          <label>Комментарий</label>
          <Textarea v-model="policyForm.notes" class="w-full" rows="2" />
        </div>

        <div class="actions-row mt-2">
          <Button icon="pi pi-save" label="Сохранить" size="small" :loading="savingPolicy" @click="savePolicy" />
          <Button icon="pi pi-plus" label="Новая" size="small" text @click="resetPolicyForm" />
          <Button icon="pi pi-trash" label="Удалить" size="small" severity="danger" text :disabled="!policyForm.id" @click="deletePolicy" />
        </div>

        <DataTable
          :value="policies"
          class="mt-2"
          dataKey="id"
          stripedRows
          selectionMode="single"
          :selection="selectedPolicyRow"
          @rowSelect="onPolicyRowSelect"
        >
          <Column field="name" header="Политика" />
          <Column field="version" header="v" />
          <Column field="horizon" header="H" />
          <Column field="scope" header="Scope" />
        </DataTable>
      </div>

      <div class="card p-3 manage-card">
        <div class="table-head">
          <h4 class="m-0">Матрица потерь</h4>
          <Dropdown
            v-model="lossPolicyId"
            :options="policyOptionsForLosses"
            optionLabel="label"
            optionValue="id"
            class="loss-policy-dd"
          />
        </div>
        <p class="text-500 mt-1 mb-2">Это ключевые числа для ожидаемых потерь в состояниях S0/S1/S2.</p>

        <div class="form-inline mt-2">
          <div class="field-block">
            <label>Действие</label>
            <Dropdown v-model="lossForm.action" :options="actionOptions" optionLabel="label" optionValue="id" class="w-full" />
          </div>
          <div class="field-block">
            <label>loss_s0</label>
            <InputNumber v-model="lossForm.loss_s0" :min="0" class="w-full" />
          </div>
          <div class="field-block">
            <label>loss_s1</label>
            <InputNumber v-model="lossForm.loss_s1" :min="0" class="w-full" />
          </div>
          <div class="field-block">
            <label>loss_s2</label>
            <InputNumber v-model="lossForm.loss_s2" :min="0" class="w-full" />
          </div>
        </div>

        <div v-if="isDecisionSettingsExpert" class="form-inline mt-2">
          <div class="field-block">
            <label>fixed_cost</label>
            <InputNumber v-model="lossForm.fixed_cost" :min="0" class="w-full" />
          </div>
          <div class="field-block">
            <label>downtime_minutes</label>
            <InputNumber v-model="lossForm.downtime_minutes" :min="0" class="w-full" />
          </div>
          <div class="field-block">
            <label>ops_effort</label>
            <InputNumber v-model="lossForm.ops_effort" :min="0" :max="10" :step="0.1" class="w-full" />
          </div>
        </div>

        <div v-if="isDecisionSettingsExpert" class="field-block mt-2">
          <label>Комментарий</label>
          <Textarea v-model="lossForm.notes" class="w-full" rows="2" />
        </div>

        <div class="actions-row mt-2">
          <Button icon="pi pi-save" label="Сохранить" size="small" :loading="savingLoss" @click="savePolicyLoss" :disabled="!lossPolicyId" />
          <Button icon="pi pi-plus" label="Новая" size="small" text @click="resetLossForm" />
          <Button icon="pi pi-trash" label="Удалить" size="small" severity="danger" text :disabled="!lossForm.id" @click="deletePolicyLoss" />
        </div>

        <DataTable
          :value="policyLossRows"
          class="mt-2"
          dataKey="id"
          stripedRows
          selectionMode="single"
          :selection="selectedLossRow"
          @rowSelect="onLossRowSelect"
        >
          <Column field="action_name" header="Действие" />
          <Column field="loss_s0" header="S0" />
          <Column field="loss_s1" header="S1" />
          <Column field="loss_s2" header="S2" />
          <Column field="fixed_cost" header="Cost" />
        </DataTable>
      </div>
    </div>

    <div v-if="isDecisionSettingsExpert" class="card p-3">
      <div class="table-head">
        <h4 class="m-0">AHP матрица критериев</h4>
        <Dropdown
          v-model="ahpPolicyId"
          :options="policyOptionsForLosses"
          optionLabel="label"
          optionValue="id"
          class="loss-policy-dd"
        />
      </div>
      <p class="text-500 mt-1 mb-2">Меняйте важность критериев попарно (1 = равны, 3 = умеренно важнее, 5 = сильно важнее).</p>

      <div v-if="ahpPairsEditable.length">
        <div class="actions-row mb-2">
          <Tag
            v-if="ahpMatrix"
            :severity="ahpMatrix.is_consistent ? 'success' : 'danger'"
            :value="ahpMatrix.is_consistent ? 'CR в норме' : 'CR высокий'"
          />
          <span v-if="ahpMatrix" class="text-500 text-sm">CR: {{ formatNum(ahpMatrix.cr, 4) }}</span>
          <Button icon="pi pi-save" label="Сохранить AHP" :loading="savingMatrix" @click="saveAhpMatrix" />
        </div>

        <DataTable :value="ahpPairsEditable" dataKey="pair_key" stripedRows>
          <Column field="criterion_i_name" header="Критерий i" />
          <Column field="criterion_j_name" header="Критерий j" />
          <Column header="i / j" style="min-width: 140px">
            <template #body="{ data }">
              <InputNumber
                v-model="data.value"
                :min="0.111111"
                :max="9"
                :step="0.1"
                mode="decimal"
                :minFractionDigits="3"
                :maxFractionDigits="3"
                class="w-full"
              />
            </template>
          </Column>
        </DataTable>
      </div>
      <div v-else class="text-500">Выберите политику для редактирования AHP-матрицы.</div>
    </div>
    <div v-else class="card p-3">
      <div class="table-head">
        <h4 class="m-0">AHP матрица критериев</h4>
        <Tag value="Экспертный режим" severity="info" />
      </div>
      <p class="text-500 mt-2 mb-0">
        В базовом режиме AHP-матрица скрыта, чтобы не перегружать интерфейс.
        Переключитесь в экспертный режим, если нужно редактировать попарные веса критериев.
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed, defineProps, onMounted, reactive, ref, watch } from 'vue';
import apiClient from '@/api';
import { useToast } from 'primevue/usetoast';
import Toast from 'primevue/toast';
import Button from 'primevue/button';
import Dropdown from 'primevue/dropdown';
import InputText from 'primevue/inputtext';
import InputNumber from 'primevue/inputnumber';
import InputSwitch from 'primevue/inputswitch';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Tag from 'primevue/tag';
import Textarea from 'primevue/textarea';
import { useConfirmAction } from '@/composables/useConfirmAction';
import PageHeader from '@/components/ui/PageHeader.vue';
import FilterPanel from '@/components/ui/FilterPanel.vue';
import ModeSwitch from '@/components/ui/ModeSwitch.vue';

const props = defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
});
const isEmbedded = computed(() => Boolean(props.embedded));

const toast = useToast();
const { confirmAction } = useConfirmAction();
const SETTINGS_UI_MODE_KEY = 'monitoring_decision_settings_ui_mode';
const settingsUiMode = ref((() => {
  const raw = localStorage.getItem(SETTINGS_UI_MODE_KEY);
  return raw === 'expert' ? 'expert' : 'basic';
})());
const isDecisionSettingsExpert = computed(() => settingsUiMode.value === 'expert');
const decisionSettingsBasicHidden = [
  'AHP матрица критериев',
  'расширенные ограничения действий (окна обслуживания, резерв, JSON)',
  'продвинутые поля политики и матрицы потерь',
];
const decisionSettingsHelpSteps = [
  'Заполните «Действия» — что система может рекомендовать оператору.',
  'Проверьте «Критерии» — по чему сравниваются альтернативы в расширенном режиме.',
  'Создайте или выберите «Политику»: горизонт, scope и рабочий контекст.',
  'Настройте матрицу потерь — это основа расчета ожидаемых потерь.',
  'Для быстрого старта используйте кнопку инициализации и донастройте под вашу инфраструктуру.',
];

const loadingDevices = ref(false);
const loadingDeviceTypes = ref(false);
const loadingPolicies = ref(false);
const loadingCriteria = ref(false);
const loadingActions = ref(false);
const loadingLosses = ref(false);
const loadingBootstrap = ref(false);
const loadingMatrix = ref(false);

const savingAction = ref(false);
const savingCriterion = ref(false);
const savingPolicy = ref(false);
const savingLoss = ref(false);
const savingMatrix = ref(false);

const devices = ref([]);
const deviceTypes = ref([]);
const policies = ref([]);
const criteriaList = ref([]);
const actionsList = ref([]);
const policyLossRows = ref([]);

const selectedActionRow = ref(null);
const selectedCriterionRow = ref(null);
const selectedPolicyRow = ref(null);
const selectedLossRow = ref(null);

const lossPolicyId = ref(null);
const ahpPolicyId = ref(null);
const ahpMatrix = ref(null);
const ahpPairsEditable = ref([]);

const horizonOptions = [
  { label: '24 часа', value: '24h' },
  { label: '7 дней', value: '7d' },
  { label: '30 дней', value: '30d' },
];

const scopeOptions = [
  { label: 'global', value: 'global' },
  { label: 'device_type', value: 'device_type' },
  { label: 'device', value: 'device' },
];

const actionForm = reactive({
  id: null,
  code: '',
  name: '',
  description: '',
  is_active: true,
  metric_codes_text: '',
  metric_groups_text: '',
  source_models_text: '',
  requires_reserve_host: false,
  requires_maintenance_window: false,
  maintenance_start_hour: 22,
  maintenance_end_hour: 6,
  extra_constraints_json_text: '',
});

const criterionForm = reactive({
  id: null,
  code: '',
  name: '',
  description: '',
  is_active: true,
});

const policyForm = reactive({
  id: null,
  name: '',
  version: 1,
  is_active: true,
  scope: 'global',
  device_type: null,
  device: null,
  horizon: '30d',
  notes: '',
});

const lossForm = reactive({
  id: null,
  action: null,
  loss_s0: 0,
  loss_s1: 0,
  loss_s2: 0,
  fixed_cost: 0,
  downtime_minutes: 0,
  ops_effort: 0,
  notes: '',
});

const loadingAny = computed(() => (
  loadingDevices.value
  || loadingDeviceTypes.value
  || loadingPolicies.value
  || loadingCriteria.value
  || loadingActions.value
  || loadingLosses.value
  || loadingMatrix.value
));

const deviceOptions = computed(() => (
  devices.value.map((d) => ({ id: d.id, label: `${d.name} (${d.serial_number})` }))
));

const deviceTypeOptions = computed(() => (
  deviceTypes.value.map((row) => ({ id: row.id, label: row.name }))
));

const actionOptions = computed(() => (
  actionsList.value.filter((a) => a.is_active).map((a) => ({ id: a.id, label: `${a.name} (${a.code})` }))
));

const policyOptionsForLosses = computed(() => (
  policies.value.map((p) => ({ id: p.id, label: `${p.name} v${p.version} [${p.horizon}]` }))
));

function formatNum(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return n.toFixed(digits);
}

function getResponseRows(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
}

function parseCsv(text) {
  return String(text || '')
    .split(',')
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function toJsonText(value) {
  try {
    return JSON.stringify(value || {}, null, 2);
  } catch (_) {
    return '{}';
  }
}

async function fetchDevices() {
  loadingDevices.value = true;
  try {
    const res = await apiClient.get('devices/?ordering=name');
    devices.value = getResponseRows(res.data);
  } finally {
    loadingDevices.value = false;
  }
}

async function fetchDeviceTypes() {
  loadingDeviceTypes.value = true;
  try {
    const res = await apiClient.get('devicetypes/?ordering=name');
    deviceTypes.value = getResponseRows(res.data);
  } finally {
    loadingDeviceTypes.value = false;
  }
}

async function fetchPolicies() {
  loadingPolicies.value = true;
  try {
    const res = await apiClient.get('decision-policies/?ordering=-updated_at');
    policies.value = getResponseRows(res.data);

    if (lossPolicyId.value && !policies.value.some((p) => p.id === lossPolicyId.value)) {
      lossPolicyId.value = null;
    }
    if (ahpPolicyId.value && !policies.value.some((p) => p.id === ahpPolicyId.value)) {
      ahpPolicyId.value = null;
    }
  } finally {
    loadingPolicies.value = false;
  }
}

async function fetchCriteria() {
  loadingCriteria.value = true;
  try {
    const res = await apiClient.get('decision-criteria/?ordering=name');
    criteriaList.value = getResponseRows(res.data);
  } finally {
    loadingCriteria.value = false;
  }
}

async function fetchActions() {
  loadingActions.value = true;
  try {
    const res = await apiClient.get('decision-actions/?ordering=name');
    actionsList.value = getResponseRows(res.data);
  } finally {
    loadingActions.value = false;
  }
}

function resetActionForm() {
  actionForm.id = null;
  actionForm.code = '';
  actionForm.name = '';
  actionForm.description = '';
  actionForm.is_active = true;
  actionForm.metric_codes_text = '';
  actionForm.metric_groups_text = '';
  actionForm.source_models_text = '';
  actionForm.requires_reserve_host = false;
  actionForm.requires_maintenance_window = false;
  actionForm.maintenance_start_hour = 22;
  actionForm.maintenance_end_hour = 6;
  actionForm.extra_constraints_json_text = '';
  selectedActionRow.value = null;
}

function onActionRowSelect(event) {
  const row = event?.data;
  if (!row) return;
  const constraints = row.constraints_json && typeof row.constraints_json === 'object' ? row.constraints_json : {};
  const extra = { ...constraints };
  delete extra.metric_codes;
  delete extra.metric_groups;
  delete extra.source_models;
  delete extra.metric_match_mode;
  delete extra.requires_reserve_host;
  delete extra.requires_maintenance_window;
  delete extra.maintenance_start_hour;
  delete extra.maintenance_end_hour;

  selectedActionRow.value = row;
  actionForm.id = row.id;
  actionForm.code = row.code || '';
  actionForm.name = row.name || '';
  actionForm.description = row.description || '';
  actionForm.is_active = Boolean(row.is_active);
  actionForm.metric_codes_text = (Array.isArray(constraints.metric_codes) ? constraints.metric_codes : []).join(', ');
  actionForm.metric_groups_text = (Array.isArray(constraints.metric_groups) ? constraints.metric_groups : []).join(', ');
  actionForm.source_models_text = (Array.isArray(constraints.source_models) ? constraints.source_models : []).join(', ');
  actionForm.requires_reserve_host = Boolean(constraints.requires_reserve_host);
  actionForm.requires_maintenance_window = Boolean(constraints.requires_maintenance_window);
  actionForm.maintenance_start_hour = Number(constraints.maintenance_start_hour ?? 22);
  actionForm.maintenance_end_hour = Number(constraints.maintenance_end_hour ?? 6);
  actionForm.extra_constraints_json_text = Object.keys(extra).length ? toJsonText(extra) : '';
}

async function saveAction() {
  if (!actionForm.code || !actionForm.name) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Для действия обязательны код и название', life: 2600 });
    return;
  }
  let extraConstraints = {};
  try {
    extraConstraints = actionForm.extra_constraints_json_text ? JSON.parse(actionForm.extra_constraints_json_text) : {};
  } catch (_) {
    toast.add({ severity: 'error', summary: 'JSON', detail: 'Доп. JSON должен быть валидным', life: 3200 });
    return;
  }

  const metricCodes = parseCsv(actionForm.metric_codes_text);
  const metricGroups = parseCsv(actionForm.metric_groups_text);
  const sourceModels = parseCsv(actionForm.source_models_text);

  const constraints = { ...(extraConstraints || {}) };
  if (metricCodes.length) constraints.metric_codes = metricCodes;
  if (metricGroups.length) constraints.metric_groups = metricGroups;
  if (sourceModels.length) constraints.source_models = sourceModels;
  if (actionForm.requires_reserve_host) constraints.requires_reserve_host = true;
  if (actionForm.requires_maintenance_window) {
    constraints.requires_maintenance_window = true;
    constraints.maintenance_start_hour = Math.max(0, Math.min(23, Number(actionForm.maintenance_start_hour ?? 22)));
    constraints.maintenance_end_hour = Math.max(0, Math.min(23, Number(actionForm.maintenance_end_hour ?? 6)));
  }

  savingAction.value = true;
  try {
    const payload = {
      code: actionForm.code,
      name: actionForm.name,
      description: actionForm.description || '',
      is_active: Boolean(actionForm.is_active),
      constraints_json: constraints,
    };
    if (actionForm.id) {
      await apiClient.patch(`decision-actions/${actionForm.id}/`, payload);
    } else {
      await apiClient.post('decision-actions/', payload);
    }
    await fetchActions();
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Действие сохранено', life: 2200 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось сохранить действие';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    savingAction.value = false;
  }
}

async function deleteAction() {
  if (!actionForm.id) return;
  const ok = await confirmAction({
    header: 'Удаление действия',
    message: 'Удалить выбранное действие?',
    acceptLabel: 'Удалить',
    acceptSeverity: 'danger',
  });
  if (!ok) return;
  savingAction.value = true;
  try {
    const res = await apiClient.delete(`decision-actions/${actionForm.id}/`);
    resetActionForm();
    await Promise.all([fetchActions(), fetchPolicyLosses(lossPolicyId.value)]);
    const detail = res?.data?.detail || 'Действие удалено';
    toast.add({ severity: 'success', summary: 'Готово', detail, life: 3000 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось удалить действие';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    savingAction.value = false;
  }
}

function resetCriterionForm() {
  criterionForm.id = null;
  criterionForm.code = '';
  criterionForm.name = '';
  criterionForm.description = '';
  criterionForm.is_active = true;
  selectedCriterionRow.value = null;
}

function onCriterionRowSelect(event) {
  const row = event?.data;
  if (!row) return;
  selectedCriterionRow.value = row;
  criterionForm.id = row.id;
  criterionForm.code = row.code || '';
  criterionForm.name = row.name || '';
  criterionForm.description = row.description || '';
  criterionForm.is_active = Boolean(row.is_active);
}

async function saveCriterion() {
  if (!criterionForm.code || !criterionForm.name) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Для критерия обязательны код и название', life: 2600 });
    return;
  }
  savingCriterion.value = true;
  try {
    const payload = {
      code: criterionForm.code,
      name: criterionForm.name,
      description: criterionForm.description || '',
      is_active: Boolean(criterionForm.is_active),
    };
    if (criterionForm.id) {
      await apiClient.patch(`decision-criteria/${criterionForm.id}/`, payload);
    } else {
      await apiClient.post('decision-criteria/', payload);
    }
    await fetchCriteria();
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Критерий сохранен', life: 2200 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось сохранить критерий';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    savingCriterion.value = false;
  }
}

async function deleteCriterion() {
  if (!criterionForm.id) return;
  const ok = await confirmAction({
    header: 'Удаление критерия',
    message: 'Удалить выбранный критерий?',
    acceptLabel: 'Удалить',
    acceptSeverity: 'danger',
  });
  if (!ok) return;
  savingCriterion.value = true;
  try {
    const res = await apiClient.delete(`decision-criteria/${criterionForm.id}/`);
    resetCriterionForm();
    await fetchCriteria();
    const detail = res?.data?.detail || 'Критерий удален';
    toast.add({ severity: 'success', summary: 'Готово', detail, life: 3000 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось удалить критерий';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    savingCriterion.value = false;
  }
}

function resetPolicyForm() {
  policyForm.id = null;
  policyForm.name = '';
  policyForm.version = 1;
  policyForm.is_active = true;
  policyForm.scope = 'global';
  policyForm.device_type = null;
  policyForm.device = null;
  policyForm.horizon = '30d';
  policyForm.notes = '';
  selectedPolicyRow.value = null;
}

function onPolicyRowSelect(event) {
  const row = event?.data;
  if (!row) return;
  selectedPolicyRow.value = row;
  policyForm.id = row.id;
  policyForm.name = row.name || '';
  policyForm.version = Number(row.version || 1);
  policyForm.is_active = Boolean(row.is_active);
  policyForm.scope = row.scope || 'global';
  policyForm.device_type = row.device_type || null;
  policyForm.device = row.device || null;
  policyForm.horizon = row.horizon || '30d';
  policyForm.notes = row.notes || '';
  lossPolicyId.value = row.id;
  ahpPolicyId.value = row.id;
}

async function savePolicy() {
  if (!policyForm.name) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'У политики должно быть название', life: 2600 });
    return;
  }
  if (policyForm.scope === 'device_type' && !policyForm.device_type) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Для scope=device_type выберите тип устройства', life: 3000 });
    return;
  }
  if (policyForm.scope === 'device' && !policyForm.device) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Для scope=device выберите устройство', life: 3000 });
    return;
  }

  savingPolicy.value = true;
  try {
    const payload = {
      name: policyForm.name,
      version: Number(policyForm.version || 1),
      is_active: Boolean(policyForm.is_active),
      scope: policyForm.scope,
      device_type: policyForm.scope === 'device_type' ? policyForm.device_type : null,
      device: policyForm.scope === 'device' ? policyForm.device : null,
      horizon: policyForm.horizon,
      notes: policyForm.notes || '',
    };
    if (policyForm.id) {
      await apiClient.patch(`decision-policies/${policyForm.id}/`, payload);
    } else {
      const res = await apiClient.post('decision-policies/', payload);
      if (res?.data?.id) {
        policyForm.id = res.data.id;
      }
    }
    await fetchPolicies();
    if (policyForm.id) {
      lossPolicyId.value = policyForm.id;
      ahpPolicyId.value = policyForm.id;
    }
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Политика сохранена', life: 2200 });
  } catch (e) {
    const detail = e?.response?.data?.detail || JSON.stringify(e?.response?.data || {}) || 'Не удалось сохранить политику';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 5000 });
  } finally {
    savingPolicy.value = false;
  }
}

async function deletePolicy() {
  if (!policyForm.id) return;
  const ok = await confirmAction({
    header: 'Удаление политики',
    message: 'Удалить выбранную политику?',
    acceptLabel: 'Удалить',
    acceptSeverity: 'danger',
  });
  if (!ok) return;
  savingPolicy.value = true;
  try {
    await apiClient.delete(`decision-policies/${policyForm.id}/`);
    const deletedId = policyForm.id;
    resetPolicyForm();
    if (lossPolicyId.value === deletedId) lossPolicyId.value = null;
    if (ahpPolicyId.value === deletedId) ahpPolicyId.value = null;
    await Promise.all([fetchPolicies(), fetchPolicyLosses(lossPolicyId.value)]);
    toast.add({ severity: 'success', summary: 'Удалено', detail: 'Политика удалена', life: 2200 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось удалить политику';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    savingPolicy.value = false;
  }
}

function resetLossForm() {
  lossForm.id = null;
  lossForm.action = null;
  lossForm.loss_s0 = 0;
  lossForm.loss_s1 = 0;
  lossForm.loss_s2 = 0;
  lossForm.fixed_cost = 0;
  lossForm.downtime_minutes = 0;
  lossForm.ops_effort = 0;
  lossForm.notes = '';
  selectedLossRow.value = null;
}

function onLossRowSelect(event) {
  const row = event?.data;
  if (!row) return;
  selectedLossRow.value = row;
  lossForm.id = row.id;
  lossForm.action = row.action;
  lossForm.loss_s0 = Number(row.loss_s0 || 0);
  lossForm.loss_s1 = Number(row.loss_s1 || 0);
  lossForm.loss_s2 = Number(row.loss_s2 || 0);
  lossForm.fixed_cost = Number(row.fixed_cost || 0);
  lossForm.downtime_minutes = Number(row.downtime_minutes || 0);
  lossForm.ops_effort = Number(row.ops_effort || 0);
  lossForm.notes = row.notes || '';
}

async function fetchPolicyLosses(policyId) {
  if (!policyId) {
    policyLossRows.value = [];
    resetLossForm();
    return;
  }
  loadingLosses.value = true;
  try {
    const res = await apiClient.get(`decision-policy-losses/?policy=${encodeURIComponent(policyId)}&ordering=action`);
    policyLossRows.value = getResponseRows(res.data);
  } finally {
    loadingLosses.value = false;
  }
}

async function savePolicyLoss() {
  if (!lossPolicyId.value) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Сначала выберите политику', life: 2600 });
    return;
  }
  if (!lossForm.action) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Выберите действие для строки потерь', life: 2600 });
    return;
  }
  savingLoss.value = true;
  try {
    const payload = {
      policy: lossPolicyId.value,
      action: lossForm.action,
      loss_s0: Number(lossForm.loss_s0 || 0),
      loss_s1: Number(lossForm.loss_s1 || 0),
      loss_s2: Number(lossForm.loss_s2 || 0),
      fixed_cost: Number(lossForm.fixed_cost || 0),
      downtime_minutes: Number(lossForm.downtime_minutes || 0),
      ops_effort: Number(lossForm.ops_effort || 0),
      notes: lossForm.notes || '',
    };
    if (lossForm.id) {
      await apiClient.patch(`decision-policy-losses/${lossForm.id}/`, payload);
    } else {
      await apiClient.post('decision-policy-losses/', payload);
    }
    await fetchPolicyLosses(lossPolicyId.value);
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Строка потерь сохранена', life: 2200 });
  } catch (e) {
    const detail = e?.response?.data?.detail || JSON.stringify(e?.response?.data || {}) || 'Не удалось сохранить строку потерь';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 5000 });
  } finally {
    savingLoss.value = false;
  }
}

async function deletePolicyLoss() {
  if (!lossForm.id) return;
  const ok = await confirmAction({
    header: 'Удаление строки потерь',
    message: 'Удалить выбранную строку потерь?',
    acceptLabel: 'Удалить',
    acceptSeverity: 'danger',
  });
  if (!ok) return;
  savingLoss.value = true;
  try {
    await apiClient.delete(`decision-policy-losses/${lossForm.id}/`);
    resetLossForm();
    await fetchPolicyLosses(lossPolicyId.value);
    toast.add({ severity: 'success', summary: 'Удалено', detail: 'Строка потерь удалена', life: 2200 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось удалить строку потерь';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    savingLoss.value = false;
  }
}

async function bootstrapDefaults() {
  loadingBootstrap.value = true;
  try {
    await apiClient.post('decision-policies/bootstrap_defaults/', {});
    await refreshAll();
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Базовые настройки СППР инициализированы', life: 2500 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось инициализировать базовые настройки';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    loadingBootstrap.value = false;
  }
}

async function loadAhpMatrix(policyId) {
  if (!policyId) {
    ahpMatrix.value = null;
    ahpPairsEditable.value = [];
    return;
  }

  loadingMatrix.value = true;
  try {
    const res = await apiClient.get(`decision-policies/${policyId}/ahp_matrix/`);
    ahpMatrix.value = res.data || null;

    const criteria = ahpMatrix.value?.criteria || [];
    const matrix = ahpMatrix.value?.matrix || [];
    const pairs = [];

    for (let i = 0; i < criteria.length; i += 1) {
      for (let j = i + 1; j < criteria.length; j += 1) {
        const value = Number(matrix?.[i]?.[j]);
        pairs.push({
          pair_key: `${criteria[i].id}_${criteria[j].id}`,
          criterion_i: criteria[i].id,
          criterion_j: criteria[j].id,
          criterion_i_name: criteria[i].name,
          criterion_j_name: criteria[j].name,
          value: Number.isFinite(value) && value > 0 ? value : 1,
        });
      }
    }
    ahpPairsEditable.value = pairs;
  } catch (e) {
    ahpMatrix.value = null;
    ahpPairsEditable.value = [];
    const detail = e?.response?.data?.detail || 'Не удалось загрузить AHP матрицу';
    toast.add({ severity: 'warn', summary: 'AHP', detail, life: 3500 });
  } finally {
    loadingMatrix.value = false;
  }
}

async function saveAhpMatrix() {
  if (!ahpPolicyId.value || !ahpPairsEditable.value.length) return;
  savingMatrix.value = true;
  try {
    const pairs = ahpPairsEditable.value.map((row) => ({
      criterion_i: row.criterion_i,
      criterion_j: row.criterion_j,
      value: Number(row.value) > 0 ? Number(row.value) : 1,
    }));

    const res = await apiClient.post(`decision-policies/${ahpPolicyId.value}/ahp_matrix/`, { pairs });
    ahpMatrix.value = res.data || ahpMatrix.value;
    toast.add({ severity: 'success', summary: 'Готово', detail: 'AHP-матрица сохранена', life: 2200 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось сохранить AHP матрицу';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    savingMatrix.value = false;
  }
}

async function refreshAll() {
  await Promise.all([fetchDevices(), fetchDeviceTypes(), fetchPolicies(), fetchCriteria(), fetchActions()]);
  if (lossPolicyId.value) {
    await fetchPolicyLosses(lossPolicyId.value);
  }
  if (ahpPolicyId.value) {
    await loadAhpMatrix(ahpPolicyId.value);
  }
}

watch(() => policyForm.scope, (scope) => {
  if (scope !== 'device_type') policyForm.device_type = null;
  if (scope !== 'device') policyForm.device = null;
});

watch(lossPolicyId, async (policyId) => {
  await fetchPolicyLosses(policyId);
  if (policyId && !ahpPolicyId.value) {
    ahpPolicyId.value = policyId;
  }
});

watch(ahpPolicyId, async (policyId) => {
  await loadAhpMatrix(policyId);
});

watch(settingsUiMode, (value) => {
  localStorage.setItem(SETTINGS_UI_MODE_KEY, value);
});

onMounted(async () => {
  await refreshAll();
});
</script>

<style scoped>
.decision-settings-page {
  display: flex;
  flex-direction: column;
  gap: 0;
  width: 100%;
  min-width: 0;
}

.help-card {
  border: 1px solid #dbeafe;
  background: #f8fbff;
}

.help-steps {
  margin: 0;
  padding-left: 1.1rem;
  color: #334155;
}

.manage-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 480px), 1fr));
  gap: 1rem;
  min-width: 0;
}

.manage-card {
  border: 1px solid #e6edf5;
  min-width: 0;
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  min-width: 0;
}

.field-block label {
  font-size: 0.82rem;
  color: #64748b;
  font-weight: 600;
}

.form-inline {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr));
  gap: 0.75rem;
  min-width: 0;
}

.actions-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.table-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
  min-width: 0;
}

.loss-policy-dd {
  min-width: min(100%, 18rem);
}

.decision-settings-page :deep(.p-inputtext),
.decision-settings-page :deep(.p-inputnumber),
.decision-settings-page :deep(.p-inputnumber-input),
.decision-settings-page :deep(.p-inputtextarea),
.decision-settings-page :deep(.p-dropdown) {
  width: 100%;
  min-width: 0;
}

.decision-settings-page :deep(.p-datatable-wrapper) {
  overflow: auto;
  max-width: 100%;
}

.decision-settings-page :deep(.p-datatable-table) {
  min-width: 620px;
}

@media (max-width: 1200px) {
  .manage-grid {
    grid-template-columns: 1fr;
  }

  .form-inline {
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr));
  }
}

@media (max-width: 760px) {
  .table-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .form-inline {
    grid-template-columns: 1fr;
  }

  .loss-policy-dd {
    min-width: 0;
    width: 100%;
  }

  .actions-row :deep(.p-button) {
    width: 100%;
    justify-content: center;
  }
}
</style>
