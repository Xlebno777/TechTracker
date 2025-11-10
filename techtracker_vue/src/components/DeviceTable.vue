<template>
  <div class="device-table p-p-4">
    <h2 class="p-mb-4" style="font-size: 1.6rem; font-weight: 600; color: #2c3e50;">
      Таблица устройств
    </h2>

    <!-- Кнопка добавить -->
    <div class="button-create p-d-flex p-jc-between p-ai-center p-mb-3">
      <Button
        v-if="canCreateDevice"
        label="Добавить устройство"
        icon="pi pi-plus"
        class="p-button-success"
        @click="$router.push('/device/create')"
      />
    </div>

    <!-- Панель фильтров -->
    <div class="filters-panel p-p-4 p-mb-4">
      <div class="filters-header">
        <i class="pi pi-sliders-h" style="font-size: 1.4rem; color: #2563eb; margin-right: 0.5rem;"></i>
        <h3>Фильтры устройств</h3>
      </div>
    
      <div class="filters-row">
        <div class="filter-item">
          <label class="filter-label"><i class="pi pi-desktop p-mr-2"></i>Тип устройства</label>
          <Dropdown
            v-model="filters.device_type"
            :options="deviceTypes"
            optionLabel="name"
            optionValue="id"
            placeholder="Все типы"
            showClear
          />
        </div>
      
        <div class="filter-item">
          <label class="filter-label"><i class="pi pi-cog p-mr-2"></i>Статус</label>
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
          <label class="filter-label"><i class="pi pi-map-marker p-mr-2"></i>Местоположение</label>
          <Dropdown
            v-model="filters.location"
            :options="locations"
            optionLabel="name"
            optionValue="id"
            placeholder="Все местоположения"
            showClear
          />
        </div>
      
        <div class="filter-item">
          <label class="filter-label"><i class="pi pi-user p-mr-2"></i>Владелец</label>
          <Dropdown
            v-model="filters.owner"
            :options="users"
            optionLabel="username"
            optionValue="id"
            placeholder="Все владельцы"
            showClear
          />
        </div>
      
        <div class="filter-item search-item">
          <label class="filter-label"><i class="pi pi-search p-mr-2"></i>Поиск</label>
          <InputText v-model="filters.search" placeholder="Название или сер. №" />
        </div>
      
        <div class="filter-item">
          <label class="filter-label">&nbsp;</label>
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
      :value="filteredDevices"
      :loading="loading"
      paginator
      :rows="10"
      stripedRows
      responsiveLayout="scroll"
      class="p-datatable-sm p-datatable-gridlines"
    >
      <template #empty>Устройства не найдены.</template>
      <template #loading>Загрузка устройств...</template>

      <Column header="Избранное" style="width: 80px;"> <!-- Укажем ширину -->
        <template #body="slotProps">
          <!-- Иконка звезды -->
          <Button
            :icon="isDeviceFavorite(slotProps.data) ? 'pi pi-star-fill' : 'pi pi-star'"
            :class="isDeviceFavorite(slotProps.data) ? 'p-button-warning p-button-text' : 'p-button-outlined p-button-secondary'"
            @click="toggleFavorite(slotProps.data)"
            aria-label="Переключить избранное"
            size="small"
            text
          />
        </template>
      </Column>
      <Column field="name" header="Название" sortable />
      <Column field="serial_number" header="Серийный номер" sortable />
      <Column field="asset_number" header="Инв. номер" sortable />
      <Column header="Тип" field="device_type" sortable />
      <Column header="Статус" field="status" sortable />
      <Column header="Местоположение" field="location" sortable />
      <Column header="Владелец" field="owner" sortable />
      <Column field="ip_address" header="IP" />
      <Column field="mac_address" header="MAC" />

      <Column header="Действия" style="width: 120px;">
        <template #body="slotProps">
          <SplitButton
            label="Действия"
            icon="pi pi-cog"
            :model="getMenuItems(slotProps.data)"
            severity="secondary"
            size="small"
            :disabled="!canPerformAnyAction(slotProps.data)"
          ></SplitButton>
        </template>
      </Column>
    </DataTable>

    <Dialog
      v-model:visible="detailDialogVisible"
      :header="`Информация об устройстве: ${selectedDevice?.name}`"
      :modal="true"
      :closable="true"
      :style="{ width: '50vw' }"
      :draggable="false"
      :resizable="false"
    >
      <div v-if="selectedDevice" class="p-text-center">
        <!-- Отображение QR-кода -->
        <img
          v-if="qrCodeUrl"
          :src="qrCodeUrl"
          alt="QR-код устройства"
          class="p-mb-3"
          style="max-width: 200px; max-height: 200px; display: block; margin: 0 auto;"
        />
        <div v-else class="p-mb-3">Загрузка QR-кода...</div>

        <!-- Подробная информация -->
        <div class="p-grid p-nogutter p-ai-center">
          <div class="p-col-6 p-text-left"><strong>Название:</strong></div>
          <div class="p-col-6 p-text-left">{{ selectedDevice.name }}</div>
        </div>
        <div class="p-grid p-nogutter p-ai-center">
          <div class="p-col-6 p-text-left"><strong>Серийный номер:</strong></div>
          <div class="p-col-6 p-text-left">{{ selectedDevice.serial_number }}</div>
        </div>
        <div class="p-grid p-nogutter p-ai-center">
          <div class="p-col-6 p-text-left"><strong>Инвентарный номер:</strong></div>
          <div class="p-col-6 p-text-left">{{ selectedDevice.asset_number || '—' }}</div>
        </div>
        <div class="p-grid p-nogutter p-ai-center">
          <div class="p-col-6 p-text-left"><strong>Тип:</strong></div>
          <div class="p-col-6 p-text-left">{{ selectedDevice.device_type?.name || '—' }}</div>
        </div>
        <div class="p-grid p-nogutter p-ai-center">
          <div class="p-col-6 p-text-left"><strong>Статус:</strong></div>
          <div class="p-col-6 p-text-left">{{ selectedDevice.status }}</div>
        </div>
        <div class="p-grid p-nogutter p-ai-center">
          <div class="p-col-6 p-text-left"><strong>Местоположение:</strong></div>
          <div class="p-col-6 p-text-left">{{ selectedDevice.location?.name || '—' }}</div>
        </div>
        <div class="p-grid p-nogutter p-ai-center">
          <div class="p-col-6 p-text-left"><strong>Владелец:</strong></div>
          <div class="p-col-6 p-text-left">{{ getOwnerName(selectedDevice.owner) }}</div>
        </div>
        <div class="p-grid p-nogutter p-ai-center">
          <div class="p-col-6 p-text-left"><strong>IP-адрес:</strong></div>
          <div class="p-col-6 p-text-left">{{ selectedDevice.ip_address || '—' }}</div>
        </div>
        <div class="p-grid p-nogutter p-ai-center">
          <div class="p-col-6 p-text-left"><strong>MAC-адрес:</strong></div>
          <div class="p-col-6 p-text-left">{{ selectedDevice.mac_address || '—' }}</div>
        </div>
        <div class="p-grid p-nogutter p-ai-center">
          <div class="p-col-6 p-text-left"><strong>Заметки:</strong></div>
          <div class="p-col-6 p-text-left">{{ selectedDevice.notes || '—' }}</div>
        </div>
        <!-- Можно добавить и специфичные данные, если нужно -->
      </div>
      <template #footer>
        <Button label="Закрыть" icon="pi pi-times" @click="detailDialogVisible = false" class="p-button-text" />
      </template>
    </Dialog>
    <ConfirmDialog />
    <Toast />

    <Message v-if="error" severity="error" class="p-mt-3" :text="error" />
  </div>
