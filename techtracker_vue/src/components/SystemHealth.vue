<template>
  <div class="system-health-page p-4">
    <Toast />

    <PageHeader
      title="Состояние системы"
      subtitle="Контроль нагрузки backend, базы данных, очередей прогнозирования и внешнего LSTM-сервиса."
      :refreshable="true"
      :loading="loadingDetails"
      :system-status-indicator="false"
      help-title="Гайд: состояние системы"
      help-intro="Эта страница нужна для быстрой диагностики: тормозит ли сама система, растёт ли очередь LSTM и хватает ли ресурсов серверу."
      :help-steps="helpSteps"
      help-note="Показатели являются оперативными. Для глубокого профилирования процесса используйте серверные логи и инструменты ОС."
      @refresh="loadDetails"
    />

    <section class="health-hero" :class="`health-hero--${status}`">
      <div>
        <span class="eyebrow">Общий статус</span>
        <h3>{{ statusLabel }}</h3>
        <p>{{ statusDescription }}</p>
      </div>
      <div class="hero-meta">
        <span>Host: {{ payload?.resources?.host || '—' }}</span>
        <span>Обновлено: {{ formatDateTime(payload?.generated_at) }}</span>
      </div>
    </section>

    <section v-if="warnings.length" class="warning-panel">
      <div class="warning-panel__head">
        <i class="pi pi-exclamation-triangle" />
        <strong>Предупреждения</strong>
      </div>
      <div class="warning-list">
        <div v-for="item in warnings" :key="`${item.code}-${item.message}`" class="warning-row" :class="`warning-row--${item.severity}`">
          <Tag :value="severityLabel(item.severity)" :severity="tagSeverity(item.severity)" />
          <span>{{ item.message }}</span>
        </div>
      </div>
    </section>

    <section class="metrics-grid">
      <div class="health-card">
        <span class="card-label">CPU сервера</span>
        <strong>{{ formatPercent(system.cpu_percent) }}</strong>
        <ProgressBar :value="safePercent(system.cpu_percent)" :showValue="false" />
      </div>
      <div class="health-card">
        <span class="card-label">RAM сервера</span>
        <strong>{{ formatPercent(system.memory_percent) }}</strong>
        <small>{{ formatMb(system.memory_used_mb) }} / {{ formatMb(system.memory_total_mb) }}</small>
        <ProgressBar :value="safePercent(system.memory_percent)" :showValue="false" />
      </div>
      <div class="health-card">
        <span class="card-label">Диск приложения</span>
        <strong>{{ formatPercent(system.disk_percent) }}</strong>
        <small>Свободно: {{ formatMb(system.disk_free_mb) }}</small>
        <ProgressBar :value="safePercent(system.disk_percent)" :showValue="false" />
      </div>
      <div class="health-card">
        <span class="card-label">Backend process</span>
        <strong>{{ formatMb(process.rss_mb) }}</strong>
        <small>PID {{ process.pid || '—' }} • потоков {{ process.threads || '—' }}</small>
      </div>
      <div class="health-card">
        <span class="card-label">База данных</span>
        <strong>{{ formatMb(database.size_mb) }}</strong>
        <small>{{ database.vendor || 'unknown' }}</small>
      </div>
      <div class="health-card">
        <span class="card-label">Удалённый LSTM</span>
        <strong>{{ lstmStatusLabel }}</strong>
        <small>{{ lstmDetailsText }}</small>
      </div>
    </section>

    <section class="content-grid mt-3">
      <div class="card p-3">
        <div class="section-head">
          <h4>Очереди и фоновые задачи</h4>
          <span class="text-500 text-sm">Оперативный контроль зависаний</span>
        </div>
        <div class="queue-grid">
          <div class="queue-item">
            <span>Активных LSTM-задач</span>
            <strong>{{ queues.lstm_active ?? 0 }}</strong>
          </div>
          <div class="queue-item">
            <span>LSTM failed за 24ч</span>
            <strong>{{ queues.lstm_failed_24h ?? 0 }}</strong>
          </div>
          <div class="queue-item">
            <span>Forecast в процессе</span>
            <strong>{{ queues.forecast_runs_active ?? 0 }}</strong>
          </div>
          <div class="queue-item">
            <span>Долгие forecast-запуски</span>
            <strong>{{ queues.forecast_runs_long ?? 0 }}</strong>
          </div>
          <div class="queue-item">
            <span>Обновления в работе</span>
            <strong>{{ queues.application_updates_active ?? 0 }}</strong>
          </div>
          <div class="queue-item">
            <span>Старейшая LSTM-задача</span>
            <strong>{{ queues.lstm_oldest_active?.age_minutes ?? '—' }} мин</strong>
          </div>
        </div>
      </div>

      <div class="card p-3">
        <div class="section-head">
          <h4>Объём данных</h4>
          <span class="text-500 text-sm">Оценки таблиц, без тяжелого COUNT для PostgreSQL</span>
        </div>
        <DataTable :value="countRows" size="small" responsiveLayout="scroll">
          <Column field="label" header="Раздел" />
          <Column field="value" header="Строк" style="width: 140px">
            <template #body="{ data }">{{ formatNumber(data.value) }}</template>
          </Column>
          <Column field="estimated" header="Тип" style="width: 130px">
            <template #body="{ data }">{{ data.estimated ? 'оценка' : 'точно' }}</template>
          </Column>
        </DataTable>
      </div>
    </section>

    <section class="card p-3 mt-3">
      <div class="section-head">
        <h4>Последние ошибки</h4>
        <span class="text-500 text-sm">forecast, LSTM очередь и агенты</span>
      </div>
      <div v-if="!failureRows.length" class="empty-inline">
        <i class="pi pi-check-circle" />
        <span>Свежих ошибок в отслеживаемых подсистемах не найдено.</span>
      </div>
      <DataTable v-else :value="failureRows" size="small" responsiveLayout="scroll">
        <Column field="kind" header="Источник" style="width: 160px" />
        <Column field="device" header="Устройство" style="width: 240px" />
        <Column field="updated_at" header="Время" style="width: 190px">
          <template #body="{ data }">{{ formatDateTime(data.updated_at) }}</template>
        </Column>
        <Column field="message" header="Сообщение" />
      </DataTable>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue';
