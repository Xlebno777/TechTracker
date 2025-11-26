<template>
  <div id="app" class="app-layout">
    <header class="navbar-glass">
      <div class="nav-container">
        <router-link to="/" class="brand">
          <i class="pi pi-desktop"></i>
          <span>Учет Техники</span>
        </router-link>
   
        <router-link :to="{ name: 'Dashboard' }" class="nav-link" active-class="active">
          <i class="pi pi-chart-bar"></i>
          <span>Дашборд</span>
        </router-link>

        <nav class="nav-menu">
          <router-link :to="{ name: 'DeviceTable' }" class="nav-link" active-class="active">
            <i class="pi pi-table"></i>
            <span>Устройства</span>
          </router-link>

          <router-link :to="{ name: 'DeviceCreate' }" class="nav-link" active-class="active">
            <i class="pi pi-plus"></i>
            <span>Добавить</span>
          </router-link>

          <router-link :to="{ name: 'RequestForm' }" class="nav-link" active-class="active">
            <i class="pi pi-envelope"></i>
            <span>Заявка</span>
          </router-link>

          <!-- Используем геттер из store -->
          <router-link v-if="auth.isAdmin" :to="{ name: 'RequestList' }" class="nav-link" active-class="active">
            <i class="pi pi-list"></i>
            <span>Заявки</span>
          </router-link>
        </nav>

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
              :label="`Выход (${auth.user.username})`" 
              icon="pi pi-sign-out" 
              severity="danger" 
              outlined 
              @click="handleLogout" 
            />
          </template>
          <i v-else class="pi pi-spin pi-spinner" style="font-size: 1.5rem"></i>
        </div>
      </div>
    </header>

    <main class="main-content">
      <!-- Показываем контент только когда проверили токен -->
      <router-view v-if="!auth.loading" />
      <div v-else class="loading-screen">
        <i class="pi pi-spin pi-spinner" style="font-size: 3rem; color: #007ad9;"></i>
      </div>
    </main>
  </div>
</template>

<script setup>
import { onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import Button from 'primevue/button'; // Используем компонент Button

const auth = useAuthStore();
const router = useRouter();

const handleLogout = async () => {
  await auth.logout();
  router.push('/login');
};

onMounted(() => {
  auth.init();
});
</script>

<style scoped>
/* Стили те же, немного почистил кнопки, так как используем PrimeVue Button компонент */
.app-layout {
  font-family: 'Inter', 'Segoe UI', Roboto, sans-serif;
  background-color: #f8fafc;
  min-height: 100vh;
  color: #1f2937;
}

.navbar-glass {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  backdrop-filter: blur(12px);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(245, 247, 250, 0.9));
  border-bottom: 1px solid rgba(255, 255, 255, 0.4);
  box-shadow: 0 1px 8px rgba(0, 0, 0, 0.05);
  z-index: 100;
}

.nav-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0.75rem 1.5rem;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 700;
  font-size: 1.3rem;
  color: #0284c7;
  text-decoration: none;
}

.nav-menu {
  display: flex;
  gap: 1rem;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #64748b;
  font-weight: 500;
  text-decoration: none;
  padding: 0.5rem 0.8rem;
  border-radius: 8px;
  transition: all 0.2s;
}

.nav-link:hover, .nav-link.active {
  color: #0284c7;
  background-color: #e0f2fe;
}

.nav-auth {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.main-content {
  padding-top: 80px;
  max-width: 1200px;
  margin: 0 auto;
  padding-left: 1.5rem;
  padding-right: 1.5rem;
}

.loading-screen {
  height: 80vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>