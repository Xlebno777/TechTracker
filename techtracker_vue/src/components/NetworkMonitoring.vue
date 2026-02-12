<template>
  <div class="network-monitoring p-4 page-shell">
    <Toast />
    <div class="flex flex-wrap justify-content-between align-items-start gap-3 mb-4">
      <div>
        <h2 class="text-2xl font-bold m-0 text-900">Сетевой мониторинг</h2>
        <p class="text-500 m-0">Пути, матрица доступности и инциденты</p>
      </div>
      <div class="flex align-items-center gap-2">
        <Button icon="pi pi-refresh" label="Обновить" text @click="refreshActiveTab" />
      </div>
    </div>

    <div class="tab-switch mb-3">
      <Button :outlined="activeTab !== 'paths'" label="Пути" @click="activeTab = 'paths'" />
      <Button :outlined="activeTab !== 'matrix'" label="Матрица" @click="activeTab = 'matrix'" />
      <Button :outlined="activeTab !== 'incidents'" label="Инциденты" @click="activeTab = 'incidents'" />
      <Button :outlined="activeTab !== 'derived_alerts'" label="Метрики и тревоги" @click="activeTab = 'derived_alerts'" />
    </div>

    <div v-if="activeTab === 'paths'">
      <div class="card p-3 mb-3">
        <div class="grid">
          <div class="col-12 md:col-4">
            <label class="block mb-2">Поиск</label>
            <InputText v-model="pathFilter.search" placeholder="Источник / назначение" class="w-full" />
          </div>
          <div class="col-12 md:col-3">
            <label class="block mb-2">Состояние</label>
            <Dropdown v-model="pathFilter.state" :options="stateOptions" optionLabel="label" optionValue="value" showClear class="w-full" />
          </div>
          <div class="col-12 md:col-3">
            <label class="block mb-2">Включен</label>
            <Dropdown v-model="pathFilter.enabled" :options="enabledOptions" optionLabel="label" optionValue="value" showClear class="w-full" />
          </div>
          <div class="col-12 md:col-2 flex align-items-end">
            <Button label="Создать путь" icon="pi pi-plus" class="w-full" @click="openCreatePath" />
          </div>
        </div>
      </div>

      <div class="card p-3 mb-3">
        <div class="flex flex-wrap gap-2 align-items-center">
          <span class="text-600">Массовые действия ({{ selectedPaths.length }})</span>
          <Button label="Вкл" size="small" @click="bulkEnable(true)" :disabled="!selectedPaths.length" />
          <Button label="Выкл" size="small" severity="secondary" @click="bulkEnable(false)" :disabled="!selectedPaths.length" />
          <InputNumber v-model="bulkInterval" :min="5" :max="3600" suffix=" c" class="bulk-input" />
          <Button label="Применить интервал" size="small" severity="secondary" @click="bulkSetInterval" :disabled="!selectedPaths.length" />
          <Button label="Проверить выбранные" size="small" severity="help" @click="probeSelected" :disabled="!selectedPaths.length" />
          <Button label="Проверить все" size="small" severity="help" outlined @click="probeAll" />
        </div>
      </div>

      <div class="card p-3 mb-3">
        <h4 class="m-0 mb-2">Мастер создания путей</h4>
        <div class="grid">
          <div class="col-12 md:col-3">
            <label class="block mb-2">Шаблон</label>
            <Dropdown v-model="templateForm.template" :options="templateOptions" optionLabel="label" optionValue="value" class="w-full" />
          </div>
          <div class="col-12 md:col-3">
            <label class="block mb-2">Интервал</label>
            <InputNumber v-model="templateForm.defaults.interval_sec" :min="5" :max="3600" suffix=" c" class="w-full" />
          </div>
          <div class="col-12 md:col-2">
            <label class="block mb-2">Timeout</label>
            <InputNumber v-model="templateForm.defaults.timeout_sec" :min="1" :max="120" suffix=" c" class="w-full" />
          </div>
          <div class="col-12 md:col-2">
            <label class="block mb-2">Fail/Recover</label>
            <div class="flex gap-2">
              <InputNumber v-model="templateForm.defaults.fail_threshold" :min="1" :max="20" class="w-full" />
              <InputNumber v-model="templateForm.defaults.recover_threshold" :min="1" :max="20" class="w-full" />
            </div>
          </div>
          <div class="col-12 md:col-2 flex align-items-end">
            <Button label="Сгенерировать" icon="pi pi-sparkles" class="w-full" @click="runTemplate" />
          </div>
          <div v-if="templateForm.template === 'custom'" class="col-12 md:col-6">
            <label class="block mb-2">Источники</label>
            <MultiSelect
              v-model="templateForm.src_device_ids"
              :options="deviceOptions"
              optionLabel="label"
              optionValue="value"
              class="w-full"
              filter
              display="chip"
            />
          </div>
          <div v-if="templateForm.template === 'custom'" class="col-12 md:col-6">
            <label class="block mb-2">Назначения (с IP)</label>
            <MultiSelect
              v-model="templateForm.dst_device_ids"
              :options="deviceOptionsWithIp"
              optionLabel="label"
              optionValue="value"
              class="w-full"
              filter
              display="chip"
            />
          </div>
        </div>
      </div>

      <DataTable
        :value="filteredPaths"
        v-model:selection="selectedPaths"
        dataKey="id"
        :loading="loadingPaths"
        paginator
        :rows="15"
        stripedRows
        responsiveLayout="scroll"
      >
        <Column selectionMode="multiple" headerStyle="width: 3rem"></Column>
        <Column field="src_device_name" header="Источник" sortable />
        <Column field="dst_device_name" header="Назначение" sortable />
        <Column field="dst_ip" header="IP назначения" />
        <Column field="last_state" header="Состояние" sortable>
          <template #body="{ data }">
            <Tag :value="stateLabel(data.last_state)" :severity="stateSeverity(data.last_state)" />
          </template>
        </Column>
        <Column header="Эффективность">
          <template #body="{ data }">
            <div class="eff-cell">
              <div>24ч: {{ formatPercent(data.uptime_24h_pct) }}</div>
              <div>7д: {{ formatPercent(data.uptime_7d_pct) }}</div>
            </div>
          </template>
        </Column>
        <Column header="Инциденты">
          <template #body="{ data }">
            <div class="eff-cell">
              <div>24ч: {{ data.outage_count_24h ?? 0 }}</div>
              <div>7д: {{ data.outage_count_7d ?? 0 }}</div>
            </div>
          </template>
        </Column>
        <Column field="last_latency_ms" header="RTT (ms)">
          <template #body="{ data }">{{ formatNum(data.last_latency_ms, 1) }}</template>
        </Column>
        <Column field="last_packet_loss_pct" header="Loss (%)">
          <template #body="{ data }">{{ formatNum(data.last_packet_loss_pct, 1) }}</template>
        </Column>
        <Column header="Последний outage (сек)">
          <template #body="{ data }">{{ data.last_outage_duration_sec ?? '—' }}</template>
        </Column>
        <Column header="Действия" style="width: 11rem">
          <template #body="{ data }">
            <div class="flex gap-1">
              <Button icon="pi pi-pencil" text rounded @click="openEditPath(data)" />
              <Button icon="pi pi-play" text rounded severity="help" @click="probePath(data.id)" />
              <Button icon="pi pi-trash" text rounded severity="danger" @click="removePath(data)" />
            </div>
          </template>
        </Column>
      </DataTable>
    </div>

    <div v-if="activeTab === 'matrix'" class="card p-3">
      <div class="flex justify-content-between align-items-center mb-2">
        <h4 class="m-0">PING-матрица</h4>
        <div class="flex align-items-center gap-2">
          <label class="text-600">Показывать выключенные пути</label>
          <InputSwitch v-model="matrixIncludeDisabled" @change="loadMatrix" />
        </div>
      </div>
      <div class="matrix-wrap">
        <table class="matrix-table">
          <thead>
            <tr>
              <th>Источник \ Назначение</th>
              <th v-for="dst in matrix.destinations" :key="dst.id">{{ dst.name }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in matrix.rows" :key="row.src_device_id">
              <td class="src-cell">{{ row.src_device_name }}</td>
              <td
                v-for="cell in row.cells"
                :key="`${row.src_device_id}-${cell.dst_device_id}`"
                :class="['matrix-cell', matrixCellClass(cell)]"
                @click="openCellHistory(cell)"
              >
                <div v-if="cell.path_id">
                  <div class="cell-main">{{ stateLabel(cell.state) }}</div>
                  <div class="cell-sub">{{ formatNum(cell.latency_ms, 1) }} ms</div>
                  <div class="cell-sub">{{ formatPercent(cell.uptime_24h_pct) }}</div>
                </div>
                <div v-else>—</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="activeTab === 'incidents'" class="card p-3">
      <div class="grid mb-2">
        <div class="col-12 md:col-3">
          <label class="block mb-2">Период</label>
          <Dropdown v-model="incidentFilter.period" :options="periodOptions" optionLabel="label" optionValue="value" class="w-full" @change="loadOutages" />
        </div>
        <div class="col-12 md:col-3">
          <label class="block mb-2">Статус</label>
          <Dropdown v-model="incidentFilter.active" :options="activeOptions" optionLabel="label" optionValue="value" class="w-full" @change="loadOutages" />
        </div>
      </div>
      <DataTable :value="outages" :loading="loadingOutages" paginator :rows="15" stripedRows responsiveLayout="scroll">
        <Column field="path_src" header="Источник" />
        <Column field="path_dst" header="Назначение" />
        <Column field="path_dst_ip" header="IP" />
        <Column field="started_at" header="Начало">
          <template #body="{ data }">{{ fmtTime(data.started_at) }}</template>
        </Column>
        <Column field="ended_at" header="Конец">
          <template #body="{ data }">{{ data.ended_at ? fmtTime(data.ended_at) : 'Активен' }}</template>
        </Column>
        <Column field="duration_sec" header="Длительность (сек)" />
        <Column field="fail_count" header="Ошибки" />
        <Column field="is_active" header="Статус">
          <template #body="{ data }">
            <Tag :value="data.is_active ? 'Активен' : 'Закрыт'" :severity="data.is_active ? 'danger' : 'success'" />
          </template>
        </Column>
      </DataTable>
    </div>

    <div v-if="activeTab === 'derived_alerts'">
      <div class="grid mb-3">
        <div class="col-12 md:col-2">
          <div class="metric-card border-round p-3">
            <div class="text-500">Critical</div>
            <div class="text-3xl font-bold text-red-600">{{ alertSummary.critical || 0 }}</div>
          </div>
        </div>
        <div class="col-12 md:col-2">
          <div class="metric-card border-round p-3">
            <div class="text-500">High</div>
            <div class="text-3xl font-bold text-orange-500">{{ alertSummary.high || 0 }}</div>
          </div>
        </div>
        <div class="col-12 md:col-2">
          <div class="metric-card border-round p-3">
            <div class="text-500">Medium</div>
            <div class="text-3xl font-bold text-yellow-600">{{ alertSummary.medium || 0 }}</div>
          </div>
        </div>
        <div class="col-12 md:col-2">
          <div class="metric-card border-round p-3">
            <div class="text-500">Low</div>
            <div class="text-3xl font-bold text-teal-600">{{ alertSummary.low || 0 }}</div>
          </div>
        </div>
        <div class="col-12 md:col-2">
          <div class="metric-card border-round p-3">
            <div class="text-500">Всего тревог</div>
            <div class="text-3xl font-bold text-900">{{ alertSummary.total || 0 }}</div>
          </div>
        </div>
      </div>

      <div class="card p-3 mb-3">
        <div class="flex flex-wrap align-items-center gap-2">
          <Button label="Пересчитать + проверить правила" icon="pi pi-cog" @click="evaluateAlerts(true)" :loading="loadingDerived" />
          <Button label="Проверить правила" severity="secondary" outlined @click="evaluateAlerts(false)" :loading="loadingDerived" />
          <Button label="Сбросить дефолтные правила" severity="help" outlined @click="seedDefaultRules" />
          <span class="text-500 ml-2">Обновлено: {{ fmtTime(alertSummary.generated_at) }}</span>
        </div>
      </div>

      <div class="card p-3 mb-3">
        <h4 class="m-0 mb-2">Правила тревог</h4>
        <DataTable :value="alertRules" :loading="loadingDerived" stripedRows responsiveLayout="scroll">
          <Column field="order" header="Порядок">
            <template #body="{ data }">
              <InputNumber v-model="data.order" :min="1" :max="10000" class="w-full" />
            </template>
          </Column>
          <Column field="code" header="Код" />
          <Column field="name" header="Название" />
          <Column field="metric_code" header="Метрика">
            <template #body="{ data }">
              <Dropdown v-model="data.metric_code" :options="metricCodeOptions" optionLabel="label" optionValue="value" class="w-full" />
            </template>
          </Column>
          <Column field="window" header="Окно">
            <template #body="{ data }">
              <Dropdown v-model="data.window" :options="windowOptions" optionLabel="label" optionValue="value" class="w-full" />
            </template>
          </Column>
          <Column field="comparison" header="Сравнение">
            <template #body="{ data }">
              <Dropdown v-model="data.comparison" :options="comparisonOptions" optionLabel="label" optionValue="value" class="w-full" />
            </template>
          </Column>
          <Column field="threshold_value" header="Порог">
            <template #body="{ data }">
              <InputNumber v-model="data.threshold_value" :minFractionDigits="0" :maxFractionDigits="2" class="w-full" />
            </template>
          </Column>
          <Column field="severity" header="Severity">
            <template #body="{ data }">
              <Dropdown v-model="data.severity" :options="severityOptions" optionLabel="label" optionValue="value" class="w-full" />
            </template>
          </Column>
          <Column field="enabled" header="Enabled">
            <template #body="{ data }">
              <InputSwitch v-model="data.enabled" />
            </template>
          </Column>
          <Column header="Сохранить">
            <template #body="{ data }">
              <Button icon="pi pi-save" text rounded @click="saveRule(data)" />
            </template>
          </Column>
        </DataTable>
      </div>

      <div class="card p-3 mb-3">
        <h4 class="m-0 mb-2">Derived метрики путей</h4>
        <DataTable :value="derivedRows" :loading="loadingDerived" stripedRows paginator :rows="15" responsiveLayout="scroll">
          <Column field="src_device_name" header="Источник" />
          <Column field="dst_device_name" header="Назначение" />
          <Column field="dst_ip" header="IP" />
          <Column field="net_path_uptime_24h" header="Uptime 24ч (%)"><template #body="{ data }">{{ formatNum(data.net_path_uptime_24h, 2) }}</template></Column>
          <Column field="net_path_uptime_7d" header="Uptime 7д (%)"><template #body="{ data }">{{ formatNum(data.net_path_uptime_7d, 2) }}</template></Column>
          <Column field="net_path_outage_count_24h" header="Outage 24ч" />
          <Column field="net_path_latency_p95_24h" header="Latency p95 (ms)"><template #body="{ data }">{{ formatNum(data.net_path_latency_p95_24h, 1) }}</template></Column>
          <Column field="net_path_latency_jitter_1h" header="Jitter 1ч (ms)"><template #body="{ data }">{{ formatNum(data.net_path_latency_jitter_1h, 1) }}</template></Column>
          <Column field="net_path_packet_loss_avg_24h" header="Loss avg 24ч (%)"><template #body="{ data }">{{ formatNum(data.net_path_packet_loss_avg_24h, 2) }}</template></Column>
        </DataTable>
      </div>

      <div class="card p-3">
        <div class="flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
          <h4 class="m-0">Активные тревоги</h4>
          <div class="flex gap-2">
            <Dropdown
              v-model="alertsFilter.severity"
              :options="alertsSeverityOptions"
              optionLabel="label"
              optionValue="value"
              class="alert-filter"
            />
            <InputText v-model="alertsFilter.search" placeholder="Поиск по пути/правилу" class="alert-filter" />
          </div>
        </div>
        <DataTable :value="filteredActiveAlerts" :loading="loadingDerived" stripedRows paginator :rows="15" responsiveLayout="scroll">
          <Column field="severity" header="Severity">
            <template #body="{ data }"><Tag :value="data.severity" :severity="severityTag(data.severity)" /></template>
          </Column>
          <Column field="rule_name" header="Правило" />
          <Column field="src_device_name" header="Источник" />
          <Column field="dst_device_name" header="Назначение" />
          <Column field="metric_code" header="Метрика" />
          <Column header="Текущее"><template #body="{ data }">{{ formatNum(data.metric_value, 2) }}</template></Column>
          <Column header="Порог"><template #body="{ data }">{{ data.comparison }} {{ formatNum(data.threshold_value, 2) }}</template></Column>
          <Column field="message" header="Описание" />
        </DataTable>
      </div>
    </div>

    <Dialog v-model:visible="pathDialogVisible" modal :header="editingPathId ? 'Редактировать путь' : 'Создать путь'" :style="{ width: '40rem' }">
      <div class="grid p-fluid">
        <div class="col-12 md:col-6">
          <label class="block mb-2">Источник</label>
          <Dropdown v-model="pathForm.src_device" :options="deviceOptions" optionLabel="label" optionValue="value" class="w-full" />
        </div>
        <div class="col-12 md:col-6">
          <label class="block mb-2">Назначение</label>
          <Dropdown v-model="pathForm.dst_device" :options="deviceOptionsWithIp" optionLabel="label" optionValue="value" class="w-full" />
        </div>
        <div class="col-12 md:col-3">
          <label class="block mb-2">Интервал</label>
          <InputNumber v-model="pathForm.interval_sec" :min="5" :max="3600" suffix=" c" class="w-full" />
        </div>
        <div class="col-12 md:col-3">
          <label class="block mb-2">Timeout</label>
          <InputNumber v-model="pathForm.timeout_sec" :min="1" :max="120" suffix=" c" class="w-full" />
        </div>
        <div class="col-12 md:col-3">
          <label class="block mb-2">Пакеты</label>
          <InputNumber v-model="pathForm.packet_count" :min="1" :max="10" class="w-full" />
        </div>
        <div class="col-12 md:col-3">
          <label class="block mb-2">Вкл</label>
          <InputSwitch v-model="pathForm.enabled" />
        </div>
        <div class="col-12 md:col-6">
          <label class="block mb-2">Порог fail</label>
          <InputNumber v-model="pathForm.fail_threshold" :min="1" :max="20" class="w-full" />
        </div>
        <div class="col-12 md:col-6">
          <label class="block mb-2">Порог recover</label>
          <InputNumber v-model="pathForm.recover_threshold" :min="1" :max="20" class="w-full" />
        </div>
      </div>
      <template #footer>
        <Button label="Отмена" severity="secondary" text @click="pathDialogVisible = false" />
        <Button label="Сохранить" icon="pi pi-check" @click="savePath" />
      </template>
    </Dialog>

    <Dialog v-model:visible="historyDialogVisible" modal header="История пути" :style="{ width: '56rem' }">
      <div v-if="historyPath">
        <div class="text-700 mb-3">{{ historyPath.src_device }} -> {{ historyPath.dst_device }}</div>
        <div class="grid">
          <div class="col-12">
            <Chart type="line" :data="historyCharts.reachability" :options="historyChartOptions" class="h-16rem" />
          </div>
          <div class="col-12 md:col-6">
            <Chart type="line" :data="historyCharts.latency" :options="historyChartOptions" class="h-16rem" />
          </div>
          <div class="col-12 md:col-6">
            <Chart type="line" :data="historyCharts.loss" :options="historyChartOptions" class="h-16rem" />
          </div>
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Dropdown from 'primevue/dropdown';
import MultiSelect from 'primevue/multiselect';
import InputText from 'primevue/inputtext';
import InputNumber from 'primevue/inputnumber';
import InputSwitch from 'primevue/inputswitch';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Tag from 'primevue/tag';
import Dialog from 'primevue/dialog';
import Toast from 'primevue/toast';
import Chart from 'primevue/chart';
import { useToast } from 'primevue/usetoast';

const toast = useToast();
const activeTab = ref('paths');
const autoTimer = ref(null);

const loadingPaths = ref(false);
const loadingOutages = ref(false);
const loadingDerived = ref(false);

const paths = ref([]);
const devices = ref([]);
const outages = ref([]);
const selectedPaths = ref([]);
const alertRules = ref([]);
const derivedRows = ref([]);
const activeAlerts = ref([]);
const alertSummary = ref({
  critical: 0,
  high: 0,
  medium: 0,
  low: 0,
  total: 0,
  generated_at: null,
});
const alertsFilter = ref({
  severity: '',
  search: '',
});

const pathDialogVisible = ref(false);
const editingPathId = ref(null);
const pathForm = ref({
  src_device: null,
  dst_device: null,
  enabled: true,
  interval_sec: 60,
  timeout_sec: 3,
  packet_count: 1,
  fail_threshold: 3,
  recover_threshold: 2,
});

const pathFilter = ref({
  search: '',
  state: null,
  enabled: null,
});

const bulkInterval = ref(60);

const templateForm = ref({
  template: 'servers_to_gateways',
  src_device_ids: [],
  dst_device_ids: [],
  defaults: {
    interval_sec: 60,
    timeout_sec: 3,
    packet_count: 1,
    fail_threshold: 3,
    recover_threshold: 2,
    enabled: true,
  },
});

const stateOptions = [
  { label: 'UP', value: 'up' },
  { label: 'DOWN', value: 'down' },
  { label: 'UNKNOWN', value: 'unknown' },
];
const enabledOptions = [
  { label: 'Включен', value: true },
  { label: 'Выключен', value: false },
];
const templateOptions = [
  { label: 'Серверы -> Шлюзы', value: 'servers_to_gateways' },
  { label: 'Серверы -> Маршрутизаторы', value: 'servers_to_routers' },
  { label: 'Маршрутизаторы -> Шлюзы', value: 'routers_to_gateways' },
  { label: 'Custom', value: 'custom' },
];

const matrixIncludeDisabled = ref(false);
const matrix = ref({ sources: [], destinations: [], rows: [] });
const historyDialogVisible = ref(false);
const historyPath = ref(null);
const historyCharts = ref({
  reachability: { labels: [], datasets: [] },
  latency: { labels: [], datasets: [] },
  loss: { labels: [], datasets: [] },
});
const historyChartOptions = {
  maintainAspectRatio: false,
  plugins: { legend: { display: true } },
};

const incidentFilter = ref({
  period: '24h',
  active: '',
});
const periodOptions = [
  { label: '24 часа', value: '24h' },
  { label: '7 дней', value: '7d' },
  { label: 'Все', value: 'all' },
];
const activeOptions = [
  { label: 'Все', value: '' },
  { label: 'Только активные', value: 'true' },
  { label: 'Только закрытые', value: 'false' },
];
const metricCodeOptions = [
  { label: 'Путь DOWN (current)', value: 'net_path_down_flag_current' },
  { label: 'Uptime 24ч', value: 'net_path_uptime_24h' },
  { label: 'Uptime 7д', value: 'net_path_uptime_7d' },
  { label: 'Outage count 24ч', value: 'net_path_outage_count_24h' },
  { label: 'Outage count 7д', value: 'net_path_outage_count_7d' },
  { label: 'Latency p95 24ч', value: 'net_path_latency_p95_24h' },
  { label: 'Latency jitter 1ч', value: 'net_path_latency_jitter_1h' },
  { label: 'Packet loss avg 24ч', value: 'net_path_packet_loss_avg_24h' },
];
const windowOptions = [
  { label: 'Current', value: 'current' },
  { label: '1h', value: '1h' },
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
];
const comparisonOptions = [
  { label: '>', value: 'gt' },
  { label: '>=', value: 'gte' },
  { label: '<', value: 'lt' },
  { label: '<=', value: 'lte' },
  { label: '=', value: 'eq' },
  { label: '!=', value: 'ne' },
];
const severityOptions = [
  { label: 'Low', value: 'low' },
  { label: 'Medium', value: 'medium' },
  { label: 'High', value: 'high' },
  { label: 'Critical', value: 'critical' },
];
const alertsSeverityOptions = [
  { label: 'Все severity', value: '' },
  ...severityOptions,
];

const unwrap = (res) => (Array.isArray(res.data) ? res.data : (res.data?.results || []));

const deviceOptions = computed(() => devices.value.map((d) => ({
  label: `${d.name} (${d.serial_number})`,
  value: d.id,
})));
const deviceOptionsWithIp = computed(() => devices.value
  .filter((d) => !!d.ip_address)
  .map((d) => ({ label: `${d.name} (${d.ip_address})`, value: d.id })));

const filteredPaths = computed(() => {
  return paths.value.filter((p) => {
    const stateOk = !pathFilter.value.state || p.last_state === pathFilter.value.state;
    const enabledOk = pathFilter.value.enabled === null || p.enabled === pathFilter.value.enabled;
    const search = (pathFilter.value.search || '').toLowerCase().trim();
    const searchOk = !search || `${p.src_device_name} ${p.dst_device_name} ${p.dst_ip || ''}`.toLowerCase().includes(search);
    return stateOk && enabledOk && searchOk;
  });
});
const filteredActiveAlerts = computed(() => {
  return activeAlerts.value.filter((item) => {
    const severityOk = !alertsFilter.value.severity || item.severity === alertsFilter.value.severity;
    const search = (alertsFilter.value.search || '').toLowerCase().trim();
    if (!search) return severityOk;
    const haystack = `${item.rule_name || ''} ${item.src_device_name || ''} ${item.dst_device_name || ''} ${item.message || ''}`.toLowerCase();
    return severityOk && haystack.includes(search);
  });
});

const stateLabel = (state) => {
  if (state === 'up') return 'UP';
  if (state === 'down') return 'DOWN';
  return 'UNKNOWN';
};
const stateSeverity = (state) => {
  if (state === 'up') return 'success';
  if (state === 'down') return 'danger';
  return 'warning';
};

const fmtTime = (value) => {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value));
  } catch (e) {
    return value;
  }
};
const formatNum = (value, digits = 1) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
};
const formatPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(1)}%`;
};

const validatePathForm = () => {
  if (!pathForm.value.src_device || !pathForm.value.dst_device) {
    return 'Нужно выбрать источник и назначение.';
  }
  if (pathForm.value.src_device === pathForm.value.dst_device) {
    return 'Источник и назначение не могут совпадать.';
  }
  const dst = devices.value.find((d) => d.id === pathForm.value.dst_device);
  if (!dst || !dst.ip_address) {
    return 'У назначения должен быть IP-адрес.';
  }
  if (pathForm.value.timeout_sec > pathForm.value.interval_sec) {
    return 'Timeout должен быть меньше или равен интервалу.';
  }
  return '';
};

const loadDevices = async () => {
  const res = await apiClient.get('devices/?ordering=name');
  devices.value = unwrap(res);
};

const loadPaths = async () => {
  loadingPaths.value = true;
  try {
    const res = await apiClient.get('network-paths/');
    paths.value = unwrap(res);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e?.response?.data?.detail || 'Не удалось загрузить пути', life: 4000 });
  } finally {
    loadingPaths.value = false;
  }
};

const loadMatrix = async () => {
  try {
    const res = await apiClient.get(`network-paths/matrix/?include_disabled=${matrixIncludeDisabled.value ? '1' : '0'}`);
    matrix.value = res.data || { sources: [], destinations: [], rows: [] };
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e?.response?.data?.detail || 'Не удалось загрузить матрицу', life: 4000 });
  }
};

const loadOutages = async () => {
  loadingOutages.value = true;
  try {
    const params = new URLSearchParams();
    params.set('ordering', '-started_at');
    if (incidentFilter.value.period === '24h') params.set('since_hours', '24');
    if (incidentFilter.value.period === '7d') params.set('since_days', '7');
    if (incidentFilter.value.active !== '') params.set('is_active', incidentFilter.value.active);
    const res = await apiClient.get(`network-outages/?${params.toString()}`);
    outages.value = unwrap(res);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: e?.response?.data?.detail || 'Не удалось загрузить инциденты', life: 4000 });
  } finally {
    loadingOutages.value = false;
  }
};

const loadAlertRules = async () => {
  try {
    const res = await apiClient.get('network-alert-rules/?ordering=order,code');
    alertRules.value = unwrap(res);
  } catch (e) {
    toast.add({
      severity: 'error',
      summary: 'Ошибка',
      detail: e?.response?.data?.detail || 'Не удалось загрузить правила тревог',
      life: 4000,
    });
  }
};

const loadDerivedSnapshot = async () => {
  try {
    const res = await apiClient.get('network-paths/derived/');
    derivedRows.value = Array.isArray(res.data) ? res.data : [];
  } catch (e) {
    toast.add({
      severity: 'error',
      summary: 'Ошибка',
      detail: e?.response?.data?.detail || 'Не удалось загрузить derived-метрики',
      life: 4000,
    });
  }
};

const severityTag = (severity) => {
  if (severity === 'critical') return 'danger';
  if (severity === 'high') return 'warning';
  if (severity === 'medium') return 'info';
  return 'success';
};

const evaluateAlerts = async (recompute = true) => {
  loadingDerived.value = true;
  try {
    const res = await apiClient.post('network-paths/evaluate_alerts/', {
      recompute,
      ensure_defaults: true,
    });
    const payload = res.data || {};
    alertSummary.value = payload.summary || {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      total: 0,
      generated_at: null,
    };
    activeAlerts.value = Array.isArray(payload.alerts) ? payload.alerts : [];
    if (Array.isArray(payload.rows) && payload.rows.length) {
      derivedRows.value = payload.rows;
    }
    toast.add({
      severity: 'success',
      summary: recompute ? 'Метрики пересчитаны' : 'Проверка завершена',
      detail: `Активных тревог: ${alertSummary.value.total || 0}`,
      life: 2800,
    });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось выполнить проверку тревог';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  } finally {
    loadingDerived.value = false;
  }
};

const seedDefaultRules = async () => {
  try {
    const res = await apiClient.post('network-alert-rules/seed_defaults/');
    await loadAlertRules();
    toast.add({
      severity: 'success',
      summary: 'Правила обновлены',
      detail: `created=${res.data?.created || 0}, updated=${res.data?.updated || 0}`,
      life: 3200,
    });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось сбросить дефолтные правила';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  }
};

const saveRule = async (rule) => {
  try {
    await apiClient.patch(`network-alert-rules/${rule.id}/`, {
      metric_code: rule.metric_code,
      window: rule.window,
      comparison: rule.comparison,
      threshold_value: rule.threshold_value,
      severity: rule.severity,
      enabled: rule.enabled,
      order: rule.order,
    });
    toast.add({ severity: 'success', summary: 'Сохранено', detail: `Правило: ${rule.code}`, life: 2200 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось сохранить правило';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 3800 });
  }
};

const loadDerivedTab = async () => {
  loadingDerived.value = true;
  try {
    await Promise.all([
      loadAlertRules(),
      loadDerivedSnapshot(),
    ]);
    const res = await apiClient.post('network-paths/evaluate_alerts/', {
      recompute: false,
      ensure_defaults: true,
    });
    const payload = res.data || {};
    alertSummary.value = payload.summary || alertSummary.value;
    activeAlerts.value = Array.isArray(payload.alerts) ? payload.alerts : [];
    if (Array.isArray(payload.rows) && payload.rows.length) {
      derivedRows.value = payload.rows;
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось загрузить тревоги';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4200 });
  } finally {
    loadingDerived.value = false;
  }
};

const refreshActiveTab = async () => {
  if (activeTab.value === 'paths') {
    await loadPaths();
  } else if (activeTab.value === 'matrix') {
    await loadMatrix();
  } else if (activeTab.value === 'derived_alerts') {
    await loadDerivedTab();
  } else {
    await loadOutages();
  }
};

const openCreatePath = () => {
  editingPathId.value = null;
  pathForm.value = {
    src_device: null,
    dst_device: null,
    enabled: true,
    interval_sec: 60,
    timeout_sec: 3,
    packet_count: 1,
    fail_threshold: 3,
    recover_threshold: 2,
  };
  pathDialogVisible.value = true;
};

const openEditPath = (path) => {
  editingPathId.value = path.id;
  pathForm.value = {
    src_device: path.src_device,
    dst_device: path.dst_device,
    enabled: path.enabled,
    interval_sec: path.interval_sec,
    timeout_sec: path.timeout_sec,
    packet_count: path.packet_count,
    fail_threshold: path.fail_threshold,
    recover_threshold: path.recover_threshold,
  };
  pathDialogVisible.value = true;
};

const savePath = async () => {
  const validationError = validatePathForm();
  if (validationError) {
    toast.add({ severity: 'warn', summary: 'Проверка данных', detail: validationError, life: 3500 });
    return;
  }

  try {
    if (editingPathId.value) {
      await apiClient.patch(`network-paths/${editingPathId.value}/`, pathForm.value);
    } else {
      await apiClient.post('network-paths/', pathForm.value);
    }
    pathDialogVisible.value = false;
    await loadPaths();
    await loadMatrix();
  } catch (e) {
    const detail = e?.response?.data?.detail || JSON.stringify(e?.response?.data || {}) || 'Не удалось сохранить путь';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  }
};

const removePath = async (path) => {
  if (!window.confirm(`Удалить путь ${path.src_device_name} -> ${path.dst_device_name}?`)) return;
  try {
    await apiClient.delete(`network-paths/${path.id}/`);
    await loadPaths();
    await loadMatrix();
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось удалить путь', life: 4000 });
  }
};

const selectedIds = computed(() => selectedPaths.value.map((p) => p.id));

const bulkEnable = async (enabled) => {
  try {
    const res = await apiClient.post('network-paths/bulk_update/', { ids: selectedIds.value, enabled });
    await loadPaths();
    await loadMatrix();
    toast.add({ severity: 'success', summary: 'OK', detail: `Обновлено: ${res.data.updated}`, life: 2500 });
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Массовое обновление не удалось', life: 4000 });
  }
};

const bulkSetInterval = async () => {
  if (!bulkInterval.value || bulkInterval.value < 5) {
    toast.add({ severity: 'warn', summary: 'Проверка данных', detail: 'Интервал должен быть >= 5 секунд', life: 3000 });
    return;
  }
  try {
    const res = await apiClient.post('network-paths/bulk_update/', { ids: selectedIds.value, interval_sec: bulkInterval.value });
    await loadPaths();
    toast.add({ severity: 'success', summary: 'OK', detail: `Обновлено: ${res.data.updated}`, life: 2500 });
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось применить интервал', life: 4000 });
  }
};

const probeAll = async () => {
  try {
    await apiClient.post('network-paths/probe/', { respect_interval: false, save_metrics: true });
    await Promise.all([loadPaths(), loadMatrix(), loadOutages()]);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Probe не выполнен', life: 4000 });
  }
};

const probeSelected = async () => {
  try {
    await apiClient.post('network-paths/probe/', { path_ids: selectedIds.value, respect_interval: false, save_metrics: true });
    await Promise.all([loadPaths(), loadMatrix(), loadOutages()]);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Probe выбранных не выполнен', life: 4000 });
  }
};

const probePath = async (pathId) => {
  try {
    await apiClient.post('network-paths/probe/', { path_id: pathId, respect_interval: false, save_metrics: true });
    await Promise.all([loadPaths(), loadMatrix(), loadOutages()]);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Probe пути не выполнен', life: 4000 });
  }
};

const runTemplate = async () => {
  if (templateForm.value.template === 'custom') {
    if (!templateForm.value.src_device_ids.length || !templateForm.value.dst_device_ids.length) {
      toast.add({ severity: 'warn', summary: 'Проверка данных', detail: 'Для custom нужно выбрать источники и назначения', life: 3000 });
      return;
    }
  }
  try {
    const res = await apiClient.post('network-paths/generate_template/', {
      template: templateForm.value.template,
      src_device_ids: templateForm.value.src_device_ids,
      dst_device_ids: templateForm.value.dst_device_ids,
      defaults: templateForm.value.defaults,
      update_existing: false,
    });
    await Promise.all([loadPaths(), loadMatrix()]);
    toast.add({
      severity: 'success',
      summary: 'Шаблон применен',
      detail: `created=${res.data.created}, updated=${res.data.updated}, skipped=${res.data.skipped}`,
      life: 3500,
    });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось применить шаблон';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  }
};

const matrixCellClass = (cell) => {
  if (!cell.path_id) return 'cell-none';
  if (cell.state === 'up') return 'cell-up';
  if (cell.state === 'down') return 'cell-down';
  return 'cell-unknown';
};

const formatLabel = (timestamp) => {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (v) => String(v).padStart(2, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())} ${pad(date.getDate())}:${pad(date.getMonth() + 1)}:${date.getFullYear()}`;
};

