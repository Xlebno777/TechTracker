<!-- frontend/src/App.vue -->
<template>
  <div id="app">
    <!-- Навигационная панель -->
    <nav class="navbar navbar-expand-lg navbar-light bg-light">
      <div class="container-fluid">
        <a class="navbar-brand" href="/">Учет Техники</a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
          <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navbarNav">
          <ul class="navbar-nav">
            <li class="nav-item">
              <router-link class="nav-link" :to="{ name: 'DeviceTable' }">Устройства</router-link>
            </li>
            <li class="nav-item">
              <router-link class="nav-link" :to="{ name: 'DeviceCreate' }">Добавить</router-link>
            </li>
          </ul>
        </div>
      </div>
    </nav>

    <!-- Контейнер для отображения компонентов по маршрутам -->
    <div class="container mt-4">
      <router-view></router-view>
    </div>
  </div>
</template>

<script>
export default {
  name: 'App',
}
</script>

<style>
/* Глобальные стили */
body {
  padding-top: 60px; /* Отступ сверху для navbar */
}
</style>