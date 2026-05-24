// frontend/src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import DeviceTable from '../components/DeviceTable.vue'
import DeviceForm from '../components/DeviceForm.vue'
import AuthPage from '../components/AuthPage.vue'
import RequestForm from '../components/RequestForm.vue'
import RequestList from '../components/RequestList.vue'
import Dashboard from '../components/DashboardMain.vue'
import MonitoringRaw from '../components/MonitoringRaw.vue'
import NetworkMonitoring from '../components/NetworkMonitoring.vue'
import AgentDiagnostics from '../components/AgentDiagnostics.vue'
import MonitoringForecast from '../components/MonitoringForecast.vue'
import MonitoringPipeline from '../components/MonitoringPipeline.vue'
import MonitoringRisk from '../components/MonitoringRisk.vue'
import MonitoringDecision from '../components/MonitoringDecision.vue'
import MonitoringDemo from '../components/MonitoringDemo.vue'
import MonitoringEvaluation from '../components/MonitoringEvaluation.vue'
import MonitoringTasks from '../components/MonitoringTasks.vue'
import MonitoringSettings from '../components/MonitoringSettings.vue'
import UserManagement from '../components/UserManagement.vue'
import PrintersPage from '../components/PrintersPage.vue'

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
    path: '/agent-diagnostics',
    name: 'AgentDiagnostics',
    component: AgentDiagnostics,
    meta: { requiresAuth: true, requiresAdmin: true }
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