const openCellHistory = async (cell) => {
  if (!cell.path_id) return;
  try {
    const res = await apiClient.get(`network-paths/${cell.path_id}/history/?since_hours=168`);
    const data = res.data || {};
    historyPath.value = { src_device: data.src_device, dst_device: data.dst_device };
    const reachable = data.series?.reachable || [];
    const latency = data.series?.latency_ms || [];
    const loss = data.series?.packet_loss_pct || [];

    historyCharts.value.reachability = {
      labels: reachable.map((p) => formatLabel(p.timestamp)),
      datasets: [{ label: 'Reachable', data: reachable.map((p) => p.value), borderColor: '#2563eb', fill: false, tension: 0.2 }],
    };
    historyCharts.value.latency = {
      labels: latency.map((p) => formatLabel(p.timestamp)),
      datasets: [{ label: 'Latency ms', data: latency.map((p) => p.value), borderColor: '#10b981', fill: false, tension: 0.2 }],
    };
    historyCharts.value.loss = {
      labels: loss.map((p) => formatLabel(p.timestamp)),
      datasets: [{ label: 'Loss %', data: loss.map((p) => p.value), borderColor: '#ef4444', fill: false, tension: 0.2 }],
    };
    historyDialogVisible.value = true;
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить историю ячейки', life: 4000 });
  }
};

