// frontend/src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'
import DeviceTable from '../components/DeviceTable.vue'
import DeviceForm from '../components/DeviceForm.vue'
import AuthPage from '../components/AuthPage.vue'
import RequestForm from '../components/RequestForm.vue'
import RequestList from '../components/RequestList.vue'
import Dashboard from '../components/DashboardMain.vue'
import PrintersPage from '../components/PrintersPage.vue'


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
    meta: { requiresAuth: true, forbidUsers: true }
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
    meta: { requiresAuth: true, requiresAdmin: true }
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
    meta: { requiresAuth: true, forbidUsers: true }
  },
  {
    path: '/admin/requests',
    name: 'AdminRequests',
    component: RequestList,
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/printers',
    name: 'Printers',
    component: PrintersPage,
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

  if (to.name === 'DeviceTable' || to.name === 'DeviceCreate' || to.name === 'DeviceEdit' || to.name === 'RequestForm' || to.name === 'RequestList' || to.name === 'Printers' || to.name === 'Dashboard' || to.name === 'AdminRequests') {
    if (!hasToken) {
      next({ name: 'AuthPage' });
    } else {
      const user = JSON.parse(localStorage.getItem('current_user') || 'null');
      const isAdmin = user?.groups?.some(g => g.name === 'Admins');
      const isUser = user?.groups?.some(g => g.name === 'Users');
      if (to.meta?.requiresAdmin && !isAdmin) {
        next({ name: 'DeviceTable' });
        return;
      }
      if (to.meta?.forbidUsers && isUser) {
        next({ name: 'DeviceTable' });
        return;
      }
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
