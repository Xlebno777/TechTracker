<template>
  <div class="device-table p-4 page-shell">
    <div class="flex justify-content-between align-items-center mb-4">
      <h2 class="text-2xl font-bold m-0 text-900">Таблица устройств</h2>
      <Button
        v-if="canCreateDevice && !auth.isUser"
        label="Добавить устройство"
        icon="pi pi-plus"
        severity="success"
        @click="$router.push('/device/create')"
      />
    </div>

    <!-- Панель фильтров -->
    <div class="card p-4 mb-4 shadow-1 border-round bg-white">
      <div class="grid formgrid p-fluid">
        <div class="col-12 md:col-3 mb-3">
          <label class="font-semibold block mb-2">Тип</label>
          <Dropdown v-model="filters.device_type" :options="deviceTypes" optionLabel="name" optionValue="id" showClear placeholder="Все" />
        </div>
        <div class="col-12 md:col-3 mb-3">
          <label class="font-semibold block mb-2">Статус</label>
          <Dropdown v-model="filters.status" :options="statusOptions" optionLabel="label" optionValue="value" showClear placeholder="Все" />
        </div>
        <div class="col-12 md:col-3 mb-3">
          <label class="font-semibold block mb-2">Местоположение</label>
          <Dropdown v-model="filters.location" :options="locations" optionLabel="name" optionValue="id" showClear placeholder="Все" />
        </div>
        <div class="col-12 md:col-3 mb-3">
          <label class="font-semibold block mb-2">Владелец</label>
          <Dropdown v-model="filters.owner" :options="users" optionLabel="username" optionValue="id" showClear placeholder="Все" />
        </div>
        <div class="col-12 md:col-9 mb-3">
          <label class="font-semibold block mb-2">Поиск</label>
          <span class="p-input-icon-left w-full">
            <i class="pi pi-search" />
            <InputText v-model="filters.search" placeholder="Название или серийный номер..." class="w-full" />
          </span>
        </div>
        <div class="col-12 md:col-3 mb-3 flex align-items-end">
          <Button label="Сбросить" icon="pi pi-filter-slash" severity="secondary" outlined class="w-full" @click="resetFilters" />
        </div>
      </div>
    </div>

    <!-- Таблица -->
    <DataTable :value="filteredDevices" :loading="loading" paginator :rows="10" stripedRows responsiveLayout="scroll" class="tech-table shadow-2 border-round">
      <template #empty><div class="p-3 text-center">Устройства не найдены.</div></template>

      <!-- Избранное -->
      <Column header="" style="width: 3rem">
        <template #body="{ data }">
          <Button
            :icon="isDeviceFavorite(data) ? 'pi pi-star-fill' : 'pi pi-star'"
            :severity="isDeviceFavorite(data) ? 'warning' : 'secondary'"
            text
            rounded
            @click="toggleFavorite(data)"
          />
        </template>
      </Column>

      <Column field="name" header="Название" sortable />
      <Column field="serial_number" header="S/N" sortable />
      <Column field="asset_number" header="Инв. №" sortable />
      
      <!-- Тип (Объект) -->
      <Column header="Тип" field="device_type.name" sortable />
      
      <!-- Статус (Маппинг) -->
      <Column field="status" header="Статус" sortable>
        <template #body="{ data }">
          <Tag :value="getStatusLabel(data.status)" :severity="getStatusSeverity(data.status)" />
        </template>
      </Column>

      <!-- Местоположение (Объект) -->
      <Column header="Место" field="location.name" sortable />

      <!-- Владелец (Форматирование) -->
      <Column header="Владелец" sortable field="owner.username">
        <template #body="{ data }">
          {{ getOwnerName(data.owner) }}
        </template>
      </Column>

      <Column field="ip_address" header="IP" />

      <!-- Действия -->
      <Column v-if="!auth.isUser" header="Действия" style="width: 120px">
        <template #body="{ data }">
          <SplitButton
            label="Действия"
            icon="pi pi-cog"
            :model="getMenuItems(data)"
            severity="secondary"
            size="small"
            text
            raised
          />
        </template>
      </Column>
    </DataTable>

    <!-- Модальное окно деталей -->
    <Dialog v-model:visible="detailDialogVisible" :header="selectedDevice?.name" modal :style="{ width: '50vw' }" :breakpoints="{ '960px': '75vw', '640px': '90vw' }">
      <div v-if="selectedDevice" class="flex flex-column align-items-center">
        <img v-if="qrCodeUrl" :src="qrCodeUrl" alt="QR" class="mb-3 shadow-2 border-round" style="max-width: 150px" />
        
        <div class="grid w-full">
            <div class="col-6 font-bold">Серийный номер:</div>
            <div class="col-6">{{ selectedDevice.serial_number }}</div>
            
            <div class="col-6 font-bold">Владелец:</div>
            <div class="col-6">{{ getOwnerName(selectedDevice.owner) }}</div>

            <div class="col-6 font-bold">Назначен:</div>
            <div class="col-6">{{ getOwnerName(selectedDevice.assigned_to) }}</div>
            
            <div class="col-6 font-bold">Заметки:</div>
            <div class="col-6">{{ selectedDevice.notes || '-' }}</div>
        </div>
      </div>
    </Dialog>

    <ConfirmDialog />
    <Toast />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useRouter } from 'vue-router';
