<template>
  <div class="request-list p-p-4">
    <h2 class="list-title">Список заявок</h2>

    <!-- Панель фильтров -->
    <div class="filters-panel p-p-4 p-mb-4">
      <div class="filters-header">
        <i class="pi pi-sliders-h"></i>
        <h3>Фильтры</h3>
      </div>

      <div class="filters-row">
        <div class="filter-item">
          <label class="filter-label">Устройство</label>
          <Dropdown
            v-model="filters.device"
            :options="devices"
            optionLabel="name"
            optionValue="id"
            placeholder="Все устройства"
            showClear
          />
        </div>
        <div class="filter-item">
          <label class="filter-label">Приоритет</label>
          <Dropdown
            v-model="filters.priority"
            :options="priorityOptions"
            optionLabel="label"
            optionValue="value"
            placeholder="Все приоритеты"
            showClear
          />
        </div>
        <div class="filter-item">
          <label class="filter-label">Статус</label>
          <Dropdown
            v-model="filters.status"
            :options="statusOptions"
            optionLabel="label"
            optionValue="value"
            placeholder="Все статусы"
            showClear
          />
        </div>
        <div class="filter-item">
          <label class="filter-label">Пользователь</label>
          <Dropdown
            v-model="filters.user"
            :options="users"
            optionLabel="username"
            optionValue="id"
            placeholder="Все пользователи"
            showClear
          />
        </div>
        <div class="filter-item search-item">
          <label class="filter-label">Поиск в сообщении</label>
          <InputText
            v-model="filters.message"
            placeholder="Введите текст..."
          />
        </div>
        <div class="filter-item">
          <Button
            label="Сбросить"
            icon="pi pi-filter-slash"
            class="p-button-outlined p-button-secondary"
            @click="resetFilters"
          />
        </div>
      </div>
    </div>

    <!-- Таблица -->
    <DataTable
      :value="filteredRequests"
      paginator
      :rows="10"
      class="p-datatable-sm p-datatable-gridlines"
      stripedRows
      responsiveLayout="scroll"
    >
      <template #empty>Заявки не найдены.</template>
      <Column field="message" header="Сообщение" sortable></Column>
      <Column field="device.name" header="Устройство" sortable></Column>
      <Column field="priority" header="Приоритет" sortable>
        <template #body="slotProps">{{ getPriorityLabel(slotProps.data.priority) }}</template>
      </Column>
      <Column field="status" header="Статус" sortable>
        <template #body="slotProps">{{ getStatusLabel(slotProps.data.status) }}</template>
      </Column>
      <Column field="created_by.username" header="Кем создано" sortable></Column>
      <Column field="timestamp" header="Дата" sortable>
        <template #body="slotProps">{{ formatDate(slotProps.data.timestamp) }}</template>
      </Column>
      <Column v-if="isAdminUser" header="Действия">
        <template #body="slotProps">
          <Button
            label="Изменить статус"
            icon="pi pi-pencil"
            class="p-button-sm"
            @click="openStatusDialog(slotProps.data)"
          />
        </template>
      </Column>
    </DataTable>

    <!-- Диалог -->
    <Dialog
      v-model:visible="statusDialogVisible"
      header="Изменить статус"
      :modal="true"
      :closable="true"
      :style="{ width: '350px' }"
    >
      <div class="p-field">
        <label for="new_status" class="p-field-label">Новый статус</label>
        <Dropdown
          id="new_status"
          v-model="selectedRequestStatus"
          :options="statusOptions"
          optionLabel="label"
          optionValue="value"
        />
      </div>
      <template #footer>
        <Button
          label="Сохранить"
          icon="pi pi-check"
          class="p-button-success"
          @click="updateStatus"
        />
        <Button
          label="Отмена"
          icon="pi pi-times"
          class="p-button-secondary"
          @click="statusDialogVisible = false"
        />
      </template>
    </Dialog>
    <Toast />
  </div>
</template>

<script>
import apiClient from '@/api';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Dropdown from 'primevue/dropdown';
import InputText from 'primevue/inputtext';
import Dialog from 'primevue/dialog';
import Button from 'primevue/button';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';

