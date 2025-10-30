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
        </nav>
      </div>
    </header>

    <!-- Контент -->
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script>
export default {
  name: 'App'
}
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
</style>