</template>

<script>
import apiClient from '@/api'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Dropdown from 'primevue/dropdown'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import ConfirmDialog from 'primevue/confirmdialog'
import Toast from 'primevue/toast'
import Message from 'primevue/message'
import Dialog from 'primevue/dialog'
import SplitButton from 'primevue/splitbutton'

export default {
  name: 'DeviceTable',
  components: {
    DataTable,
    Column,
    Dropdown,
    InputText,
    Button,
    ConfirmDialog,
    Toast,
    Message,
    Dialog,
    SplitButton
  },
  setup() {
    const confirm = useConfirm()
    const toast = useToast()
    return { confirm, toast }
  },
  data() {
    return {
      devices: [],
      deviceTypes: [],
      locations: [],
      users: [],
      currentUser: null,
      loading: true,
      error: null,
      filters: {
        device_type: '',
        status: '',
        location: '',
        owner: '',
        search: ''
      },
      statusOptions: [
        { label: 'В работе', value: 'active' },
        { label: 'В ремонте', value: 'in_repair' },
        { label: 'Списано', value: 'retired' },
        { label: 'На складе', value: 'in_stock' },
        { label: 'В резерве', value: 'reserved' }
      ],
      detailDialogVisible: false,
      selectedDevice: null,
      qrCodeUrl: null
    }
  },
  computed: {
    filteredDevices() {
      return this.devices.filter(d => {
        const matchesType = !this.filters.device_type || d.device_type.id === this.filters.device_type
        const matchesStatus = !this.filters.status || d.status === this.filters.status
        const matchesLocation = !this.filters.location || d.location.id === this.filters.location
        const matchesOwner = !this.filters.owner || d.owner === this.filters.owner
        const matchesSearch =
          !this.filters.search ||
          d.name.toLowerCase().includes(this.filters.search.toLowerCase()) ||
          d.serial_number.toLowerCase().includes(this.filters.search.toLowerCase())
        return matchesType && matchesStatus && matchesLocation && matchesOwner && matchesSearch
      })
    },
    canCreateDevice() {
      return this.hasGroup('Admins') || this.hasGroup('PowerUsers')
    }
  },
  methods: {
    canPerformAnyAction(device) {
      // Проверяем, есть ли у пользователя право на редактирование, удаление или просмотр деталей
      // Можно добавить другие проверки, если нужно
      return this.canEditDevice(device) || this.canDeleteDevice(device) || true; // Всегда можно посмотреть детали
    },
    getMenuItems(device) {
      const items = [];

      // Кнопка "Подробнее" (всегда доступна)
      items.push({
        label: 'Подробнее',
        icon: 'pi pi-info-circle',
        command: () => {
          this.showDetails(device);
        }
      });

      // Кнопка "Редактировать" (только если разрешено)
      if (this.canEditDevice(device)) {
        items.push({
          label: 'Редактировать',
          icon: 'pi pi-pencil',
          command: () => {
            this.$router.push(`/device/edit/${device.id}`);
          }
        });
      }

      // Кнопка "Удалить" (только если разрешено)
      if (this.canDeleteDevice(device)) {
        items.push({
          label: 'Удалить',
          icon: 'pi pi-trash',
          command: () => {
            this.confirmDelete(device);
          }
        });
      }

      // "В избранное" больше нет в этом меню
      return items;
    },
    // --- НОВЫЙ МЕТОД: Переключение избранного ---
    async toggleFavorite(device) {
      if (!this.currentUser || !this.currentUser.profile) {
        console.error("currentUser или его profile не загружен");
        this.toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Данные пользователя не загружены', life: 3000 });
        return;
      }
    
      try {
        const response = await apiClient.post(`devices/${device.id}/toggle_favorite/`);
        const { message, is_favorite: isFavorite } = response.data;
      
        // Обновляем локальное состояние currentUser.profile.favorite_devices
        // Проверяем, что profile и favorite_devices - это объекты/массивы
        if (this.currentUser.profile) {
          if (!this.currentUser.profile.favorite_devices) {
            // Если favorite_devices не определен, инициализируем как пустой массив
            this.currentUser.profile.favorite_devices = [];
          }
        
          if (!Array.isArray(this.currentUser.profile.favorite_devices)) {
            // Если favorite_devices не массив (например, объект или число), логируем ошибку и инициализируем заново
            console.error("favorite_devices не является массивом, перезаписываем как пустой массив.");
            this.currentUser.profile.favorite_devices = [];
          }
        
          if (isFavorite) {
            // Добавляем в избранное
            // Проверяем, нет ли уже в списке (по ID)
            if (!this.currentUser.profile.favorite_devices.some(d => d.id === device.id)) {
              // Добавляем копию объекта устройства (или только ID, если это все, что есть)
              // Лучше добавить весь объект устройства, чтобы он был доступен в isDeviceFavorite
              this.currentUser.profile.favorite_devices.push(device);
            }
          } else {
            // Удаляем из избранного
            this.currentUser.profile.favorite_devices = this.currentUser.profile.favorite_devices.filter(d => d.id !== device.id);
          }
        }
      
        this.toast.add({ severity: 'success', summary: 'Избранное', detail: message, life: 3000 });
      } catch (e) {
        console.error("Ошибка переключения избранного:", e);
        this.toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось изменить статус избранного', life: 3000 });
      }
    },
    isDeviceFavorite(device) {
      if (!this.currentUser || !this.currentUser.profile || !this.currentUser.profile.favorite_devices) {
        return false; // Если профиль или список избранных не загружен, считаем, что не в избранном
      }
    
      // Проверяем, что favorite_devices - это массив
      if (!Array.isArray(this.currentUser.profile.favorite_devices)) {
        console.warn("favorite_devices не является массивом в isDeviceFavorite.");
        return false;
      }
    
      // Проверяем, есть ли ID устройства в списке избранных
      return this.currentUser.profile.favorite_devices.some(favDevice => favDevice.id === device.id);
    },
    async showDetails(device) {
      this.selectedDevice = device;
      this.qrCodeUrl = null; // Сбрасываем URL QR-кода
      this.detailDialogVisible = true;

      try {
        // Генерируем URL для QR-кода (он будет запрошен браузером)
        // Используем axios.get с responseType 'blob' для получения изображения как бинарных данных
        const response = await apiClient.get(`devices/${device.id}/qr/`, {
          responseType: 'blob' // Важно!
        });

        // Создаём URL из бинарных данных
        const blob = response.data;
        this.qrCodeUrl = URL.createObjectURL(blob);
      } catch (e) {
        console.error("Ошибка загрузки QR-кода:", e);
        this.qrCodeUrl = null; // Оставляем null или показываем сообщение об ошибке
        // this.toast.add({ severity: 'error', summary: 'QR-код', detail: 'Не удалось загрузить QR-код', life: 3000 });
      }
    },
    hasGroup(group) {
      return this.currentUser?.groups?.some(g => g.name === group)
    },
    getOwnerName(ownerObjectOrId) {
      // Если передан null/undefined, возвращаем '—'
      if (!ownerObjectOrId) return '—';

      // Проверяем, является ли ownerObjectOrId объектом (новое поведение)
      if (typeof ownerObjectOrId === 'object' && ownerObjectOrId !== null) {
        const user = ownerObjectOrId; // Это сам объект пользователя
        const fullName = `${user.first_name || ''} ${user.last_name || ''}`.trim();
        return fullName ? `${user.username} (${fullName})` : user.username;
      }
    
      // Если это всё ещё ID (старое поведение, на всякий случай), ищем в this.users
      // (Это не должно сработать, если DeviceSerializer обновлён)
      const user = this.users.find(u => u.id === ownerObjectOrId);
      if (user) {
        const fullName = `${user.first_name || ''} ${user.last_name || ''}`.trim();
        return fullName ? `${user.username} (${fullName})` : user.username;
      }
      return '—';
    },
    async fetchAll() {
      try {
        const [devices, types, locations, users, me] = await Promise.all([
          apiClient.get('devices/'),
          apiClient.get('devicetypes/'),
          apiClient.get('locations/'),
          apiClient.get('users/'),
          apiClient.get('users/me/')
        ])
        this.devices = devices.data
        this.deviceTypes = types.data
        this.locations = locations.data
        this.users = users.data
        this.currentUser = me.data
      } catch (e) {
        console.error(e)
        this.error = 'Ошибка загрузки данных'
      } finally {
        this.loading = false
      }
    },
    resetFilters() {
      this.filters = { device_type: '', status: '', location: '', owner: '', search: '' }
    },
    canEditDevice(device) {
      if (!this.currentUser) return false;
      // Редактировать могут: Admin, PowerUsers, владелец, назначенный
      const isOwner = device.owner && device.owner.id === this.currentUser.id; // <-- Обрати внимание на .id
      const isAssigned = device.assigned_to && device.assigned_to.id === this.currentUser.id; // <-- Обрати внимание на .id

      return this.hasGroup('Admins') || this.hasGroup('PowerUsers') || isOwner || isAssigned;
    },

    // Метод canDeleteDevice не изменился, так как не зависит от owner/assigned_to
    canDeleteDevice() {
      if (!this.currentUser) return false;
      // Удалять могут только Admin
      return this.hasGroup('Admins');
    },
    confirmDelete(device) {
      this.confirm.require({
        message: `Удалить устройство "${device.name}"?`,
        header: 'Подтверждение удаления',
        icon: 'pi pi-exclamation-triangle',
        acceptLabel: 'Удалить',
        rejectLabel: 'Отмена',
        acceptClass: 'p-button-danger',
        accept: async () => {
          try {
            await apiClient.delete(`devices/${device.id}/`)
            this.devices = this.devices.filter(d => d.id !== device.id)
            this.toast.add({ severity: 'success', summary: 'Удалено', detail: 'Устройство удалено', life: 3000 })
          } catch (e) {
            this.toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось удалить', life: 3000 })
          }
        }
      })
    }
  },
  mounted() {
    this.fetchAll()
  },
  beforeUnmount() {
    if (this.qrCodeUrl) {
      URL.revokeObjectURL(this.qrCodeUrl);
    }
  }
}
</script>

