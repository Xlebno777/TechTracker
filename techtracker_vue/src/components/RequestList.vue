<template>
  <div class="p-4 request-list-container">
    <div class="flex justify-content-between align-items-center mb-4">
      <h2 class="text-2xl font-bold m-0 text-900">Список заявок</h2>
      <Button icon="pi pi-refresh" rounded text @click="fetchData" :loading="loading" />
    </div>

    <!-- Фильтры -->
    <div class="card p-4 mb-4 shadow-1 border-round bg-white">
      <div class="grid formgrid p-fluid">
        <div class="col-12 md:col-3 mb-3">
          <label class="font-semibold block mb-2">Устройство</label>
          <Dropdown v-model="filters.device" :options="devices" optionLabel="name" optionValue="id" showClear placeholder="Все" />
        </div>
        <div class="col-12 md:col-3 mb-3">
          <label class="font-semibold block mb-2">Приоритет</label>
          <Dropdown v-model="filters.priority" :options="priorityOptions" optionLabel="label" optionValue="value" showClear placeholder="Все" />
        </div>
        <div class="col-12 md:col-3 mb-3">
          <label class="font-semibold block mb-2">Статус</label>
          <Dropdown v-model="filters.status" :options="statusOptions" optionLabel="label" optionValue="value" showClear placeholder="Все" />
        </div>
        <div class="col-12 md:col-3 mb-3">
          <label class="font-semibold block mb-2">Автор</label>
          <Dropdown v-model="filters.user" :options="users" optionLabel="username" optionValue="id" showClear placeholder="Все" />
        </div>
        <div class="col-12 mb-3">
          <span class="p-input-icon-left w-full">
            <i class="pi pi-search" />
            <InputText v-model="filters.message" placeholder="Поиск по тексту сообщения..." class="w-full" />
          </span>
        </div>
        <div class="col-12">
            <Button label="Сбросить фильтры" icon="pi pi-filter-slash" severity="secondary" outlined class="w-auto" @click="resetFilters" />
        </div>
      </div>
    </div>

    <!-- Таблица -->
    <DataTable :value="filteredRequests" :loading="loading" paginator :rows="10" stripedRows responsiveLayout="scroll" class="shadow-2 border-round">
      <template #empty><div class="p-3 text-center">Заявок нет.</div></template>

      <Column field="message" header="Сообщение" style="min-width: 300px" sortable />
      
      <Column field="device.name" header="Устройство" sortable />

      <!-- Приоритет -->
      <Column field="priority" header="Приоритет" sortable>
        <template #body="{ data }">
          <Tag :value="getPriorityLabel(data.priority)" :severity="getPrioritySeverity(data.priority)" />
        </template>
      </Column>

      <!-- Статус -->
      <Column field="status" header="Статус" sortable>
        <template #body="{ data }">
          <Tag :value="getStatusLabel(data.status)" :severity="getStatusSeverity(data.status)" />
        </template>
      </Column>

      <Column field="created_by.username" header="Автор" sortable>
        <template #body="{ data }">
           {{ data.created_by?.username || '—' }}
        </template>
      </Column>

      <Column header="Дата" field="timestamp" sortable>
        <template #body="{ data }">
          {{ new Date(data.timestamp).toLocaleDateString('ru-RU', {day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit'}) }}
        </template>
      </Column>

      <Column v-if="auth.isAdmin" header="Действия" style="width: 100px">
        <template #body="{ data }">
          <Button icon="pi pi-pencil" text rounded severity="info" @click="openStatusDialog(data)" />
        </template>
      </Column>
    </DataTable>

    <!-- Диалог смены статуса -->
    <Dialog v-model:visible="statusDialogVisible" header="Изменить статус" modal :style="{ width: '350px' }">
      <div class="field mt-3">
        <label class="font-semibold block mb-2">Новый статус</label>
        <Dropdown v-model="selectedRequestStatus" :options="statusOptions" optionLabel="label" optionValue="value" class="w-full" />
      </div>
      <template #footer>
        <Button label="Отмена" text icon="pi pi-times" @click="statusDialogVisible = false" />
        <Button label="Сохранить" icon="pi pi-check" @click="updateStatus" autofocus />
      </template>
    </Dialog>

    <Toast />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import apiClient from '@/api';
import { useAuthStore } from '@/stores/auth';
import { useToast } from 'primevue/usetoast';

// UI Components
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Dropdown from 'primevue/dropdown';
import InputText from 'primevue/inputtext';
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import Tag from 'primevue/tag';
import Toast from 'primevue/toast';

const auth = useAuthStore();
const toast = useToast();

const requests = ref([]);
const devices = ref([]);
const users = ref([]);
const loading = ref(true);

const statusDialogVisible = ref(false);
const selectedRequest = ref(null);
const selectedRequestStatus = ref(null);

const filters = ref({
  device: null,
  priority: null,
  status: null,
  user: null,
  message: ''
});

const priorityOptions = [
  { label: 'Низкий', value: 'low' },
  { label: 'Средний', value: 'medium' },
  { label: 'Высокий', value: 'high' },
  { label: 'Критический', value: 'critical' }
];

const statusOptions = [
  { label: 'Открыта', value: 'open' },
  { label: 'В работе', value: 'in_progress' },
  { label: 'Завершена', value: 'closed' },
  { label: 'Отменена', value: 'cancelled' }
];

// --- Helpers ---
const getPriorityLabel = (val) => {
    if (!val) return '—';
    return priorityOptions.find(o => o.value === val)?.label || val;
};

const getStatusLabel = (val) => {
    if (!val) return '—';
    return statusOptions.find(o => o.value === val)?.label || val;
};

const getPrioritySeverity = (val) => {
  if (!val) return 'secondary'; // Если нет приоритета - серый
  switch (val) {
    case 'critical': return 'danger';  // Красный
    case 'high': return 'warning';     // Оранжевый/Желтый
    case 'low': return 'success';      // Зеленый
    case 'medium': return 'info';      // Синий
    default: return 'info';            // Fallback
  }
};

const getStatusSeverity = (val) => {
  if (!val) return 'secondary';
  switch (val) {
    case 'closed': return 'success';
    case 'cancelled': return 'danger';
    case 'in_progress': return 'info';
    case 'open': return 'warning';
    default: return 'secondary';
  }
};

// --- Computed ---
const filteredRequests = computed(() => {
  return requests.value.filter(req => {
    const matchDevice = !filters.value.device || req.device?.id === filters.value.device;
    const matchPriority = !filters.value.priority || req.priority === filters.value.priority;
    const matchStatus = !filters.value.status || req.status === filters.value.status;
    const matchUser = !filters.value.user || req.created_by?.id === filters.value.user;
    const matchMessage = !filters.value.message || req.message.toLowerCase().includes(filters.value.message.toLowerCase());
    
    return matchDevice && matchPriority && matchStatus && matchUser && matchMessage;
  });
});

// --- Actions ---
const fetchData = async () => {
  loading.value = true;
  try {
    const [reqRes, devRes, userRes] = await Promise.all([
      apiClient.get('logs/?log_type=request'),
      apiClient.get('devices/'),
      apiClient.get('users/')
    ]);
    requests.value = reqRes.data;
    devices.value = devRes.data;
    users.value = userRes.data;
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить данные' });
  } finally {
    loading.value = false;
  }
};

const openStatusDialog = (req) => {
  selectedRequest.value = req;
  selectedRequestStatus.value = req.status;
  statusDialogVisible.value = true;
};

const updateStatus = async () => {
  if (!selectedRequest.value) return;
  try {
    await apiClient.patch(`logs/${selectedRequest.value.id}/`, { status: selectedRequestStatus.value });
    
    const idx = requests.value.findIndex(r => r.id === selectedRequest.value.id);
    if (idx !== -1) requests.value[idx].status = selectedRequestStatus.value;
    
    toast.add({ severity: 'success', summary: 'Успех', detail: 'Статус обновлен', life: 3000 });
    statusDialogVisible.value = false;
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Сбой обновления' });
  }
};

const resetFilters = () => {
    filters.value = { device: null, priority: null, status: null, user: null, message: '' };
};

onMounted(() => {
  fetchData();
});
</script>

<style scoped>
.w-full { width: 100%; }
.request-list-container { max-width: 1400px; margin: 0 auto; }
.grid { display: flex; flex-wrap: wrap; margin: -0.5rem; }
.col-12 { flex: 0 0 100%; padding: 0.5rem; }
@media (min-width: 768px) {
  .md\:col-3 { flex: 0 0 25%; max-width: 25%; }
}
</style>