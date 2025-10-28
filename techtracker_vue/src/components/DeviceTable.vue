<template>
  <div class="device-table">
    <h2>Таблица Устройств</h2>

    <!-- Кнопка для перехода к форме создания -->
    <router-link v-if="canCreateDevice" to="device/create" class="btn btn-primary mb-3">Добавить устройство</router-link>

    <!-- Фильтры -->
    <div class="card mb-3">
      <div class="card-body">
        <h5 class="card-title">Фильтры</h5>
        <div class="row">
          <div class="col-md-2">
            <label for="filter_type">Тип устройства:</label>
            <select id="filter_type" v-model="filters.device_type" class="form-control">
              <option value="">Все типы</option>
              <option v-for="type in deviceTypes" :key="type.id" :value="type.id">
                {{ type.name }}
              </option>
            </select>
          </div>
          <div class="col-md-2">
            <label for="filter_status">Статус:</label>
            <select id="filter_status" v-model="filters.status" class="form-control">
              <option value="">Все статусы</option>
              <option value="active">В работе</option>
              <option value="in_repair">В ремонте</option>
              <option value="retired">Списано</option>
              <option value="in_stock">На складе</option>
              <option value="reserved">В резерве</option>
            </select>
          </div>
          <div class="col-md-2">
            <label for="filter_location">Местоположение:</label>
            <select id="filter_location" v-model="filters.location" class="form-control">
              <option value="">Все местоположения</option>
              <option v-for="loc in locations" :key="loc.id" :value="loc.id">
                {{ loc.name }}
              </option>
            </select>
          </div>
          <!-- Новый фильтр по владельцу -->
          <div class="col-md-2">
            <label for="filter_owner">Владелец:</label>
            <select id="filter_owner" v-model="filters.owner" class="form-control">
              <option value="">Все владельцы</option>
              <option v-for="user in users" :key="user.id" :value="user.id">
                {{ user.username }} ({{ user.first_name }} {{ user.last_name }})
              </option>
            </select>
          </div>
          <div class="col-md-2">
            <label for="filter_search">Поиск (название, серийный):</label>
            <input type="text" id="filter_search" v-model="filters.search" class="form-control" placeholder="Введите..." />
          </div>
          <div class="col-md-2 d-flex align-items-end">
            <!-- Кнопка сброса фильтров -->
            <button @click="resetFilters" class="btn btn-outline-secondary w-100">Сбросить</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Состояние загрузки -->
    <div v-if="loading" class="alert alert-info">
      Загрузка...
    </div>

    <!-- Сообщение об ошибке -->
    <div v-if="error" class="alert alert-danger">
      Ошибка: {{ error }}
    </div>

    <!-- Таблица устройств -->
    <div v-if="!loading && !error" class="table-responsive">
      <table class="table table-striped table-hover">
        <thead class="thead-dark">
          <tr>
            <th>Название</th>
            <th>Серийный номер</th>
            <th>Инвентарный номер</th>
            <th>Тип</th>
            <th>Статус</th>
            <th>Местоположение</th>
            <th>Владелец</th>
            <th>IP-адрес</th>
            <th>MAC-адрес</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="device in filteredDevices" :key="device.id">
            <td>{{ device.name }}</td>
            <td>{{ device.serial_number }}</td>
            <td>{{ device.asset_number || '—' }}</td>
            <td>{{ device.device_type.name }}</td>
            <td>{{ device.status }}</td>
            <td>{{ device.location.name || '—' }}</td>
            <td>{{ getOwnerName(device.owner) }}</td>
            <td>{{ device.ip_address || '—' }}</td>
            <td>{{ device.mac_address || '—' }}</td>
            <td>
              <!-- Кнопка Редактировать - видна только если пользователь может редактировать -->
              <router-link
                v-if="canEditDevice(device)"
                :to="`/device/edit/${device.id}`"
                class="btn btn-primary btn-sm mr-2"
              >
                Редактировать
              </router-link>
              <!-- Кнопка Удалить - видна только если пользователь может удалить -->
              <button
                v-if="canDeleteDevice(device)"
                @click="deleteDevice(device.id)"
                class="btn btn-danger btn-sm"
              >
                Удалить
              </button>
              <!-- Если пользователь не может редактировать/удалять, кнопки не отображаются -->
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Сообщение, если фильтры не дали результатов -->
      <div v-if="filteredDevices.length === 0 && !loading" class="alert alert-info">
        Устройства не найдены по заданным фильтрам.
      </div>
    </div>
  </div>
</template>

<script>
import apiClient from '@/api'; // Используем наш настроенный apiClient

