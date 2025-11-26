<template>
  <div class="dashboard p-4">
    <div class="flex justify-content-between align-items-center mb-4">
      <div>
        <h2 class="text-2xl font-bold m-0 text-900">Дашборд мониторинга</h2>
        <p class="text-500 m-0">Обзор состояния инфраструктуры в реальном времени</p>
      </div>
      <div class="flex gap-2">
        <Button icon="pi pi-refresh" label="Обновить" rounded text @click="refreshData" :loading="loading" />
      </div>
    </div>

    <!-- Карточки статистики (Stat Cards) -->
    <div class="grid mb-4">
      <div class="col-12 md:col-6 lg:col-3">
        <div class="stat-card surface-card shadow-1 p-3 border-round">
          <div class="flex justify-content-between mb-3">
            <div>
              <span class="block text-500 font-medium mb-3">Всего устройств</span>
              <div class="text-900 font-medium text-xl">{{ stats.totalDevices }}</div>
            </div>
            <div class="flex align-items-center justify-content-center bg-blue-100 border-round" style="width:2.5rem;height:2.5rem">
              <i class="pi pi-desktop text-blue-500 text-xl"></i>
            </div>
          </div>
          <span class="text-green-500 font-medium">{{ stats.activeDevices }} </span>
          <span class="text-500"> активны в сети</span>
        </div>
      </div>

      <div class="col-12 md:col-6 lg:col-3">
        <div class="stat-card surface-card shadow-1 p-3 border-round">
          <div class="flex justify-content-between mb-3">
            <div>
              <span class="block text-500 font-medium mb-3">Заявки</span>
              <div class="text-900 font-medium text-xl">{{ stats.openRequests }}</div>
            </div>
            <div class="flex align-items-center justify-content-center bg-orange-100 border-round" style="width:2.5rem;height:2.5rem">
              <i class="pi pi-inbox text-orange-500 text-xl"></i>
            </div>
          </div>
          <span class="text-500">Открытых обращений</span>
        </div>
      </div>

      <div class="col-12 md:col-6 lg:col-3">
        <div class="stat-card surface-card shadow-1 p-3 border-round">
          <div class="flex justify-content-between mb-3">
            <div>
              <span class="block text-500 font-medium mb-3">Критические ошибки</span>
              <div class="text-900 font-medium text-xl">{{ stats.criticalErrors }}</div>
            </div>
            <div class="flex align-items-center justify-content-center bg-red-100 border-round" style="width:2.5rem;height:2.5rem">
              <i class="pi pi-exclamation-triangle text-red-500 text-xl"></i>
            </div>
          </div>
          <span class="text-500">За последние 24 часа</span>
        </div>
      </div>

      <div class="col-12 md:col-6 lg:col-3">
        <div class="stat-card surface-card shadow-1 p-3 border-round">
          <div class="flex justify-content-between mb-3">
            <div>
              <span class="block text-500 font-medium mb-3">Загрузка сети</span>
              <div class="text-900 font-medium text-xl">{{ stats.avgNetworkLoad }}%</div>
            </div>
            <div class="flex align-items-center justify-content-center bg-purple-100 border-round" style="width:2.5rem;height:2.5rem">
              <i class="pi pi-chart-line text-purple-500 text-xl"></i>
            </div>
          </div>
          <span class="text-500">Средняя нагрузка</span>
        </div>
      </div>
    </div>

    <!-- Графики -->
    <div class="grid">
      <!-- Линейный график: Загрузка CPU/RAM -->
      <div class="col-12 lg:col-8">
        <div class="card shadow-1 border-round p-4 bg-white h-full">
          <div class="flex justify-content-between align-items-center mb-4">
             <h3 class="text-xl font-semibold m-0">Нагрузка серверов (Live)</h3>
             <!-- Можно добавить выпадающий список для выбора конкретного сервера -->
          </div>
          <Chart type="line" :data="lineChartData" :options="lineChartOptions" class="h-30rem" />
        </div>
      </div>

      <!-- Круговая диаграмма: Статусы устройств -->
      <div class="col-12 lg:col-4">
        <div class="card shadow-1 border-round p-4 bg-white h-full">
          <h3 class="text-xl font-semibold mb-4">Состояние парка техники</h3>
          <div class="flex justify-content-center">
             <Chart type="doughnut" :data="doughnutChartData" :options="doughnutChartOptions" class="w-full md:w-20rem" />
          </div>
          <div class="mt-4">
             <ul class="list-none p-0 m-0">
                <li class="flex justify-content-between mb-2 p-2 border-bottom-1 surface-border">
                   <span>В работе</span>
                   <span class="font-bold text-green-500">{{ stats.statusCounts.active }}</span>
                </li>
                <li class="flex justify-content-between mb-2 p-2 border-bottom-1 surface-border">
                   <span>В ремонте</span>
                   <span class="font-bold text-orange-500">{{ stats.statusCounts.in_repair }}</span>
                </li>
                <li class="flex justify-content-between p-2">
                   <span>Списано/Склад</span>
                   <span class="font-bold text-gray-500">{{ stats.statusCounts.other }}</span>
                </li>
             </ul>
          </div>
        </div>
      </div>
      
      <!-- Гистограмма: Печать (опционально) -->
      <div class="col-12 mt-4">
         <div class="card shadow-1 border-round p-4 bg-white">
            <h3 class="text-xl font-semibold mb-4">Расход печати (Топ принтеров)</h3>
            <Chart type="bar" :data="barChartData" :options="barChartOptions" class="h-20rem" />
         </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue';
