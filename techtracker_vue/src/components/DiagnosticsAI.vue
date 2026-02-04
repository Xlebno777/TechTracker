<template>
  <div class="dashboard p-4 page-shell">
    <Toast />
    <div class="flex flex-wrap justify-content-between align-items-start gap-3 mb-4">
      <div>
        <h2 class="text-2xl font-bold m-0 text-900">Диагностика (ИИ)</h2>
        <p class="text-500 m-0">Краткий диагноз по метрикам и правилам</p>
      </div>
      <div class="flex align-items-center gap-2">
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

      <div class="text-500 text-sm mb-3">
        Обновлено: {{ formatTime(report.created_at) }}
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
import { ref, onMounted } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';

const toast = useToast();
const running = ref(false);
const report = ref(null);

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
    const res = await apiClient.get('diagnostics/latest/');
    report.value = res.data;
  } catch (e) {
    report.value = null;
  }
};

const runAnalysis = async () => {
  running.value = true;
  try {
    await apiClient.post('diagnostics/run/', {});
    await loadLatest();
    toast.add({ severity: 'success', summary: 'Готово', detail: 'Анализ выполнен', life: 2500 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось выполнить анализ';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  } finally {
    running.value = false;
  }
};

onMounted(() => {
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
.severity-pill {
  padding: 0.35rem 0.75rem;
  border-radius: 999px;
  font-weight: 600;
  font-size: 0.85rem;
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
</style>
