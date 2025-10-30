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

      <Column field="name" header="Название" sortable />
      <Column field="serial_number" header="Серийный номер" sortable />
      <Column field="asset_number" header="Инв. номер" sortable />
      <Column header="Тип" field="device_type" sortable />
      <Column header="Статус" field="status" sortable />
      <Column header="Местоположение" field="location" sortable />
      <Column header="Владелец" field="owner" sortable />
      <Column field="ip_address" header="IP" />
      <Column field="mac_address" header="MAC" />

      <Column header="Действия" style="width: 180px;">
        <template #body="slotProps">
          <div class="p-d-flex p-ai-center p-gap-2">
            <Button
              v-if="canEditDevice(slotProps.data)"
              icon="pi pi-pencil"
              label="Ред."
              class="p-button-rounded p-button-text p-button-info"
              @click="$router.push(`/device/edit/${slotProps.data.id}`)"
            />
            <Button
              v-if="canDeleteDevice(slotProps.data)"
              icon="pi pi-trash"
              label="Удал."
              class="p-button-rounded p-button-text p-button-danger"
              @click="confirmDelete(slotProps.data)"
            />
          </div>
        </template>
      </Column>
    </DataTable>

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
    Message
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
      ]
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
          apiClient.get('api/devices/'),
          apiClient.get('api/devicetypes/'),
          apiClient.get('api/locations/'),
          apiClient.get('api/users/'),
          apiClient.get('api/users/me/')
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
            await apiClient.delete(`api/devices/${device.id}/`)
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