import apiClient from '@/api';
import { useAuthStore } from '@/stores/auth'; // Используем Store
import { useConfirm } from 'primevue/useconfirm';
import { useToast } from 'primevue/usetoast';

// Импорты UI
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Dropdown from 'primevue/dropdown';
import InputText from 'primevue/inputtext';
import Button from 'primevue/button';
import SplitButton from 'primevue/splitbutton';
import Dialog from 'primevue/dialog';
import Tag from 'primevue/tag';
import ConfirmDialog from 'primevue/confirmdialog';
import Toast from 'primevue/toast';

const router = useRouter();
const auth = useAuthStore();
const confirm = useConfirm();
const toast = useToast();

// Данные
const devices = ref([]);
const deviceTypes = ref([]);
const locations = ref([]);
const users = ref([]);
const loading = ref(true);

// Состояние UI
const detailDialogVisible = ref(false);
const selectedDevice = ref(null);
const qrCodeUrl = ref(null);

const filters = ref({
  device_type: null,
  status: null,
  location: null,
  owner: null,
  search: ''
});

// Константы статусов
const statusOptions = [
  { label: 'В работе', value: 'active' },
  { label: 'В ремонте', value: 'in_repair' },
  { label: 'Списано', value: 'retired' },
  { label: 'На складе', value: 'in_stock' },
  { label: 'В резерве', value: 'reserved' }
];

// --- Helpers ---

// Форматирование имени (принимает объект UserListSerializer)
const getOwnerName = (userObj) => {
  if (!userObj) return '—';
  // Теперь это объект, а не строка!
  const nameParts = [userObj.first_name, userObj.last_name].filter(Boolean).join(' ');
  return nameParts ? `${userObj.username} (${nameParts})` : userObj.username;
};

const getStatusLabel = (val) => statusOptions.find(o => o.value === val)?.label || val;

const getStatusSeverity = (val) => {
  switch (val) {
    case 'active': return 'success';
    case 'in_repair': return 'warning';
    case 'retired': return 'danger';
    default: return 'info';
  }
};

// Права доступа
const canCreateDevice = computed(() => auth.isAdmin || auth.isPowerUser);

const canEditDevice = (device) => {
  if (!auth.user) return false;
  const isOwner = device.owner?.id === auth.user.id;
  const isAssigned = device.assigned_to?.id === auth.user.id;
  return auth.isAdmin || auth.isPowerUser || isOwner || isAssigned;
};

const canDeleteDevice = () => auth.isAdmin;

// Фильтрация
const filteredDevices = computed(() => {
  return devices.value.filter(d => {
    const matchType = !filters.value.device_type || d.device_type?.id === filters.value.device_type;
    const matchStatus = !filters.value.status || d.status === filters.value.status;
    const matchLoc = !filters.value.location || d.location?.id === filters.value.location;
    const matchOwner = !filters.value.owner || d.owner?.id === filters.value.owner; // Сравниваем ID
    
    const searchLower = filters.value.search.toLowerCase();
    const matchSearch = !filters.value.search || 
      d.name.toLowerCase().includes(searchLower) || 
      d.serial_number.toLowerCase().includes(searchLower);

    return matchType && matchStatus && matchLoc && matchOwner && matchSearch;
  });
});

