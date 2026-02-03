<template>
  <div class="dashboard p-4 page-shell">
    <Toast />
    <div class="flex flex-wrap justify-content-between align-items-start gap-3 mb-4">
      <div>
        <h2 class="text-2xl font-bold m-0 text-900">Диагностика агента</h2>
        <p class="text-500 m-0">Состояние служб отправки метрик</p>
      </div>
      <div class="flex flex-column align-items-end gap-2">
        <Button icon="pi pi-refresh" label="Обновить" rounded text @click="refreshData" :loading="loading" />
      </div>
    </div>

    <div class="card p-4 border-round shadow-1">
      <table class="metric-table">
        <thead>
          <tr>
            <th>Устройство</th>
            <th>Статус</th>
            <th>Сообщение</th>
            <th>Обновлено</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td>
              <div class="text-900">{{ row.device_name || row.device }}</div>
              <div class="text-500 text-xs">{{ row.device_serial || '' }}</div>
            </td>
            <td :class="row.status === 'error' ? 'text-red-500' : 'text-green-600'">
              {{ row.status === 'error' ? 'Ошибка' : 'OK' }}
            </td>
            <td>{{ row.message || '—' }}</td>
            <td>{{ formatTime(row.updated_at) }}</td>
          </tr>
          <tr v-if="rows.length === 0">
            <td colspan="4" class="text-500">Нет данных.</td>
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
const loading = ref(false);
const rows = ref([]);

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

const loadData = async () => {
  loading.value = true;
  try {
    const res = await apiClient.get('agent-status/?ordering=-updated_at');
    rows.value = Array.isArray(res.data) ? res.data : (res.data?.results || []);
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось загрузить диагностику';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  } finally {
    loading.value = false;
  }
};

const refreshData = () => {
  loadData();
};

onMounted(() => {
  loadData();
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
</style>