export default {
  name: 'DeviceTable',
  data() {
    return {
      devices: [],
      deviceTypes: [],
      locations: [],
      users: [], // Новый массив для пользователей
      currentUser: null, // Информация о текущем пользователе
      loading: true,
      error: null,
      filters: {
        device_type: '',
        status: '',
        location: '',
        owner: '', // Новый фильтр по владельцу
        search: '',
      }
    };
  },
  computed: {
    filteredDevices() {
      return this.devices.filter(device => {
        if (this.filters.device_type && device.device_type.id !== this.filters.device_type) {
          return false;
        }
        if (this.filters.status && device.status !== this.filters.status) {
          return false;
        }
        if (this.filters.location && device.location.id !== this.filters.location) {
          return false;
        }
        // Новый фильтр по владельцу
        if (this.filters.owner && device.owner !== parseInt(this.filters.owner)) {
          return false;
        }
        if (this.filters.search && !device.name.toLowerCase().includes(this.filters.search.toLowerCase()) && !device.serial_number.toLowerCase().includes(this.filters.search.toLowerCase())) {
          return false;
        }
        return true;
      });
    },
    // Проверяем, может ли текущий пользователь создать устройство (админ или PowerUser)
    canCreateDevice() {
      // Проверяем, что groups - это массив и ищем 'PowerUsers'
      if (!this.currentUser) return false;
      // Создавать могут: Admin или PowerUsers
      return this.hasGroup('Admins') || this.hasGroup('PowerUsers');
    }
  },
  methods: {
    hasGroup(groupName) {
      if (!this.currentUser || !Array.isArray(this.currentUser.groups)) {
        return false;
      }
      return this.currentUser.groups.some(g => g.name === groupName);
    },

    getOwnerName(ownerId) {
      if (!ownerId) return '—'; // Если ownerId null/undefined/0
      const user = this.users.find(u => u.id === ownerId);
      if (user) {
        // Возвращаем формат "username (first_name last_name)" или просто "username", если first_name/last_name пусты
        const fullName = `${user.first_name} ${user.last_name}`.trim();
        return fullName ? `${user.username} (${fullName})` : user.username;
      }
      return 'Unknown User'; // Если пользователь с таким ID не найден в списке users
    },
    async fetchDevices() {
      this.loading = true;
      this.error = null;
      try {
        const response = await apiClient.get('api/devices/');
        this.devices = response.data;
      } catch (err) {
        console.error("Ошибка при загрузке устройств:", err);
        this.error = 'Не удалось загрузить список устройств.';
      } finally {
        this.loading = false;
      }
    },
    async fetchDeviceTypesAndLocations() {
      try {
        const [typesResponse, locationsResponse] = await Promise.all([
          apiClient.get('api/devicetypes/'),
          apiClient.get('api/locations/')
        ]);
        this.deviceTypes = typesResponse.data;
        this.locations = locationsResponse.data;
      } catch (err) {
        console.error("Ошибка при загрузке справочников:", err);
        this.error = 'Не удалось загрузить справочники.';
      }
    },
    // Новый метод для загрузки пользователей
    async fetchUsers() {
      try {
        const response = await apiClient.get('api/users/');
        this.users = response.data;
      } catch (err) {
        console.error("Ошибка при загрузке пользователей:", err);
        // Не критично для основного функционала, можно не устанавливать error
        this.users = []; // Устанавливаем пустой массив, если не удалось загрузить
      }
    },
    async fetchCurrentUser() {
      try {
        const response = await apiClient.get('api/users/me/');
        this.currentUser = response.data;
        console.log("CurrentUser from API:", this.currentUser); // Для отладки
      } catch (err) {
        console.error("Ошибка при загрузке данных пользователя:", err);
        this.currentUser = null;
      }
    },
    // Метод для проверки прав на редактирование
    canEditDevice(device) {
      if (!this.currentUser) return false;
      // Права на редактирование: админ или владелец
      const isOwner = device.owner && device.owner.id === this.currentUser.id;
      // Также можно добавить проверку на назначенного пользователя (assigned_to), если нужно
      const isAssigned = device.assigned_to && device.assigned_to.id === this.currentUser.id;
      // Предположим, что PowerUsers могут редактировать любые устройства
      // Проверка на PowerUser
      let isPowerUser = false;

      if (Array.isArray(this.currentUser.groups)) {
        isPowerUser = this.currentUser.groups.some(g => g.name === 'PowerUsers');
      }

      let isAdmin = false;

      if (Array.isArray(this.currentUser.groups)) {
        isPowerUser = this.currentUser.groups.some(g => g.name === 'Admins');
      }

      return isOwner || isAssigned || isPowerUser || isAdmin;
    },
    // Метод для проверки прав на удаление
    canDeleteDevice() {
      if (!this.currentUser) return false;
      // Права на удаление: только админ
      return this.currentUser.is_staff;
    },
    // Метод для сброса фильтров
    resetFilters() {
      this.filters = {
        device_type: '',
        status: '',
        location: '',
        owner: '', // Сбрасываем фильтр по владельцу
        search: '',
      };
    },
    async deleteDevice(id) {
      const result = confirm(`Вы уверены, что хотите удалить устройство с ID ${id}?`);
      if (result) {
        try {
          await apiClient.delete(`api/devices/${id}/`);
          this.devices = this.devices.filter(device => device.id !== id);
          alert('Устройство успешно удалено.');
        } catch (err) {
          console.error("Ошибка при удалении устройства:", err);
          if (err.response && err.response.status === 403) {
            alert('У вас недостаточно прав для удаления этого устройства.');
          } else {
            alert('Не удалось удалить устройство. Проверьте консоль.');
          }
        }
      }
    }
  },
  async mounted() {
    // Загружаем все зависимости
    await this.fetchCurrentUser();
    await this.fetchDeviceTypesAndLocations();
    await this.fetchUsers(); // Загружаем пользователей для фильтра
    await this.fetchDevices();
  }
};
</script>

<style scoped>
.mr-2 {
  margin-right: 0.5rem;
}
.table-responsive {
  overflow-x: auto;
}
</style>