import { useToast } from 'primevue/usetoast';
import Toast from 'primevue/toast';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Tag from 'primevue/tag';
import ProgressBar from 'primevue/progressbar';
import PageHeader from '@/components/ui/PageHeader.vue';
import { useSystemHealth } from '@/composables/useSystemHealth';

const toast = useToast();
const { details, loadingDetails, status, statusLabel, loadSystemDetails } = useSystemHealth();

const helpSteps = [
  'Сначала смотрите общий статус: если он жёлтый или красный, ниже будет список причин.',
  'CPU/RAM/диск показывают состояние сервера, на котором работает backend TechTracker.',
  'Очереди показывают, не копятся ли LSTM-задачи и нет ли зависших прогнозных запусков.',
  'Блок LSTM проверяет доступность удалённого нейросетевого сервиса через backend.',
  'Объём данных помогает понять, почему тяжелые графики или оценка прогноза могут работать медленнее.',
];

const payload = computed(() => details.value || {});
const system = computed(() => payload.value.resources?.system || {});
const process = computed(() => payload.value.resources?.process || {});
const database = computed(() => payload.value.database || {});
const queues = computed(() => payload.value.queues || {});
const lstm = computed(() => payload.value.lstm || {});
const warnings = computed(() => (Array.isArray(payload.value.warnings) ? payload.value.warnings : []));

const statusDescription = computed(() => {
  if (status.value === 'critical') return 'Есть критичные признаки: проверьте предупреждения и очередь задач.';
  if (status.value === 'warning') return 'Есть предупреждения, которые могут влиять на скорость или корректность расчетов.';
  if (status.value === 'ok') return 'Основные подсистемы работают без найденных предупреждений.';
  return 'Данные о состоянии пока не загружены.';
});

const lstmStatusLabel = computed(() => {
  if (!lstm.value.configured) return 'Не настроен';
  if (lstm.value.status === 'ok') return 'Доступен';
  if (lstm.value.status === 'error') return 'Ошибка';
  return 'Не проверен';
});

const lstmDetailsText = computed(() => {
  if (!lstm.value.configured) return 'Настройте на вкладке «Интеграции»';
  if (lstm.value.status === 'ok') return `${lstm.value.base_url || ''} • ${lstm.value.latency_ms || 0} мс`;
  if (lstm.value.error) return String(lstm.value.error).slice(0, 90);
  return lstm.value.base_url || '—';
});