export default {
  name: 'RequestList',
  components: { DataTable, Column, Dropdown, InputText, Dialog, Button, Toast },
  data() {
    return {
      requests: [],
      devices: [],
      users: [],
      filters: {
        device: null,
        priority: null,
        status: null,
        user: null,
        message: '',
      },
      priorityOptions: [
        { label: 'Низкий', value: 'low' },
        { label: 'Средний', value: 'medium' },
        { label: 'Высокий', value: 'high' },
        { label: 'Критический', value: 'critical' },
      ],
      statusOptions: [
        { label: 'Открыта', value: 'open' },
        { label: 'В работе', value: 'in_progress' },
        { label: 'Завершена', value: 'closed' },
        { label: 'Отменена', value: 'cancelled' },
      ],
      selectedRequest: null,
      selectedRequestStatus: null,
      statusDialogVisible: false,
    };
  },
  setup() {
    const toast = useToast();
    return { toast };
  },
  computed: {
    isAdminUser() {
      if (!this.currentUser || !this.currentUser.groups) {
        return false;
      }
      return this.currentUser.groups.some(group => group.name === 'Admins');
    },
    filteredRequests() {
      return this.requests.filter(req =>
        (!this.filters.device || req.device.id === this.filters.device) &&
        (!this.filters.priority || req.priority === this.filters.priority) &&
        (!this.filters.status || req.status === this.filters.status) &&
        (!this.filters.user || req.created_by?.id === this.filters.user) &&
        (!this.filters.message || req.message.toLowerCase().includes(this.filters.message.toLowerCase()))
      );
    },
  },
  methods: {
    async fetchData() {
      const [reqRes, devRes, userRes] = await Promise.all([
        apiClient.get('logs/?log_type=request'),
        apiClient.get('devices/'),
        apiClient.get('users/'),
      ]);
      this.requests = reqRes.data;
      this.devices = devRes.data;
      this.users = userRes.data;
    },
    getPriorityLabel(value) {
      return this.priorityOptions.find(option => option.value === value)?.label || value;
    },
    getStatusLabel(value) {
      return this.statusOptions.find(option => option.value === value)?.label || value;
    },
    formatDate(dateString) {
      return new Date(dateString).toLocaleString();
    },
    resetFilters() {
      this.filters = { device: null, priority: null, status: null, user: null, message: '' };
    },
    openStatusDialog(request) {
      this.selectedRequest = request;
      this.selectedRequestStatus = request.status;
      this.statusDialogVisible = true;
    },
    async updateStatus() {
      try {
        await apiClient.patch(`logs/${this.selectedRequest.id}/`, {
          status: this.selectedRequestStatus,
        });
        this.selectedRequest.status = this.selectedRequestStatus;
        this.toast.add({ severity: 'success', summary: 'Обновлено', detail: 'Статус заявки обновлён', life: 3000 });
        this.statusDialogVisible = false;
      } catch {
        this.toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось обновить статус', life: 3000 });
      }
    },
  },
  async mounted() {
    await this.fetchData();
  },
};
</script>

<style scoped>
.request-list {
  font-family: 'Inter', sans-serif;
}

.list-title {
  font-size: 1.6rem;
  font-weight: 600;
  color: #2c3e50;
  margin-bottom: 1rem;
  text-align: center;
}

.filters-panel {
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.85), rgba(240, 245, 255, 0.8));
  backdrop-filter: blur(8px);
  padding: 1.5rem;
  margin-bottom: 2rem;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
}

.filters-header {
  display: flex;
  justify-content: center;
  align-items: center;
  margin-bottom: 1rem;
  color: #1f2937;
}

.filters-header i {
  margin-right: 0.5rem;
  font-size: 1.4rem;
  color: #2563eb;
}

.filters-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 1.5rem;
}

.filter-item {
  min-width: 200px;
}

.filter-label {
  font-size: 0.9rem;
  font-weight: 600;
  margin-bottom: 0.4rem;
  color: #374151;
}

.p-inputtext,
.p-dropdown {
  width: 100%;
  border-radius: 0.5rem;
}

.search-item .p-inputtext {
  width: 220px;
}
</style>