<style scoped>
.device-table {
  font-family: 'Inter', 'Segoe UI', Roboto, sans-serif;
  color: #1f2937;
  background-color: #f9fafb;
  border-radius: 12px;
}

.button-create{
  margin-bottom: 1.5rem;
}

.filters-panel {
  position: relative;
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.85), rgba(240, 245, 255, 0.8));
  backdrop-filter: blur(8px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.5);
  transition: all 0.3s ease;
}

.filters-panel:hover {
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.1);
}

/* Заголовок панели */
.filters-header {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1.5rem;
}

.filters-header h3 {
  font-size: 1.2rem;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
  text-align: center;
}

/* Контейнер с фильтрами */
.filters-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: flex-end;
  gap: 1.5rem;
  text-align: center;
}

/* Каждый фильтр */
.filter-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 170px;
  margin-bottom: 2em;
}

/* Подписи над полями */
.filter-label {
  font-weight: 600;
  color: #374151;
  margin-bottom: 0.5rem;
  font-size: 0.95rem;
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

/* Поля ввода и dropdown */
.filter-item .p-inputtext,
.filter-item .p-dropdown {
  width: 190px;
  font-size: 0.95rem;
  border-radius: 10px;
}

/* Поисковое поле чуть шире */
.search-item .p-inputtext {
  width: 230px;
}

/* Кнопка сброса */
.filter-item .p-button {
  border-radius: 10px;
  font-size: 0.9rem;
  padding: 0.5rem 1rem;
}

/* Таблица */
.p-datatable {
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
  margin-top: 2em;
}

/* Заголовки */
.p-datatable-thead > tr > th {
  background: #f3f4f6;
  font-weight: 600;
  color: #374151;
}

/* Ряд таблицы */
.p-datatable-tbody > tr:hover {
  background: #f9fafb;
}

/* Кнопки */
.p-button {
  font-family: inherit;
  border-radius: 8px;
}
</style>
