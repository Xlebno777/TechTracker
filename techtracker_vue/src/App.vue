<template>
  <div id="app" :class="['app-shell', { 'nav-collapsed': isNavCollapsed }]">
    <aside class="side-nav">
      <div class="nav-top">
        <router-link to="/" class="brand">
          <i class="pi pi-desktop"></i>
          <span>Учет Техники</span>
        </router-link>
        <button class="nav-toggle" @click="isNavCollapsed = !isNavCollapsed" aria-label="toggle nav">
          <i :class="isNavCollapsed ? 'pi pi-angle-right' : 'pi pi-angle-left'"></i>
        </button>
      </div>

      <nav class="nav-menu">
        <router-link v-if="!auth.isUser" :to="{ name: 'Monitoring' }" class="nav-link" active-class="active">
          <i class="pi pi-chart-line"></i>
          <span>Мониторинг</span>
        </router-link>

        <router-link v-if="!auth.isUser" :to="{ name: 'MonitoringAnalysis' }" class="nav-link" active-class="active">
          <i class="pi pi-chart-bar"></i>
          <span>Анализ мониторинга</span>
        </router-link>

        <router-link :to="{ name: 'DeviceTable' }" class="nav-link" active-class="active">
          <i class="pi pi-table"></i>
          <span>Устройства</span>
        </router-link>

        <router-link v-if="!auth.isUser" :to="{ name: 'DeviceCreate' }" class="nav-link" active-class="active">
          <i class="pi pi-plus"></i>
          <span>Добавить</span>
        </router-link>

        <router-link :to="{ name: 'Printers' }" class="nav-link" active-class="active">
          <i class="pi pi-print"></i>
          <span>Принтеры</span>
        </router-link>

        <router-link :to="{ name: 'RequestForm' }" class="nav-link" active-class="active">
          <i class="pi pi-envelope"></i>
          <span>Заявка</span>
        </router-link>

        <router-link v-if="auth.isAdmin" :to="{ name: 'AdminRequests' }" class="nav-link" active-class="active">
          <i class="pi pi-list"></i>
          <span>Заявки</span>
        </router-link>

        <router-link v-if="auth.isAdmin" :to="{ name: 'AgentDiagnostics' }" class="nav-link" active-class="active">
          <i class="pi pi-shield"></i>
          <span>Диагностика агента</span>
        </router-link>

        <router-link v-if="auth.isAdmin" :to="{ name: 'AiDiagnostics' }" class="nav-link" active-class="active">
          <i class="pi pi-bolt"></i>
          <span>Диагностика (ИИ)</span>
        </router-link>
      </nav>

      <div class="nav-footer">
        <div class="nav-auth">
          <template v-if="!auth.loading">
            <Button 
              v-if="!auth.isAuthenticated" 
              label="Вход" 
              icon="pi pi-sign-in" 
              severity="success" 
              outlined 
              @click="$router.push('/login')" 
            />
            <Button 
              v-else 
              :label="isNavCollapsed ? '' : `Выход (${auth.user.username})`" 
              icon="pi pi-sign-out" 
              severity="danger" 
              outlined 
              @click="handleLogout" 
            />
          </template>
          <i v-else class="pi pi-spin pi-spinner" style="font-size: 1.5rem"></i>
        </div>
      </div>
    </aside>

    <main class="main-content">
      <router-view v-if="!auth.loading" />
      <div v-else class="loading-screen">
        <i class="pi pi-spin pi-spinner" style="font-size: 3rem; color: #0ea5e9;"></i>
      </div>
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import Button from 'primevue/button'; // Используем компонент Button

const auth = useAuthStore();
const router = useRouter();
const isNavCollapsed = ref(false);

const handleLogout = async () => {
  await auth.logout();
  router.push('/login');
};

onMounted(() => {
  auth.init();
});
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 260px 1fr;
  background: #f4f6f9;
  color: #0f172a;
  font-family: 'Inter', 'Segoe UI', Roboto, sans-serif;
  transition: grid-template-columns 0.25s ease;
}

.app-shell.nav-collapsed {
  grid-template-columns: 78px 1fr;
}

.side-nav {
  position: sticky;
  top: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 1.25rem 1rem 1.25rem 1rem;
  background: #0b1220;
  color: #e2e8f0;
  border-right: 1px solid rgba(148, 163, 184, 0.15);
}

.nav-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-weight: 700;
  font-size: 1.1rem;
  color: #e2e8f0;
  text-decoration: none;
  white-space: nowrap;
}

.nav-toggle {
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(30, 41, 59, 0.7);
  color: #e2e8f0;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: transform 0.2s ease, background 0.2s ease;
}

.nav-toggle:hover {
  transform: translateY(-1px);
  background: rgba(51, 65, 85, 0.9);
}

.nav-menu {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  color: #cbd5f5;
  text-decoration: none;
  padding: 0.65rem 0.8rem;
  border-radius: 10px;
  transition: all 0.2s ease;
  font-weight: 500;
}

.nav-link i {
  font-size: 1rem;
}

.nav-link:hover {
  background: rgba(56, 189, 248, 0.12);
  color: #e0f2fe;
}

.nav-link.active {
  background: rgba(56, 189, 248, 0.2);
  color: #e0f2fe;
  box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.25);
}

.nav-footer {
  padding-top: 1rem;
}

.nav-auth :deep(.p-button) {
  width: 100%;
  justify-content: center;
}

.app-shell.nav-collapsed .nav-link span,
.app-shell.nav-collapsed .brand span,
.app-shell.nav-collapsed .nav-auth :deep(.p-button-label) {
  display: none;
}

.main-content {
  padding: 2rem;
  min-height: 100vh;
  width: 100%;
}

.loading-screen {
  height: calc(100vh - 4rem);
  display: grid;
  place-items: center;
}

:global(.page-shell) {
  width: 100%;
}

:global(.page-shell .card) {
  background: #ffffff;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
}

:global(.tech-table) {
  border-radius: 14px;
  overflow: hidden;
}

:global(.tech-table .p-datatable-thead > tr > th) {
  background: #f8fafc;
  color: #1e293b;
  font-weight: 600;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

:global(.tech-table .p-datatable-tbody > tr > td) {
  color: #0f172a;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

:global(.tech-table .p-datatable-tbody > tr:hover) {
  background: #f1f5f9;
}
</style>
