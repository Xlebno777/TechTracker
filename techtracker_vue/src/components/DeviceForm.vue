<!-- frontend/src/components/DeviceForm.vue -->
<template>
  <div class="device-form">
    <h2>{{ isEditing ? 'Редактировать' : 'Добавить' }} Устройство</h2>

    <form @submit.prevent="handleSubmit">
      <div class="form-group">
        <label for="name">Название:</label>
        <input
          type="text"
          id="name"
          v-model="form.name"
          class="form-control"
          required
        />
      </div>

      <div class="form-group">
        <label for="serial_number">Серийный номер:</label>
        <input
          type="text"
          id="serial_number"
          v-model="form.serial_number"
          class="form-control"
          required
        />
      </div>

      <div class="form-group">
        <label for="asset_number">Инвентарный номер:</label>
        <input
          type="text"
          id="asset_number"
          v-model="form.asset_number"
          class="form-control"
        />
      </div>

      <div class="form-group">
        <label for="device_type">Тип устройства:</label>
        <select
          id="device_type"
          v-model="form.device_type"
          class="form-control"
          required
        >
          <option value="">Выберите тип</option>
          <option v-for="type in deviceTypes" :key="type.id" :value="type.id">
            {{ type.name }}
          </option>
        </select>
      </div>

      <div class="form-group">
        <label for="status">Статус:</label>
        <select
          id="status"
          v-model="form.status"
          class="form-control"
          required
        >
          <option value="">Выберите статус</option>
          <option value="active">В работе</option>
          <option value="in_repair">В ремонте</option>
          <option value="retired">Списано</option>
          <option value="in_stock">На складе</option>
          <option value="reserved">В резерве</option>
        </select>
      </div>

      <div class="form-group">
        <label for="location">Местоположение:</label>
        <select
          id="location"
          v-model="form.location"
          class="form-control"
          required
        >
          <option value="">Выберите местоположение</option>
          <option v-for="loc in locations" :key="loc.id" :value="loc.id">
            {{ loc.name }}
          </option>
        </select>
      </div>

      <div class="form-group">
        <label for="ip_address">IP-адрес:</label>
        <input
          type="text"
          id="ip_address"
          v-model="form.ip_address"
          class="form-control"
        />
      </div>

      <div class="form-group">
        <label for="mac_address">MAC-адрес:</label>
        <input
          type="text"
          id="mac_address"
          v-model="form.mac_address"
          class="form-control"
        />
      </div>

      <div class="form-group">
        <label for="owner">Владелец:</label>
        <select id="owner" v-model="form.owner" class="form-control">
          <option value="">Нет владельца</option>
          <option v-for="user in users" :key="user.id" :value="user.id">
            {{ user.username }} ({{ user.first_name }} {{ user.last_name }})
          </option>
        </select>
      </div>

      <div class="form-group">
        <label for="assigned_to">Назначен пользователю:</label>
        <select id="assigned_to" v-model="form.assigned_to" class="form-control">
          <option value="">Не назначен</option>
          <option v-for="user in users" :key="user.id" :value="user.id">
            {{ user.username }} ({{ user.first_name }} {{ user.last_name }})
          </option>
        </select>
      </div>

      <div class="form-group">
        <label for="notes">Заметки:</label>
        <textarea
          id="notes"
          v-model="form.notes"
          class="form-control"
        ></textarea>
      </div>

      <!-- Специфичные поля (упрощённо, можно сделать динамически) -->
      <div v-if="selectedDeviceType && (selectedDeviceType.name === 'Ноутбук' || selectedDeviceType.name === 'Настольный ПК' || selectedDeviceType.name === 'Моноблок')">
        <h4>Спецификации ПК</h4>
        <div class="form-group">
          <label for="cpu">Процессор:</label>
          <input type="text" id="cpu" v-model="form.computer_specs.cpu" class="form-control" />
        </div>
        <div class="form-group">
          <label for="ram_gb">ОЗУ (ГБ):</label>
          <input type="number" id="ram_gb" v-model.number="form.computer_specs.ram_gb" class="form-control" />
        </div>
        <!-- ... другие поля ComputerSpecs ... -->
      </div>

      <div v-if="selectedDeviceType && (selectedDeviceType.name.includes('Принтер') || selectedDeviceType.name.includes('Сканер'))">
        <h4>Спецификации МФУ</h4>
        <div class="form-group">
          <label for="printer_type">Тип принтера:</label>
          <select id="printer_type" v-model="form.printer_scanner_specs.printer_type" class="form-control">
            <option value="">Выберите тип</option>
            <option value="laser">Лазерный</option>
            <option value="inkjet">Струйный</option>
            <option value="matrix">Матричный</option>
          </select>
        </div>
        <div class="form-group">
          <label>
            <input type="checkbox" v-model="form.printer_scanner_specs.color_printing" />
            Цветная печать
          </label>
        </div>
        <!-- ... другие поля PrinterScannerSpecs ... -->
      </div>

      <div v-if="selectedDeviceType && (selectedDeviceType.name.includes('Коммутатор') || selectedDeviceType.name.includes('Маршрутизатор') || selectedDeviceType.name.includes('Точка доступа'))">
        <h4>Спецификации Сетевого устройства</h4>
        <div class="form-group">
          <label for="ports_count">Количество портов:</label>
          <input type="number" id="ports_count" v-model.number="form.network_specs.ports_count" class="form-control" />
        </div>
        <!-- ... другие поля NetworkDeviceSpecs ... -->
      </div>

      <button type="submit" class="btn btn-success" :disabled="loading">
        {{ loading ? 'Загрузка...' : (isEditing ? 'Сохранить' : 'Создать') }}
      </button>
      <router-link to="/devices" class="btn btn-secondary ml-2">Отмена</router-link>
    </form>

    <!-- Сообщение об ошибке -->
    <div v-if="error" class="alert alert-danger mt-3">
      Ошибка: {{ error }}
    </div>
  </div>
