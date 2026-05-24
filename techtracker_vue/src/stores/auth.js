// src/stores/auth.js
import { defineStore } from 'pinia';
import apiClient from '@/api';

const FALLBACK_ROUTE_GROUPS = {
  DeviceTable: ['Admins', 'Users'],
  DeviceCreate: ['Admins'],
  DeviceEdit: ['Admins', 'Users'],
  RequestForm: ['Admins', 'Users'],
  RequestList: ['Admins'],
  Printers: ['Admins', 'Users'],
  Monitoring: ['Admins'],
  MonitoringAnalysis: ['Admins'],
  MonitoringForecast: ['Admins'],
  MonitoringPipeline: ['Admins'],
  MonitoringRisk: ['Admins'],
  MonitoringDecision: ['Admins'],
  MonitoringDemo: ['Admins'],
  MonitoringEvaluation: ['Admins'],
  MonitoringTasks: ['Admins'],
  NetworkMonitoring: ['Admins'],
  AgentDiagnostics: ['Admins'],
  Settings: ['Admins'],
  UserManagement: ['Admins'],
  AdminRequests: ['Admins'],
};

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: JSON.parse(localStorage.getItem('current_user')) || null,
    token: localStorage.getItem('auth_token') || null,
    loading: false,
    pageAccessRules: JSON.parse(localStorage.getItem('page_access_rules') || '[]'),
    allowedRouteNames: JSON.parse(localStorage.getItem('allowed_route_names') || '[]'),
    pageAccessLoaded: false,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token && !!state.user,
    groupNames: (state) => (state.user?.groups || []).map((g) => g.name),
    isAdmin: (state) => Boolean(state.user?.is_staff) || state.user?.groups?.some(g => g.name === 'Admins'),
    isUser: (state) => state.user?.groups?.some(g => g.name === 'Users'),
    isPowerUser: (state) => state.user?.groups?.some(g => g.name === 'PowerUsers'),
    userFullName: (state) => state.user ? `${state.user.first_name} ${state.user.last_name}`.trim() || state.user.username : '',
    canRoute: (state) => (routeName) => {
      if (!routeName || routeName === 'AuthPage' || routeName === 'NoAccess') return true;
      if (!state.token) return false;
      if (state.user?.is_staff || state.user?.groups?.some(g => g.name === 'Admins')) return true;
      if (state.pageAccessLoaded) {
        return state.allowedRouteNames.includes(routeName);
      }
      const groups = (state.user?.groups || []).map((g) => g.name);
      const fallbackGroups = FALLBACK_ROUTE_GROUPS[routeName];
      if (!fallbackGroups) return true;
      return fallbackGroups.some((name) => groups.includes(name));
    },
  },
  actions: {
    async login(username, password) {
      const res = await apiClient.post('auth/login/', { username, password });
      this.token = res.data.key;
      localStorage.setItem('auth_token', this.token);
      await this.fetchUser();
      await this.fetchPageAccess();
    },
    async fetchUser() {
      try {
        const res = await apiClient.get('users/me/');
        this.user = res.data;
        localStorage.setItem('current_user', JSON.stringify(this.user));
      } catch (e) {
        await this.logout();
        throw e;
      }
    },
    async fetchPageAccess() {
      if (!this.token) return;
      try {
        const res = await apiClient.get('page-access/me/');
        this.pageAccessRules = Array.isArray(res.data?.rules) ? res.data.rules : [];
        this.allowedRouteNames = Array.isArray(res.data?.allowed_route_names) ? res.data.allowed_route_names : [];
        this.pageAccessLoaded = true;
        localStorage.setItem('page_access_rules', JSON.stringify(this.pageAccessRules));
        localStorage.setItem('allowed_route_names', JSON.stringify(this.allowedRouteNames));
      } catch (e) {
        this.pageAccessLoaded = false;
        console.error('page access load failed', e);
      }
    },
    async ensurePageAccess() {
      if (this.token && !this.pageAccessLoaded) {
        await this.fetchPageAccess();
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
        this.pageAccessRules = [];
        this.allowedRouteNames = [];
        this.pageAccessLoaded = false;
        localStorage.removeItem('auth_token');
        localStorage.removeItem('current_user');
        localStorage.removeItem('page_access_rules');
        localStorage.removeItem('allowed_route_names');
      }
    },
    async init() {
      if (this.token && !this.user) {
        this.loading = true;
        await this.fetchUser().finally(() => { this.loading = false; });
      }
      if (this.token) {
        await this.ensurePageAccess();
      }
    }
  }
});