// --- Actions ---

// Избранное (работаем через Store)
const isDeviceFavorite = (device) => {
  return auth.user?.profile?.favorite_devices?.some(d => d.id === device.id);
};

const toggleFavorite = async (device) => {
  try {
    const res = await apiClient.post(`devices/${device.id}/toggle_favorite/`);
    const isFav = res.data.is_favorite;
    
    // Обновляем локально в Store, чтобы не перезагружать страницу
    // ВАЖНО: Мы мутируем состояние Pinia напрямую, это допустимо, но лучше через action
    const favs = auth.user.profile.favorite_devices;
    if (isFav) {
        // Добавляем (объект device уже содержит нужные поля благодаря LimitedDeviceSerializer)
        favs.push(device);
    } else {
        const idx = favs.findIndex(d => d.id === device.id);
        if (idx !== -1) favs.splice(idx, 1);
    }
    
    toast.add({ severity: 'success', summary: isFav ? 'Добавлено' : 'Удалено', detail: res.data.message, life: 2000 });
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось обновить избранное' });
  }
};

const getMenuItems = (device) => {
  const items = [
    {
      label: 'Подробнее',
      icon: 'pi pi-info-circle',
      command: () => showDetails(device)
    }
  ];

  if (canEditDevice(device)) {
    items.push({
      label: 'Редактировать',
      icon: 'pi pi-pencil',
      command: () => router.push(`/device/edit/${device.id}`)
    });
  }

  if (canDeleteDevice()) {
    items.push({
      label: 'Удалить',
      icon: 'pi pi-trash',
      command: () => confirmDelete(device)
    });
  }
  return items;
};

const showDetails = async (device) => {
  selectedDevice.value = device;
  detailDialogVisible.value = true;
  qrCodeUrl.value = null;
  try {
    const res = await apiClient.get(`devices/${device.id}/qr/`, { responseType: 'blob' });
    qrCodeUrl.value = URL.createObjectURL(res.data);
  } catch (e) {
    console.error(e);
  }
};

const confirmDelete = (device) => {
  confirm.require({
    message: `Удалить устройство "${device.name}"?`,
    header: 'Подтверждение',
    icon: 'pi pi-exclamation-triangle',
    acceptLabel: 'Да',
    rejectLabel: 'Нет',
    acceptClass: 'p-button-danger',
    accept: async () => {
      try {
        await apiClient.delete(`devices/${device.id}/`);
        devices.value = devices.value.filter(d => d.id !== device.id);
        toast.add({ severity: 'success', summary: 'Удалено', detail: 'Устройство удалено', life: 3000 });
      } catch (e) {
        toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось удалить' });
      }
    }
  });
};

const resetFilters = () => {
  filters.value = { device_type: null, status: null, location: null, owner: null, search: '' };
};

const fetchData = async () => {
  loading.value = true;
  try {
    const [devRes, typesRes, locRes, usersRes] = await Promise.all([
      apiClient.get('devices/'),
      apiClient.get('devicetypes/'),
      apiClient.get('locations/'),
      apiClient.get('users/')
    ]);
    devices.value = devRes.data;
    deviceTypes.value = typesRes.data;
    locations.value = locRes.data;
    users.value = usersRes.data;
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить данные' });
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  fetchData();
});

onBeforeUnmount(() => {
  if (qrCodeUrl.value) URL.revokeObjectURL(qrCodeUrl.value);
});
</script>

<style scoped>
/* Стили для сетки, если PrimeFlex не подключен глобально */
.grid { display: flex; flex-wrap: wrap; margin: -0.5rem; }
.col-12 { flex: 0 0 100%; padding: 0.5rem; }
@media (min-width: 768px) {
  .md\:col-3 { flex: 0 0 25%; max-width: 25%; }
  .md\:col-9 { flex: 0 0 75%; max-width: 75%; }
}
.w-full { width: 100%; }
.mb-2 { margin-bottom: 0.5rem; }
.mb-3 { margin-bottom: 1rem; }
.mb-4 { margin-bottom: 1.5rem; }
</style>