</template>

<script>
// import axios from 'axios';
import apiClient from '@/api';

export default {
  name: 'DeviceForm',
  props: {
    // ID устройства для редактирования (если передан)
    deviceId: {
      type: String,
      default: null
    }
  },
  data() {
    return {
      form: {
        name: '',
        serial_number: '',
        asset_number: '',
        device_type: '', // ID типа
        status: 'active',
        location: '', // ID местоположения
        ip_address: '',
        mac_address: '',
        notes: '',
        owner: null, // ID владельца
        assigned_to: null, // ID назначенного пользователя
        // Вложенные объекты для специфичных данных
        computer_specs: {
          cpu: '',
          ram_gb: null,
          // ... другие поля
        },
        printer_scanner_specs: {
          printer_type: '',
          color_printing: false,
          // ... другие поля
        },
        network_specs: {
          ports_count: null,
          // ... другие поля
        }
      },
      deviceTypes: [],
      locations: [],
      users: [], // Добавляем список пользователей
      currentUser: null, // Добавляем информацию о текущем пользователе
      loading: false,
      error: null,
      isEditing: false, // Флаг для определения режима редактирования
    };
  },
  computed: {
    // Находим выбранный тип устройства для динамического отображения полей
    selectedDeviceType() {
      return this.deviceTypes.find(type => type.id === this.form.device_type);
    }
  },
  methods: {
    async fetchCurrentUser() {
      try {
        const response = await apiClient.get('users/me/');
        this.currentUser = response.data;
      } catch (err) {
        console.error("Ошибка при загрузке данных пользователя:", err);
        this.currentUser = null;
      }
    },
    async fetchUsers() {
      try {
        const response = await apiClient.get('users/');
        this.users = response.data;
      } catch (err) {
        console.error("Ошибка при загрузке пользователей:", err);
        this.users = [];
      }
    },
    async fetchDeviceTypesAndLocations() {
      // Загружаем справочники
      try {
        const [typesResponse, locationsResponse] = await Promise.all([
          apiClient.get('api/devicetypes/'), // ✅ Новый код
          apiClient.get('api/locations/') // ✅ Новый код
        ]);
        this.deviceTypes = typesResponse.data;
        this.locations = locationsResponse.data;
      } catch (err) {
        console.error("Ошибка при загрузке справочников:", err);
        this.error = 'Не удалось загрузить справочники.';
      }
    },
    async fetchDeviceForEdit(id) {
      this.loading = true;
      this.error = null;
      try { 
        const response = await apiClient.get(`/api/devices/${id}/`);
        const deviceData = response.data;

        this.form = {
          ...deviceData,
          // Убираем вложенные объекты из основной формы
          device_type: deviceData.device_type.id,
          location: deviceData.location.id,
          owner: deviceData.owner ? deviceData.owner.id : null,
          assigned_to: deviceData.assigned_to ? deviceData.assigned_to.id : null,
          computer_specs: deviceData.computer_specs || {
            cpu: '',
            ram_gb: null,
          },
          printer_scanner_specs: deviceData.printer_scanner_specs || {
            printer_type: '',
            color_printing: false,
          },
          network_specs: deviceData.network_specs || {
            ports_count: null,
          }
          // owner и assigned_to останутся числами, как и должны
        }
        this.isEditing = true
      } catch (err) {
        console.error("Ошибка при загрузке устройства для редактирования:", err);
        this.error = 'Не удалось загрузить устройство для редактирования.';
      } finally {
        this.loading = false;
      }
    },        
    async handleSubmit() {
      this.loading = true;
      this.error = null;

      // 👇 Добавь эту строку для отладки
      console.log("Данные формы перед отправкой:", this.form);

      const method = this.isEditing ? 'PUT' : 'POST';
      const url = this.isEditing ? `api/devices/${this.deviceId}/` : 'api/devices/'; // Убедись, что используешь правильный путь
      const payload = { ...this.form,
        device_type: parseInt(this.form.device_type, 10),
        location: parseInt(this.form.location, 10),
       };

      console.log("Payload перед отправкой:", payload);

      try {
        // --- ИСПОЛЬЗУЕМ МЕТОД ЭКЗЕМПЛЯРА ---
        if (method === 'POST') {
          await apiClient.post(url, payload);
        } else if (method === 'PUT') {
          await apiClient.put(url, payload);
        }
        // --- ИЛИ ПЕРЕДАЕМ ОБЪЕКТ КОНФИГУРАЦИИ ---
        // await apiClient({ method, url, data: payload });
        // --- Убедись, что используешь 'data: payload', а не 'payload' ---

        alert(this.isEditing ? 'Устройство обновлено.' : 'Устройство создано.');
        this.$router.push('/devices');
      } catch (err) {
        console.error(`Ошибка при ${this.isEditing ? 'обновлении' : 'создании'} устройства:`, err);
        this.handleError(err);
      } finally {
        this.loading = false;
      }
    },
    handleError(err) {
      if (err.response) {
        const status = err.response.status;
        const statusText = err.response.statusText;
        const responseData = err.response.data;

        console.error("Данные ответа ошибки:", responseData); // Для отладки

        if (typeof responseData === 'string') {
          // Если ответ - строка (например, HTML-страница ошибки)
          this.error = `Сервер вернул ошибку (${status} ${statusText}). Подробности в консоли.`;
        } else if (typeof responseData === 'object' && responseData !== null) {
          // Если ответ - объект (предположительно JSON с ошибками)
          // Проверим, содержит ли он ошибки валидации
          const allErrors = [];
          // Проверяем основные поля устройства
          Object.entries(responseData).forEach(([field, errors]) => {
            if (Array.isArray(errors)) {
              // Если это массив ошибок для конкретного поля (например, { name: ["Обязательное поле."] } )
              allErrors.push(`${field}: ${errors.join(', ')}`);
            } else if (typeof errors === 'object' && errors !== null) {
              // Если это вложенный объект (например, computer_specs, printer_scanner_specs)
              // Рекурсивно извлекаем ошибки из вложенного объекта
              Object.entries(errors).forEach(([subField, subErrors]) => {
                if (Array.isArray(subErrors)) {
                  allErrors.push(`${field}.${subField}: ${subErrors.join(', ')}`);
                } else {
                  // Если внутри еще один уровень вложенности, можно добавить логику, но для простоты пока оставим
                  allErrors.push(`${field}.${subField}: ${JSON.stringify(subErrors)}`); // Или просто строковое представление
                }
              });
            } else {
              // Неожиданный формат
              allErrors.push(`${field}: ${JSON.stringify(errors)}`);
            }
          });

          if (allErrors.length > 0) {
            this.error = allErrors.join('; ');
          } else {
            // Объект пустой или не содержит ожидаемых ошибок
            this.error = `Сервер вернул ошибку (${status} ${statusText}).`;
          }
        } else {
          // Неизвестный формат ответа
          this.error = `Сервер вернул ошибку (${status} ${statusText}).`;
        }
      } else if (err.request) {
        console.error("Ошибка запроса:", err.request);
        this.error = 'Не удалось подключиться к серверу API. Проверьте соединение.';
      } else {
        const errorMessage = err.message || err || 'Неизвестная ошибка при настройке запроса';
        console.error("Ошибка Axios:", errorMessage);
        this.error = `Произошла ошибка: ${errorMessage}`;
      }
    }
  },
  async mounted() {
    await this.fetchCurrentUser(); // Получаем текущего пользователя
    await this.fetchDeviceTypesAndLocations();
    await this.fetchUsers(); // Получаем список пользователей

    // Если передан deviceId, загружаем данные для редактирования
    if (this.deviceId) {
      await this.fetchDeviceForEdit(this.deviceId);
    }
  }
};
</script>

<style scoped>
.form-group {
  margin-bottom: 1rem;
}
.form-control {
  width: 100%;
  padding: 0.375rem 0.75rem;
  font-size: 1rem;
  line-height: 1.5;
  border: 1px solid #ced4da;
  border-radius: 0.25rem;
}
.btn {
  padding: 0.375rem 0.75rem;
  font-size: 1rem;
  line-height: 1.5;
  border-radius: 0.25rem;
  cursor: pointer;
}
.btn-success { background-color: #28a745; border-color: #28a745; color: white; }
.btn-secondary { background-color: #6c757d; border-color: #6c757d; color: white; }
.ml-2 { margin-left: 0.5rem; }
.mt-3 { margin-top: 1rem; }
</style>
