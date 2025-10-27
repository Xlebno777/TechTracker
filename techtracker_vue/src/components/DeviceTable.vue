<template>
  <div class="device-table">
    <h2>Таблица Устройств</h2>

    <!-- Кнопка для перехода к форме создания -->
    <router-link to="/device/create" class="btn btn-primary mb-3">Добавить устройство</router-link>

    <!-- Фильтры -->
    <div class="card mb-3">
      <div class="card-body">
        <h5 class="card-title">Фильтры</h5>
        <div class="row">
          <div class="col-md-3">
            <label for="filter_type">Тип устройства:</label>
            <select id="filter_type" v-model="filters.device_type" class="form-control">
              <option value="">Все типы</option>
              <option v-for="type in deviceTypes" :key="type.id" :value="type.id">
                {{ type.name }}
              </option>
            </select>
          </div>
          <div class="col-md-3">
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
          <div class="col-md-3">
            <label for="filter_location">Местоположение:</label>
            <select id="filter_location" v-model="filters.location" class="form-control">
              <option value="">Все местоположения</option>
              <option v-for="loc in locations" :key="loc.id" :value="loc.id">
                {{ loc.name }}
              </option>
            </select>
          </div>
          <div class="col-md-3">
            <label for="filter_search">Поиск (название, серийный):</label>
            <input type="text" id="filter_search" v-model="filters.search" class="form-control" placeholder="Введите..." />
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
            <th>IP-адрес</th>
            <th>MAC-адрес</th>
            <th>Действия</th> <!-- Колонка для кнопок -->
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
            <td>{{ device.ip_address || '—' }}</td>
            <td>{{ device.mac_address || '—' }}</td>
            <td>
              <!-- Кнопка Редактировать (доступна админам и PowerUsers) -->
              <router-link
                :to="`/device/edit/${device.id}`"
                class="btn btn-primary btn-sm mr-2"
                :disabled="!canEdit(device)"
              >
                Редактировать
              </router-link>
              <!-- Кнопка Удалить (доступна админам) -->
              <button
                @click="deleteDevice(device.id)"
                class="btn btn-danger btn-sm"
                :disabled="!canDelete(device)"
              >
                Удалить
              </button>
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
      devices: [], // Массив для хранения всех устройств
      deviceTypes: [], // Массив типов устройств (для фильтра)
      locations: [], // Массив местоположений (для фильтра)
      loading: true, // Флаг загрузки
      error: null, // Сообщение об ошибке
      filters: {
        device_type: '',
        status: '',
        location: '',
        search: '', // Поле для поиска по названию/серийнику
      }
    };
  },
  computed: {
    // Вычисляемые свойства для фильтрации
    filteredDevices() {
      return this.devices.filter(device => {
        // Фильтр по типу
        if (this.filters.device_type && device.device_type.id !== this.filters.device_type) {
          return false;
        }
        // Фильтр по статусу
        if (this.filters.status && device.status !== this.filters.status) {
          return false;
        }
        // Фильтр по местоположению
        if (this.filters.location && device.location.id !== this.filters.location) {
          return false;
        }
        // Поиск по названию или серийному номеру (частичное совпадение)
        if (this.filters.search && !device.name.toLowerCase().includes(this.filters.search.toLowerCase()) && !device.serial_number.toLowerCase().includes(this.filters.search.toLowerCase())) {
          return false;
        }
        return true; // Если все фильтры пройдены
      });
    },
    // Определяем, может ли текущий пользователь редактировать устройство
    // Пока упрощенно: редактировать может админ или PowerUser
    // В реальности можно проверять разрешения через API или хранить роль в состоянии
    canEdit() {
      return () => {
      // Проверяем, есть ли у текущего пользователя роль, позволяющая редактировать
      // Предполагаем, что fetchCurrentUser был вызван и currentUser заполнен
      if (!this.currentUser) {
        // Если данные пользователя не загружены, не показываем кнопку
        return false;
      }
      // Предполагаем, что is_staff означает админа
      // И что PowerUsers входят в группу с именем 'PowerUsers'
      // (В Django DRF сериализатор User возвращает 'groups' как список объектов {'id': X, 'name': 'Y'})
      return this.currentUser.is_staff || this.currentUser.groups.some(group => group.name === 'PowerUsers');
    };
    },
    // Определяем, может ли текущий пользователь удалить устройство
    // Удаление обычно доступно только админам
    canDelete() {
    // Функция, возвращаемая computed, будет вызываться в шаблоне как canDelete(device)
    return () => {
      // Проверяем, есть ли у текущего пользователя роль, позволяющая удалять
      if (!this.currentUser) {
        return false;
      }
      // Удаление доступно только админам (is_staff)
      return this.currentUser.is_staff;
    };
  }
  },
  methods: {
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
    async fetchCurrentUser() {
      // Получаем информацию о текущем аутентифицированном пользователе
      try {
        const response = await apiClient.get('users/me/'); // Используем наш кастомный эндпоинт
        this.currentUser = response.data;
      } catch (err) {
        console.error("Ошибка при загрузке данных пользователя:", err);
        // Не критично для отображения списка, но логично уведомить
        // this.error = 'Не удалось загрузить данные пользователя.'; // Не будем делать это ошибкой списка
        this.currentUser = null; // Устанавливаем null, если не удалось получить
      }
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
          // Проверяем, была ли ошибка связана с разрешениями
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
    // Загружаем список устройств, справочники и данные пользователя при монтировании
    await this.fetchDeviceTypesAndLocations();
    await this.fetchCurrentUser(); // Сначала получаем пользователя
    await this.fetchDevices(); // Потом загружаем устройства
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
