import axios from 'axios';

// Создаем экземпляр axios с базовой конфигурацией
const apiClient = axios.create({
  baseURL: '/', // Базовый URL для API (прокси в vue.config.js)
  headers: {
    'Content-Type': 'application/json',
    // 'X-CSRFToken': getCSRFToken(), // Будет добавлено ниже
  },
});

// Функция для получения CSRF-токена из куки
function getCSRFToken() {
  const name = 'csrftoken';
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      // Does this cookie string begin with the name we want?
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// Перехватчик запросов (request interceptor)
// Добавляем CSRF-токен в заголовки каждого запроса
apiClient.interceptors.request.use(
  config => {
    // Добавляем CSRF-токен в заголовки
    const csrfToken = getCSRFToken();
    if (csrfToken) {
      config.headers['X-CSRFToken'] = csrfToken;
    }
    return config;
  },
  error => {
    return Promise.reject(error);
  }
);

export default apiClient;