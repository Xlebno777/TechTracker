import axios from 'axios';

// Создаем экземпляр axios с базовой конфигурацией
const apiClient = axios.create({
  baseURL: '/api/', // Базовый URL для API (прокси в vue.config.js)
  headers: {
    'Content-Type': 'application/json',
    // 'X-CSRFToken': getCSRFToken(), // Будет добавлено ниже
  },
});

// Перехватчик запросов (request interceptor)
// Добавляем CSRF-токен в заголовки каждого запроса
apiClient.interceptors.request.use(
  config => {
    // Получаем токен из localStorage
    const token = localStorage.getItem('auth_token');
    if (token) {
      // Добавляем токен в заголовок Authorization
      config.headers['Authorization'] = `Token ${token}`;
    }
    return config;
  },
  error => {
    return Promise.reject(error);
  }
);

export default apiClient;