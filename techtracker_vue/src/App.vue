<!-- frontend/src/App.vue -->
<template>
  <div id="app" class="app-layout">
    <!-- Современная панель навигации -->
    <header class="navbar-glass">
      <div class="nav-container">
        <!-- Левая часть: Логотип -->
        <router-link to="/" class="brand">
          <i class="pi pi-desktop"></i>
          <span>Учет Техники</span>
        </router-link>

        <!-- Правая часть: Меню -->
        <nav class="nav-menu">
          <router-link
            :to="{ name: 'DeviceTable' }"
            class="nav-link"
            active-class="active"
          >
            <i class="pi pi-table"></i>
            <span>Устройства</span>
          </router-link>

          <router-link
            :to="{ name: 'DeviceCreate' }"
            class="nav-link"
            active-class="active"
          >
            <i class="pi pi-plus"></i>
            <span>Добавить</span>
          </router-link>
          <!-- Ссылка "Заявка" для всех пользователей -->
          <router-link
            :to="{ name: 'RequestForm' }"
            class="nav-link"
            active-class="active"
          >
            <i class="pi pi-envelope"></i>
            <span>Заявка</span>
          </router-link>

          <!-- Ссылка "Заявки" только для администраторов -->
          <router-link
            v-if="isAdminUser"
            :to="{ name: 'RequestList' }"
            class="nav-link"
            active-class="active"
          >
            <i class="pi pi-list"></i>
            <span>Заявки</span>
          </router-link>
        </nav>

        <!-- Кнопка "Вход/Выход" -->
        <div class="nav-auth">
          <button v-if="!isAuthenticated" class="btn btn-outline-success" @click="goToLogin">
            Вход
          </button>
          <button v-else class="btn btn-outline-danger" @click="logout">
            Выход ({{ currentUser.username }})
          </button>
        </div>
      </div>
    </header>

    <!-- Контент -->
    <main class="main-content">
      <router-view v-if="!loadingAuth" />
      <!-- Индикатор загрузки, если данные ещё не готовы -->
      <div v-else class="p-d-flex p-jc-center p-ai-center" style="height: 70vh;">
        <i class="pi pi-spin pi-spinner" style="font-size: 2rem; color: #007ad9;"></i>
      </div>
    </main>
  </div>
</template>

<script>
import apiClient from '@/api';

export default {
  name: 'App',
  data() {
    return {
      currentUser: null,
      isAuthenticated: false,
      loadingAuth: true, // Добавим флаг загрузки
    };
  },
  computed: {
    // Вычисляемое свойство для проверки, является ли пользователь администратором
    isAdminUser() {
      if (!this.currentUser || !this.currentUser.groups) {
        return false;
      }
      const isAdmin = this.currentUser.groups.some(group => group.name === 'Admins');
      return isAdmin;
    }
  },
  methods: {
    goToLogin() {
      this.$router.push('/login');
    },
    async logout() {
      try {
        // Вызываем API logout (dj-rest-auth удаляет токен на сервере)
        await apiClient.post('auth/logout/');
        // Очищаем локальное состояние (токен)
        localStorage.removeItem('auth_token');
        // localStorage.removeItem('user_authenticated'); // Необязательно, если не используем
        this.currentUser = null;
        this.isAuthenticated = false;
        // Перенаправляем на страницу входа
        this.$router.push('/login');
      } catch (err) {
        console.error("Ошибка выхода:", err);
        // Даже если API logout не сработал, всё равно очищаем локальное состояние
        localStorage.removeItem('auth_token');
        // localStorage.removeItem('user_authenticated');
        this.currentUser = null;
        this.isAuthenticated = false;
        this.$router.push('/login');
      }
    },
    async refreshUser() {
      try {
        const response = await apiClient.get('users/me/');
        this.currentUser = response.data;
        this.isAuthenticated = true;
      } catch {
        this.currentUser = null;
        this.isAuthenticated = false;
      }
      this.loadingAuth = false; // Убираем индикатор загрузки после проверки
    }
  },
  async mounted() {
    await this.refreshUser(); // Проверяем статус при монтировании App
  }
};
</script>

<style scoped>
.app-layout {
  font-family: 'Inter', 'Segoe UI', Roboto, sans-serif;
  background-color: #f8fafc;
  min-height: 100vh;
  color: #1f2937;
}

/* === ШАПКА === */
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

/* Контейнер */
.nav-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1100px;
  margin: 0 auto;
  padding: 0.75rem 1.5rem;
}

/* Логотип */
.brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 1.2rem;
  color: #007ad9;
  text-decoration: none;
  transition: color 0.3s ease;
}

.brand:hover {
  color: #0d6efd;
}

/* Меню */
.nav-menu {
  display: flex;
  gap: 1.5rem;
}

/* Ссылки */
.nav-link {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: #475569;
  font-weight: 500;
  font-size: 1rem;
  text-decoration: none;
  transition: all 0.25s ease;
  padding: 0.3rem 0.6rem;
  border-radius: 6px;
}

.nav-link:hover {
  color: #007ad9;
  background-color: rgba(0, 122, 217, 0.1);
}

.nav-link.active {
  color: #007ad9;
  font-weight: 600;
  background-color: rgba(0, 122, 217, 0.08);
}

/* Контент */
.main-content {
  padding-top: 70px; /* чтобы не пряталось под navbar */
  padding-left: 1.5rem;
  padding-right: 1.5rem;
}

.nav-auth {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn {
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  border-radius: 0.25rem;
  cursor: pointer;
  border: 1px solid transparent;
  text-decoration: none;
  display: inline-block;
  text-align: center;
  transition: color 0.15s ease-in-out, background-color 0.15s ease-in-out, border-color 0.15s ease-in-out, box-shadow 0.15s ease-in-out;
}

.btn-outline-success {
  color: #28a745;
  border-color: #28a745;
}

.btn-outline-success:hover {
  color: #fff;
  background-color: #28a745;
  border-color: #28a745;
}

.btn-outline-danger {
  color: #dc3545;
  border-color: #dc3545;
}

.btn-outline-danger:hover {
  color: #fff;
  background-color: #dc3545;
  border-color: #dc3545;
}
</style>
