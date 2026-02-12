<template>
  <div class="dashboard p-4 page-shell">
    <Toast />
    <div class="flex flex-wrap justify-content-between align-items-start gap-3 mb-4">
      <div>
        <h2 class="text-2xl font-bold m-0 text-900">Диагностика (ИИ)</h2>
        <p class="text-500 m-0">Краткий диагноз по метрикам и правилам</p>
        <div class="mt-3">
          <label class="block text-600 text-sm mb-1">Устройство</label>
          <Dropdown
            v-model="selectedMonitoringDeviceId"
            :options="monitoringDevices"
            optionLabel="label"
            optionValue="id"
            placeholder="Нет активных устройств (AgentStatus=ok)"
            class="device-select"
            :loading="loadingMonitoringDevices"
          />
        </div>
      </div>
      <div class="flex flex-wrap align-items-center gap-2">
        <div class="mode-toggle">
          <Button
            :outlined="mode !== 'llm'"
            :severity="mode === 'llm' ? 'primary' : 'secondary'"
            label="LLM"
            @click="mode = 'llm'"
          />
          <Button
            :outlined="mode !== 'rules'"
            :severity="mode === 'rules' ? 'primary' : 'secondary'"
            label="Rules"
            @click="mode = 'rules'"
          />
        </div>
        <Button icon="pi pi-refresh" label="Запустить анализ" rounded @click="runAnalysis" :loading="running" />
      </div>
    </div>

    <div v-if="report" class="card p-4 border-round shadow-1 mb-4">
      <div class="flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
        <div>
          <div class="text-700 text-sm">Диагноз</div>
          <div class="text-900 text-lg font-semibold">{{ report.summary }}</div>
        </div>
        <div class="severity-pill" :class="severityClass(report.severity)">
          {{ severityLabel(report.severity) }}
        </div>
      </div>

      <div class="text-500 text-sm mb-3 meta-row">
        <span>Обновлено: {{ formatTime(report.created_at) }}</span>
        <span v-if="modeLabel" class="mode-badge">{{ modeLabel }}</span>
      </div>

      <div v-if="fallbackReason" class="fallback-note">
        <i class="pi pi-info-circle"></i>
        <span>{{ fallbackReason }}</span>
      </div>

      <div class="section-title">Рекомендации</div>
      <ul class="recommendations">
        <li v-for="(rec, idx) in report.recommendations" :key="idx">{{ rec }}</li>
      </ul>
    </div>

    <div class="card p-4 border-round shadow-1">
      <div class="section-title mb-2">Найденные проблемы</div>
      <table class="metric-table">
        <thead>
          <tr>
            <th>Проблема</th>
            <th>Серьезность</th>
            <th>Доказательства</th>
            <th>Интерпретация</th>
            <th>Рекомендация</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="issue in report?.issues || []" :key="issue.id">
            <td class="text-900">{{ issue.title }}</td>
            <td :class="severityClass(issue.severity)">{{ severityLabel(issue.severity) }}</td>
            <td class="text-500">
              <div v-for="(ev, idx) in issue.evidence || []" :key="idx">{{ ev }}</div>
            </td>
            <td>{{ issue.explanation }}</td>
            <td>{{ issue.recommendation }}</td>
          </tr>
          <tr v-if="!report || (report.issues || []).length === 0">
            <td colspan="5" class="text-500">Проблем не обнаружено.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Dropdown from 'primevue/dropdown';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';
import { useMonitoringDevice } from '@/composables/useMonitoringDevice';

const toast = useToast();
const running = ref(false);
const report = ref(null);
const mode = ref('llm');
const modeLabel = ref('');
const fallbackReason = ref('');
const {
  monitoringDevices,
  selectedMonitoringDeviceId,
  selectedMonitoringSerial,
  loadingMonitoringDevices,
  loadMonitoringDevices,
} = useMonitoringDevice();

const severityLabel = (value) => {
  if (value === 'critical') return 'Критично';
  if (value === 'high') return 'Высокая';
  if (value === 'medium') return 'Средняя';
  return 'Низкая';
};

