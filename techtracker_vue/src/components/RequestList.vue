<template>
  <div class="p-4 request-list-container page-shell">
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
    <DataTable :value="filteredRequests" :loading="loading" paginator :rows="10" stripedRows responsiveLayout="scroll" class="tech-table shadow-2 border-round">
      <template #empty><div class="p-3 text-center">Заявок нет.</div></template>

      <Column field="device.name" header="Устройство" sortable />
      <Column field="message" header="Сообщение" style="min-width: 300px" sortable />

      <Column field="priority" header="Приоритет" sortable>
        <template #body="{ data }">
          <span :class="['priority-text', `priority-${data.priority || 'medium'}`]">
            {{ getPriorityLabel(data.priority) }}
          </span>
        </template>
      </Column>

      <Column field="created_by.username" header="Кто отправил" sortable>
        <template #body="{ data }">
          {{ data.created_by?.username || '—' }}
        </template>
      </Column>

      <Column header="Когда создана" field="timestamp" sortable>
        <template #body="{ data }">
          {{ new Date(data.timestamp).toLocaleDateString('ru-RU', {day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit'}) }}
        </template>
      </Column>

      <Column header="Выполнено" style="width: 140px">
        <template #body="{ data }">
          <Checkbox :binary="true" :modelValue="isCompleted(data)" @update:modelValue="(val) => toggleCompleted(data, val)" />
        </template>
      </Column>

      <Column header="Действия" style="width: 120px">
        <template #body="{ data }">
          <div class="action-stack">
            <Button icon="pi pi-pencil" text rounded severity="info" @click="openStatusDialog(data)" />
            <Button icon="pi pi-trash" text rounded severity="danger" @click="deleteRequest(data)" />
          </div>
        </template>
      </Column>
    </DataTable>

    <!-- Диалог смены статуса -->
    <Dialog
      v-model:visible="statusDialogVisible"
      header="Изменить статус"
      modal
      :style="{ width: 'min(460px, var(--dialog-width-lg))', maxWidth: 'var(--dialog-max-width)' }"
      :breakpoints="{ '640px': '96vw' }"
    >
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
import { useToast } from 'primevue/usetoast';
import { useConfirmAction } from '@/composables/useConfirmAction';

// UI Components
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Dropdown from 'primevue/dropdown';
import InputText from 'primevue/inputtext';
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import Checkbox from 'primevue/checkbox';
import Toast from 'primevue/toast';

const toast = useToast();
const { confirmAction } = useConfirmAction();

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

const isCompleted = (req) => req.status === 'closed';

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

const toggleCompleted = async (req, value) => {
  const newStatus = value ? 'closed' : 'open';
  try {
    await apiClient.patch(`logs/${req.id}/`, { status: newStatus });
    const idx = requests.value.findIndex(r => r.id === req.id);
    if (idx !== -1) requests.value[idx].status = newStatus;
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось обновить статус' });
  }
};

const deleteRequest = async (req) => {
  const ok = await confirmAction({
    header: 'Удаление заявки',
    message: 'Удалить выбранную заявку?',
    acceptLabel: 'Удалить',
    acceptSeverity: 'danger',
  });
  if (!ok) return;
  try {
    await apiClient.delete(`logs/${req.id}/`);
    requests.value = requests.value.filter(r => r.id !== req.id);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось удалить заявку' });
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
.request-list-container { width: 100%; }
.grid { display: flex; flex-wrap: wrap; margin: -0.5rem; }
.col-12 { flex: 0 0 100%; padding: 0.5rem; }
@media (min-width: 768px) {
  .md\:col-3 { flex: 0 0 25%; max-width: 25%; }
}
.priority-text {
  font-weight: 600;
}
.priority-low { color: #22c55e; }
.priority-medium { color: #0ea5e9; }
.priority-high { color: #f59e0b; }
.priority-critical { color: #ef4444; }
.action-stack {
  display: flex;
  gap: 0.25rem;
  justify-content: center;
}
</style>