watch(activeTab, async (tab) => {
  if (tab === 'paths') await loadPaths();
  if (tab === 'matrix') await loadMatrix();
  if (tab === 'incidents') await loadOutages();
  if (tab === 'derived_alerts') await loadDerivedTab();
});

onMounted(async () => {
  await loadDevices();
  await loadPaths();
  autoTimer.value = setInterval(() => {
    if (activeTab.value === 'paths') loadPaths();
    if (activeTab.value === 'matrix') loadMatrix();
    if (activeTab.value === 'incidents') loadOutages();
    if (activeTab.value === 'derived_alerts') loadDerivedTab();
  }, 60000);
});

onBeforeUnmount(() => {
  if (autoTimer.value) clearInterval(autoTimer.value);
});
</script>

<style scoped>
.tab-switch {
  display: inline-flex;
  gap: 0.5rem;
  padding: 0.4rem;
  border-radius: 12px;
  background: #eef2ff;
}
.bulk-input {
  width: 9rem;
}
.metric-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}
.alert-filter {
  min-width: 14rem;
}
.eff-cell {
  font-size: 0.84rem;
  color: #475569;
  line-height: 1.3;
}
.matrix-wrap {
  overflow: auto;
}
.matrix-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 4px;
  min-width: 900px;
}
.matrix-table th,
.matrix-table td {
  padding: 0.45rem;
  text-align: center;
  border-radius: 8px;
}
.src-cell {
  text-align: left;
  background: #f8fafc;
  font-weight: 600;
}
.matrix-cell {
  cursor: pointer;
  transition: transform 0.15s ease;
}
.matrix-cell:hover {
  transform: translateY(-1px);
}
.cell-main {
  font-weight: 600;
  font-size: 0.82rem;
}
.cell-sub {
  font-size: 0.75rem;
  opacity: 0.9;
}
.cell-up {
  background: rgba(34, 197, 94, 0.18);
  color: #14532d;
}
.cell-down {
  background: rgba(239, 68, 68, 0.18);
  color: #7f1d1d;
}
.cell-unknown {
  background: rgba(245, 158, 11, 0.22);
  color: #78350f;
}
.cell-none {
  background: #e2e8f0;
  color: #475569;
}
</style>