import apiClient from '@/api';
import Chart from 'primevue/chart';
import Button from 'primevue/button';

// --- State ---
const loading = ref(false);
const pollingInterval = ref(null);

const stats = ref({
  totalDevices: 0,
  activeDevices: 0,
  openRequests: 0,
  criticalErrors: 0,
  avgNetworkLoad: 0,
  statusCounts: { active: 0, in_repair: 0, other: 0 }
});

// Данные для графиков
const lineChartData = ref(null);
const lineChartOptions = ref(null);
const doughnutChartData = ref(null);
const doughnutChartOptions = ref(null);
const barChartData = ref(null);
const barChartOptions = ref(null);

// --- Logic ---

// Генерация демо-данных (если API пустое)
const generateMockLineData = () => {
    const labels = ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '23:59'];
    return {
        labels,
        datasets: [
            {
                label: 'Server-Main CPU',
                data: [15, 20, 45, 80, 65, 30, 20],
                fill: true,
                borderColor: '#4F46E5',
                backgroundColor: 'rgba(79, 70, 229, 0.1)',
                tension: 0.4
            },
            {
                label: 'Network Switch Load',
                data: [28, 35, 40, 50, 45, 35, 30],
                fill: false,
                borderColor: '#10B981',
                tension: 0.4
            }
        ]
    };
};

// Инициализация настроек графиков (цвета, сетка)
const initChartOptions = () => {
    const documentStyle = getComputedStyle(document.documentElement);
    const textColor = documentStyle.getPropertyValue('--text-color');
    const textColorSecondary = documentStyle.getPropertyValue('--text-color-secondary');
    const surfaceBorder = documentStyle.getPropertyValue('--surface-border');

    // Line Chart Options
    lineChartOptions.value = {
        maintainAspectRatio: false,
        plugins: {
            legend: { labels: { color: textColor } }
        },
        scales: {
            x: {
                ticks: { color: textColorSecondary },
                grid: { color: surfaceBorder }
            },
            y: {
                ticks: { color: textColorSecondary },
                grid: { color: surfaceBorder }
            }
        }
    };

    // Doughnut Chart Options
    doughnutChartOptions.value = {
        cutout: '60%',
        plugins: {
            legend: { labels: { color: textColor } }
        }
    };
    
    // Bar Chart Options
    barChartOptions.value = {
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: textColor } } },
        scales: {
            x: { ticks: { color: textColorSecondary }, grid: { color: surfaceBorder, drawBorder: false } },
            y: { ticks: { color: textColorSecondary }, grid: { color: surfaceBorder, drawBorder: false } }
        }
    };
};