const countLabels = {
  devices: 'Устройства',
  raw_metrics: 'Raw-метрики',
  computed_metrics: 'Агрегированные метрики',
  forecast_runs: 'Запуски прогноза',
  forecast_points: 'Точки прогноза',
  state_estimates: 'Оценки состояния',
  lstm_queue_jobs: 'LSTM очередь',
  decision_runs: 'Запуски СППР',
  application_updates: 'Обновления приложения',
};

const countRows = computed(() => {
  const counts = payload.value.counts || {};
  const estimated = payload.value.estimated || {};
  return Object.entries(countLabels).map(([key, label]) => ({
    key,
    label,
    value: Number(counts[key] || 0),
    estimated: Boolean(estimated[key]),
  }));
});

const failureRows = computed(() => {
  const failures = payload.value.latest_failures || {};
  const rows = [];
  for (const item of failures.forecast_runs || []) {
    rows.push({
      kind: `Forecast ${item.model_kind || ''}`.trim(),
      device: item.device__serial_number || item.device__name || '—',
      updated_at: item.updated_at,
      message: item.notes || `run #${item.id}`,
    });
  }
  for (const item of failures.lstm_queue || []) {
    rows.push({
      kind: 'LSTM очередь',
      device: item.device__serial_number || item.device__name || '—',
      updated_at: item.updated_at,
      message: item.last_error || item.remote_job_id || `job #${item.id}`,
    });
  }
  for (const item of failures.agents || []) {
    rows.push({
      kind: 'Агент',
      device: item.device__serial_number || item.device__name || '—',
      updated_at: item.updated_at,
      message: item.message || `status #${item.id}`,
    });
  }
  return rows;
});

function safePercent(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return 0;
  return Math.max(0, Math.min(100, num));
}

function formatPercent(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '—';
  return `${num.toFixed(1)}%`;
}

function formatMb(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '—';
  if (num >= 1024) return `${(num / 1024).toFixed(2)} GB`;
  return `${num.toFixed(0)} MB`;
}

function formatNumber(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '0';
  return new Intl.NumberFormat('ru-RU').format(num);
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

function severityLabel(value) {
  if (value === 'critical') return 'критично';
  if (value === 'warning') return 'внимание';
  return 'инфо';
}

function tagSeverity(value) {
  if (value === 'critical') return 'danger';
  if (value === 'warning') return 'warning';
  return 'info';
}

async function loadDetails() {
  try {
    await loadSystemDetails({ includeLstm: true });
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить состояние системы', life: 3500 });
  }
}

onMounted(loadDetails);
</script>

<style scoped>
.system-health-page {
  color: #1e293b;
}

.health-hero,
.warning-panel,
.health-card,
.card {
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid #dbe6f1;
  border-radius: 16px;
}

.health-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  padding: 1.1rem;
  margin-bottom: 1rem;
  border-left: 6px solid #94a3b8;
}

.health-hero--ok { border-left-color: #22c55e; }
.health-hero--warning { border-left-color: #f59e0b; }
.health-hero--critical { border-left-color: #ef4444; }

.eyebrow,
.card-label {
  color: #64748b;
  font-size: 0.82rem;
  font-weight: 700;
}

.health-hero h3 {
  margin: 0.25rem 0;
  font-size: 1.65rem;
}

.health-hero p,
.hero-meta span,
.health-card small {
  margin: 0;
  color: #64748b;
}

.hero-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.25rem;
  text-align: right;
  font-size: 0.9rem;
}

.warning-panel {
  padding: 1rem;
  margin-bottom: 1rem;
  background: #fffbeb;
}

.warning-panel__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  color: #92400e;
}

.warning-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.warning-row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  color: #334155;
}

.metrics-grid,
.content-grid,
.queue-grid {
  display: grid;
  gap: 0.8rem;
}

.metrics-grid {
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
}

.content-grid {
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
}

.health-card,
.queue-item {
  padding: 0.9rem;
}

.health-card {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.health-card strong {
  font-size: 1.35rem;
  color: #0f172a;
}

.queue-grid {
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
}

.queue-item {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #f8fafc;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.queue-item span {
  color: #64748b;
  font-size: 0.82rem;
}

.queue-item strong {
  font-size: 1.2rem;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.85rem;
}

.section-head h4 {
  margin: 0;
}

.empty-inline {
  min-height: 5rem;
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  color: #64748b;
}

@media (max-width: 980px) {
  .health-hero,
  .section-head {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-meta {
    align-items: flex-start;
    text-align: left;
  }

  .content-grid {
    grid-template-columns: 1fr;
  }
}
</style>
