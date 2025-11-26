// frontend/src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'
import DeviceTable from '../components/DeviceTable.vue'
import DeviceForm from '../components/DeviceForm.vue'
import AuthPage from '../components/AuthPage.vue'
import RequestForm from '../components/RequestForm.vue'
import RequestList from '../components/RequestList.vue'
import Dashboard from '../components/DashboardMain.vue'


const routes = [
  {
    path: '/',
    redirect: '/devices' // Перенаправляем с главной на список устройств
  },
  {
    path: '/devices',
    name: 'DeviceTable',
    component: DeviceTable,
    meta: { requiresAuth: true }
  },
  {
    path: '/device/create',
    name: 'DeviceCreate',
    component: DeviceForm,
    meta: { requiresAuth: true }
    // props: { deviceId: null } // Явно передаем null для deviceId
  },
  {
    path: '/device/edit/:deviceId',
    name: 'DeviceEdit',
    component: DeviceForm,
    props: true,
    meta: { requiresAuth: true } // Передаем :deviceId как prop в компонент
  },
  {
    path: '/request/create', // <-- Новый маршрут
    name: 'RequestForm',
    component: RequestForm,
    meta: { requiresAuth: true }
  },
  {
    path: '/requests', // <-- Новый маршрут
    name: 'RequestList',
    component: RequestList,
    meta: { requiresAuth: true }
  },
  {
    path: '/login', // <-- Путь для страницы входа
    name: 'AuthPage',
    component: AuthPage
  },
  {
    path: '/dashboard',
    name: 'Dashboard', // Теперь главная - это дашборд
    component: Dashboard,
    meta: { requiresAuth: true }
  }
]

const router = createRouter({ // <-- router создаётся ЗДЕСЬ
  history: createWebHistory(process.env.BASE_URL),
  routes
})

// Глобальный маршрут-страж (guard)
// Проверяет, есть ли токен перед доступом к защищённым маршрутам
router.beforeEach((to, from, next) => {
  const hasToken = localStorage.getItem('auth_token') !== null;

  if (to.name === 'DeviceTable' || to.name === 'DeviceCreate' || to.name === 'DeviceEdit' || to.name === 'RequestForm' || to.name === 'RequestList') {
    if (!hasToken) {
      next({ name: 'AuthPage' });
    } else {
      next();
    }
  } else if (to.name === 'AuthPage') {
    // Если уже вошёл, не показываем страницу входа
    if (hasToken) {
      next({ name: 'DeviceTable' });
    } else {
      next();
    }
  } else {
    next(); // Для остальных маршрутов
  }
});

export default router