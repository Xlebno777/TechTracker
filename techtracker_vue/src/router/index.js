// frontend/src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const DeviceTable = () => import(/* webpackChunkName: "devices" */ '../components/DeviceTable.vue')
const DeviceForm = () => import(/* webpackChunkName: "devices" */ '../components/DeviceForm.vue')
const AuthPage = () => import(/* webpackChunkName: "auth" */ '../components/AuthPage.vue')
const RequestForm = () => import(/* webpackChunkName: "requests" */ '../components/RequestForm.vue')
const RequestList = () => import(/* webpackChunkName: "requests" */ '../components/RequestList.vue')
const Dashboard = () => import(/* webpackChunkName: "monitoring-analysis" */ '../components/DashboardMain.vue')
const MonitoringRaw = () => import(/* webpackChunkName: "monitoring-raw" */ '../components/MonitoringRaw.vue')
const NetworkMonitoring = () => import(/* webpackChunkName: "network-monitoring" */ '../components/NetworkMonitoring.vue')
const AgentDiagnostics = () => import(/* webpackChunkName: "agent-diagnostics" */ '../components/AgentDiagnostics.vue')
const MonitoringForecast = () => import(/* webpackChunkName: "monitoring-forecast" */ '../components/MonitoringForecast.vue')
const MonitoringPipeline = () => import(/* webpackChunkName: "monitoring-pipeline" */ '../components/MonitoringPipeline.vue')
const MonitoringRisk = () => import(/* webpackChunkName: "monitoring-risk" */ '../components/MonitoringRisk.vue')
const MonitoringDecision = () => import(/* webpackChunkName: "monitoring-decision" */ '../components/MonitoringDecision.vue')
const MonitoringDemo = () => import(/* webpackChunkName: "monitoring-demo" */ '../components/MonitoringDemo.vue')
const MonitoringEvaluation = () => import(/* webpackChunkName: "monitoring-evaluation" */ '../components/MonitoringEvaluation.vue')
const MonitoringTasks = () => import(/* webpackChunkName: "monitoring-tasks" */ '../components/MonitoringTasks.vue')
const MonitoringSettings = () => import(/* webpackChunkName: "settings" */ '../components/MonitoringSettings.vue')
const SystemHealth = () => import(/* webpackChunkName: "system-health" */ '../components/SystemHealth.vue')
const UserManagement = () => import(/* webpackChunkName: "users" */ '../components/UserManagement.vue')
const PrintersPage = () => import(/* webpackChunkName: "printers" */ '../components/PrintersPage.vue')

const NoAccessPage = {
  template: `
    <main class="p-4">
      <section style="max-width: 720px; background: #fff; border: 1px solid #dbe3ef; border-radius: 16px; padding: 1.25rem;">
        <h1 style="margin: 0 0 .5rem; color: #0f172a;">Нет доступа к разделам системы</h1>
        <p style="margin: 0; color: #64748b; line-height: 1.5;">
          Для вашей учетной записи не назначены страницы интерфейса. Обратитесь к администратору,
          чтобы добавить вашу группу в правила доступа на странице «Пользователи».
        </p>
      </section>
    </main>
  `,
}

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
    path: '/no-access',
    name: 'NoAccess',
    component: NoAccessPage,
    meta: { requiresAuth: true }
  },
  {
    path: '/monitoring-analysis',
    name: 'MonitoringAnalysis',
    component: Dashboard,
    meta: { requiresAuth: true, forbidUsers: true }
  },
  {
    path: '/monitoring',
    name: 'Monitoring',
    component: MonitoringRaw,
    meta: { requiresAuth: true, forbidUsers: true }
  },
  {
    path: '/network-monitoring',
    name: 'NetworkMonitoring',
    component: NetworkMonitoring,
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/agents',
    name: 'AgentDiagnostics',
    component: AgentDiagnostics,
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/agent-diagnostics',
    redirect: '/agents'
  },
  {
    path: '/monitoring-forecast',
    name: 'MonitoringForecast',
    component: MonitoringForecast,
    meta: { requiresAuth: true, forbidUsers: true }
  },
  {
    path: '/monitoring-pipeline',
    name: 'MonitoringPipeline',
    component: MonitoringPipeline,
    meta: { requiresAuth: true, forbidUsers: true }
  },
  {
    path: '/monitoring-risk',
    name: 'MonitoringRisk',
    component: MonitoringRisk,
    meta: { requiresAuth: true, forbidUsers: true }
  },
  {
    path: '/monitoring-decision',
    name: 'MonitoringDecision',
    component: MonitoringDecision,
    meta: { requiresAuth: true, forbidUsers: true }
  },
  {
    path: '/monitoring-demo',
    name: 'MonitoringDemo',
    component: MonitoringDemo,
    meta: { requiresAuth: true, forbidUsers: true }
  },
  {
    path: '/monitoring-evaluation',
    name: 'MonitoringEvaluation',
    component: MonitoringEvaluation,
    meta: { requiresAuth: true, forbidUsers: true }
  },
  {
    path: '/monitoring-tasks',
    name: 'MonitoringTasks',
    component: MonitoringTasks,
    meta: { requiresAuth: true, forbidUsers: true }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: MonitoringSettings,
    meta: { requiresAuth: true, forbidUsers: true }
  },
  {
    path: '/system-health',
    name: 'SystemHealth',
    component: SystemHealth,
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/users',
    name: 'UserManagement',
    component: UserManagement,
    meta: { requiresAuth: true, requiresAdmin: true }
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

function firstAllowedRoute(auth) {
  const priority = [
    'DeviceTable',
    'MonitoringPipeline',
    'Monitoring',
    'Printers',
    'RequestForm',
    'Settings',
  ];
  return priority.find((name) => auth.canRoute(name)) || auth.allowedRouteNames?.[0] || 'NoAccess';
}

router.beforeEach(async (to, from, next) => {
  const auth = useAuthStore();
  const hasToken = localStorage.getItem('auth_token') !== null;

  if (to.name === 'AuthPage') {
    next(hasToken ? { name: firstAllowedRoute(auth) } : undefined);
    return;
  }

  if (!to.meta?.requiresAuth) {
    next();
    return;
  }

  if (!hasToken) {
    next({ name: 'AuthPage' });
    return;
  }

  try {
    if (!auth.user) {
      await auth.fetchUser();
    }
    await auth.ensurePageAccess();
  } catch {
    next({ name: 'AuthPage' });
    return;
  }

  if (to.name !== 'NoAccess' && !auth.canRoute(to.name)) {
    next({ name: firstAllowedRoute(auth) });
    return;
  }

  next();
});

export default router