const severityClass = (value) => {
  if (value === 'critical') return 'severity-critical';
  if (value === 'high') return 'severity-high';
  if (value === 'medium') return 'severity-medium';
  return 'severity-low';
};

const formatTime = (value) => {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      dateStyle: 'short',
      timeStyle: 'short'
    }).format(new Date(value));
  } catch (e) {
    return value;
  }
};

const loadLatest = async () => {
  try {
    const params = new URLSearchParams();
    if (selectedMonitoringDeviceId.value) {
      params.set('device', String(selectedMonitoringDeviceId.value));
    }
    const query = params.toString();
    const res = await apiClient.get(`diagnostics/latest/${query ? `?${query}` : ''}`);
    report.value = res.data;
    updateModeInfo(res.data);
  } catch (e) {
    report.value = null;
    modeLabel.value = '';
    fallbackReason.value = '';
  }
};

const runAnalysis = async () => {
  running.value = true;
  try {
    const payload = { mode: mode.value };
    if (selectedMonitoringSerial.value) {
      payload.serial = selectedMonitoringSerial.value;
    }
    await apiClient.post('diagnostics/run/', payload);
    await loadLatest();
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Анализ выполнен', life: 2500 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось выполнить анализ';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  } finally {
    running.value = false;
  }
};

const updateModeInfo = (data) => {
  const payload = data?.payload || {};
  const llmUsed = payload?.llm_used;
  const llmMode = payload?.llm_mode;
  const provider = payload?.llm_provider;
  const model = payload?.llm_model;

  if (llmUsed) {
    modeLabel.value = `LLM (${provider || 'provider'}) ${model ? `• ${model}` : ''}`.trim();
    fallbackReason.value = '';
    return;
  }

  modeLabel.value = 'Rules';
  if (llmMode === 'rules') {
    fallbackReason.value = 'Выбран режим Rules — ИИ не использовался.';
    return;
  }
  if (payload?.llm_error) {
    fallbackReason.value = `Fallback на Rules: ${payload.llm_error}`;
    return;
  }
  if (provider && provider !== 'groq') {
    fallbackReason.value = `Fallback на Rules: LLM_PROVIDER=${provider}`;
    return;
  }
  fallbackReason.value = 'Fallback на Rules: LLM недоступен.';
};

onMounted(() => {
  loadMonitoringDevices().then(() => {
    loadLatest();
  });
});

watch(selectedMonitoringDeviceId, () => {
  loadLatest();
});
</script>

<style scoped>
.metric-table {
  width: 100%;
  border-collapse: collapse;
}
.metric-table th,
.metric-table td {
  text-align: left;
  padding: 0.75rem 0.5rem;
  border-bottom: 1px solid #eef1f5;
  font-size: 0.95rem;
}
.metric-table th {
  color: #6b7280;
  font-weight: 600;
}
.section-title {
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 0.5rem;
}
.recommendations {
  padding-left: 1.2rem;
  color: #334155;
}
.mode-toggle {
  display: inline-flex;
  gap: 0.35rem;
  padding: 0.25rem;
  border-radius: 999px;
  background: #f1f5f9;
}
.severity-pill {
  padding: 0.35rem 0.75rem;
  border-radius: 999px;
  font-weight: 600;
  font-size: 0.85rem;
}
.mode-badge {
  background: #e2e8f0;
  color: #334155;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
}
.meta-row {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
}
.fallback-note {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 10px;
  background: rgba(148, 163, 184, 0.15);
  color: #475569;
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}
.severity-low {
  color: #16a34a;
  background: rgba(22, 163, 74, 0.15);
}
.severity-medium {
  color: #d97706;
  background: rgba(217, 119, 6, 0.15);
}
.severity-high {
  color: #dc2626;
  background: rgba(220, 38, 38, 0.15);
}
.severity-critical {
  color: #7f1d1d;
  background: rgba(127, 29, 29, 0.2);
}
.device-select {
  min-width: 24rem;
}
@media (max-width: 768px) {
  .device-select {
    min-width: 100%;
  }
}
</style>
