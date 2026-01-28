// src/stores/auth.js
import { defineStore } from 'pinia';
import apiClient from '@/api';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: JSON.parse(localStorage.getItem('current_user')) || null,
    token: localStorage.getItem('auth_token') || null,
    loading: false, // Состояние загрузки проверки токена
  }),
  getters: {
    isAuthenticated: (state) => !!state.token && !!state.user,
    isAdmin: (state) => state.user?.groups?.some(g => g.name === 'Admins'),
    isUser: (state) => state.user?.groups?.some(g => g.name === 'Users'),
    // Пример: computed свойство для полного имени
    userFullName: (state) => state.user ? `${state.user.first_name} ${state.user.last_name}`.trim() || state.user.username : '',
  },
  actions: {
    async login(username, password) {
      // 1. Получаем токен
      const res = await apiClient.post('auth/login/', { username, password });
      this.token = res.data.key;
      localStorage.setItem('auth_token', this.token);
      
      // 2. Сразу загружаем пользователя
      await this.fetchUser();
    },
    async fetchUser() {
      try {
        const res = await apiClient.get('users/me/'); // Используем твой эндпоинт
        this.user = res.data;
        localStorage.setItem('current_user', JSON.stringify(this.user));
      } catch (e) {
        this.logout(); // Если токен невалиден - разлогиниваем
        throw e;
      }
    },
    async logout() {
      try {
        await apiClient.post('auth/logout/');
      } catch (e) {
        console.error(e);
      } finally {
        this.user = null;
        this.token = null;
        localStorage.removeItem('auth_token');
        localStorage.removeItem('current_user');
      }
    },
    // Метод для инициализации при загрузке приложения (F5)
    async init() {
      if (this.token && !this.user) {
        this.loading = true;
        await this.fetchUser().finally(() => this.loading = false);
      }
    }
  }
});
