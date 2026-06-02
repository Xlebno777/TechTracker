import axios from 'axios';

const MAX_RESPONSE_PREVIEW = 520;

function compactText(value) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim();
}

function requestUrl(config = {}) {
  const baseURL = String(config.baseURL || '');
  const url = String(config.url || '');
  if (!baseURL || /^https?:\/\//i.test(url)) return url;

  if (/^https?:\/\//i.test(baseURL)) {
    try {
      return new URL(url, baseURL.endsWith('/') ? baseURL : `${baseURL}/`).toString();
    } catch {
      return `${baseURL.replace(/\/+$/, '')}/${url.replace(/^\/+/, '')}`;
    }
  }

  return `${baseURL.replace(/\/+$/, '')}/${url.replace(/^\/+/, '')}`;
}

function responsePreview(data) {
  if (data?.detail) return compactText(data.detail);
  if (data?.message) return compactText(data.message);
  if (data?.error) return compactText(data.error);

  if (typeof data === 'string' && data.trim()) {
    const title = data.match(/<title[^>]*>(.*?)<\/title>/is)?.[1];
    const h1 = data.match(/<h1[^>]*>(.*?)<\/h1>/is)?.[1];
    const plain = data
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<[^>]+>/g, ' ');
    const parts = [title, h1, plain].map(compactText).filter(Boolean);
    return compactText([...new Set(parts)].join(' | ')).slice(0, MAX_RESPONSE_PREVIEW);
  }

  if (data && typeof data === 'object') {
    try {
      return JSON.stringify(data).slice(0, MAX_RESPONSE_PREVIEW);
    } catch {
      return '';
    }
  }

  return '';
}

export function describeApiError(error, fallback = 'Ошибка запроса') {
  const status = error?.response?.status;
  const method = String(error?.config?.method || 'GET').toUpperCase();
  const url = requestUrl(error?.config || {});
  const code = error?.code ? `Код клиента: ${error.code}` : '';
  const responseText = responsePreview(error?.response?.data);
  const message = compactText(error?.message);

  const parts = [fallback];
  if (status) parts.push(`HTTP ${status}`);
  if (url) parts.push(`Запрос: ${method} ${url}`);
  if (responseText) parts.push(`Ответ: ${responseText}`);
  if (!responseText && message) parts.push(`Причина: ${message}`);
  if (code) parts.push(code);

  return parts.filter(Boolean).join('. ');
}

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

apiClient.interceptors.response.use(
  response => response,
  error => {
    if (error.response && error.response.status === 401) {
      // Если сервер вернул 401 (Unauthorized), значит токен невалиден
      localStorage.removeItem('auth_token');
      window.location.href = '/login'; // Жесткий редирект или через router
    }
    return Promise.reject(error);
  }
);


export default apiClient;
