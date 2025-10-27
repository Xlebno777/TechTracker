<template>
  <div class="device-list">
    <h2>Список Устройств</h2>

    <!-- Кнопка для перехода к форме создания -->
    <router-link to="/device/create" class="btn btn-primary mb-3">Добавить устройство</router-link>

    <!-- Состояние загрузки -->
    <div v-if="loading" class="alert alert-info">
      Загрузка...
    </div>

    <!-- Сообщение об ошибке -->
    <div v-if="error" class="alert alert-danger">
      Ошибка: {{ error }}
    </div>

    <!-- Список устройств -->
    <div v-if="!loading && !error">
      <div v-for="device in devices" :key="device.id" class="card mb-2">
        <div class="card-body">
          <h5 class="card-title">{{ device.name }}</h5>
          <p class="card-text">
            Серийный номер: {{ device.serial_number }}<br>
            Тип: {{ device.device_type.name }}<br> <!-- Обращение к связанной модели -->
            Статус: {{ device.status }}<br>
            Местоположение: {{ device.location.name || 'Не указано' }} <!-- Обращение к связанной модели -->
            <!-- Можно добавить больше полей -->
          </p>
          <!-- Кнопки действий -->
          <button @click="deleteDevice(device.id)" class="btn btn-danger btn-sm">Удалить</button>
          <!-- Кнопка редактирования (пока не реализована) -->
          <!-- <router-link :to="`/device/edit/${device.id}`" class="btn btn-secondary btn-sm">Редактировать</router-link> -->
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// import axios from 'axios';
import apiClient from '@/api';

export default {
  name: 'DeviceList',
  data() {
    return {
      devices: [],
      loading: true,
      error: null,
    };
  },
  methods: {
    async fetchDevices() {
      this.loading = true;
      this.error = null;
      try {
        const response = await apiClient.get('api/devices/'); // Убедись, что используешь правильный путь
        this.devices = response.data;
      } catch (err) {
        console.error("Ошибка при загрузке устройств:", err); // Полная информация об ошибке
        this.handleError(err);
      } finally {
        this.loading = false;
      }
    },
    async deleteDevice(id) {
      const result = confirm(`Вы уверены, что хотите удалить устройство с ID ${id}?`);
      if (result) {
        try {
          await apiClient.delete(`api/devices/${id}/`); // Убедись, что используешь правильный путь
          this.devices = this.devices.filter(device => device.id !== id);
          alert('Устройство успешно удалено.');
        } catch (err) {
          console.error("Ошибка при удалении устройства:", err);
          this.handleError(err); // Используем общую функцию обработки
        }
      }
    },
    // --- Новая функция для обработки ошибок ---
    handleError(err) {
      if (err.response) {
        // Сервер ответил с кодом состояния, выходящим за пределы 2xx
        const status = err.response.status;
        const statusText = err.response.statusText;
        const responseData = err.response.data;

        console.error("Данные ответа ошибки:", responseData); // <-- Важно для отладки

        if (typeof responseData === 'string') {
          // Если ответ - строка (например, HTML-страница ошибки Django)
          this.error = `Сервер вернул ошибку (${status} ${statusText}). Подробности в консоли.`;
        } else if (typeof responseData === 'object' && responseData !== null) {
          // Если ответ - объект (предположительно JSON с ошибками валидации)
          // Проверим, есть ли в нем известные ключи ошибок
          if (Object.keys(responseData).length > 0) {
            // Попробуем склеить сообщения из объекта ошибок
            const errorMessages = Object.values(responseData).flat().join(', ');
            this.error = errorMessages || `Ошибка валидации: ${statusText}`;
          } else {
            // Объект пустой или не содержит ожидаемых ошибок
            this.error = `Сервер вернул ошибку (${status} ${statusText}).`;
          }
        } else {
          // Неизвестный формат ответа
          this.error = `Сервер вернул ошибку (${status} ${statusText}).`;
        }
      } else if (err.request) {
        // Запрос был сделан, но не получен ответ (например, нет соединения)
        console.error("Ошибка запроса:", err.request);
        this.error = 'Не удалось подключиться к серверу API. Проверьте соединение.';
      } else {
        // Что-то пошло не так при настройке запроса
        console.error("Ошибка Axios:", err.message);
        this.error = `Произошла ошибка: ${err.message}`;
      }
    }
  },
  mounted() {
    this.fetchDevices();
  }
};
</script>

<style scoped>
/* Добавим немного стилей */
.card {
  border: 1px solid #ccc;
}
.mb-2 {
  margin-bottom: 0.5rem;
}
.mb-3 {
  margin-bottom: 1rem;
}
</style>