// Загрузка данных с API
const loadDashboardData = async () => {
    loading.value = true;
    try {
        // 1. Получаем устройства для статистики
        const devicesRes = await apiClient.get('devices/');
        const devices = devicesRes.data;
        
        // 2. Получаем метрики (если есть)
        // В будущем: const metricsRes = await apiClient.get('metrics/');
        
        // Расчет статистики
        stats.value.totalDevices = devices.length;
        stats.value.activeDevices = devices.filter(d => d.status === 'active').length;
        stats.value.statusCounts = {
            active: devices.filter(d => d.status === 'active').length,
            in_repair: devices.filter(d => d.status === 'in_repair').length,
            other: devices.filter(d => !['active', 'in_repair'].includes(d.status)).length
        };
        
        // Заглушки для данных, которых пока нет в БД
        stats.value.openRequests = Math.floor(Math.random() * 10); 
        stats.value.criticalErrors = Math.floor(Math.random() * 3);
        stats.value.avgNetworkLoad = Math.floor(Math.random() * 40) + 20;

        // Наполняем Круговую диаграмму реальными данными о статусах
        doughnutChartData.value = {
            labels: ['В работе', 'В ремонте', 'Прочее'],
            datasets: [
                {
                    data: [stats.value.statusCounts.active, stats.value.statusCounts.in_repair, stats.value.statusCounts.other],
                    backgroundColor: ['#22C55E', '#F97316', '#64748B'],
                    hoverBackgroundColor: ['#16A34A', '#EA580C', '#475569']
                }
            ]
        };

        // Наполняем линейный график (Пока Демо, потом заменить на реальные метрики)
        lineChartData.value = generateMockLineData();
        
        // Наполняем Bar Chart (Принтеры)
        barChartData.value = {
            labels: ['HP LaserJet P1', 'Canon MF3010', 'Kyocera EcoSys'],
            datasets: [
                {
                    label: 'Страниц за сегодня',
                    backgroundColor: '#3B82F6',
                    data: [65, 59, 80]
                }
            ]
        };

    } catch (e) {
        console.error("Ошибка обновления дашборда", e);
    } finally {
        loading.value = false;
    }
};

// Обновление данных
const refreshData = () => {
    loadDashboardData();
};

// --- Lifecycle ---
onMounted(() => {
    initChartOptions();
    loadDashboardData();
    
    // Автообновление каждые 60 секунд
    pollingInterval.value = setInterval(() => {
        loadDashboardData();
    }, 60000);
});

onBeforeUnmount(() => {
    if (pollingInterval.value) clearInterval(pollingInterval.value);
});
</script>

<style scoped>
/* PrimeFlex классы используются в template, 
   но добавим немного локальных стилей для специфики */
.stat-card {
    background-color: #ffffff;
    transition: transform 0.2s;
}
.stat-card:hover {
    transform: translateY(-3px);
}

/* Цвета для иконок */
.bg-blue-100 { background-color: #dbeafe; }
.text-blue-500 { color: #3b82f6; }
.bg-orange-100 { background-color: #ffedd5; }
.text-orange-500 { color: #f97316; }
.bg-red-100 { background-color: #fee2e2; }
.text-red-500 { color: #ef4444; }
.bg-purple-100 { background-color: #f3e8ff; }
.text-purple-500 { color: #a855f7; }

.grid {
    display: flex;
    flex-wrap: wrap;
    margin-right: -0.5rem;
    margin-left: -0.5rem;
}
.col-12 { box-sizing: border-box; flex: 0 0 100%; padding: 0.5rem; }

@media (min-width: 768px) {
    .md\:col-6 { flex: 0 0 50%; max-width: 50%; }
}
@media (min-width: 992px) {
    .lg\:col-3 { flex: 0 0 25%; max-width: 25%; }
    .lg\:col-8 { flex: 0 0 66.6666%; max-width: 66.6666%; }
    .lg\:col-4 { flex: 0 0 33.3333%; max-width: 33.3333%; }
}
</style>