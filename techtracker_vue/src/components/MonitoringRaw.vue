<template>
  <div class="dashboard p-4 page-shell">
    <Toast />
    <div class="flex flex-wrap justify-content-between align-items-start gap-3 mb-4">
      <div>
        <h2 class="text-2xl font-bold m-0 text-900">Мониторинг (сырьевые метрики)</h2>
        <p class="text-500 m-0">Обновление в реальном времени (раз в минуту)</p>
      </div>
      <div class="flex flex-column align-items-end gap-2">
        <span class="text-500 text-sm">Обновлено: {{ lastMetricLabel }}</span>
        <div class="flex align-items-center gap-2">
          <Dropdown v-model="selectedStep" :options="stepOptions" optionLabel="label" class="step-select" />
          <Button icon="pi pi-refresh" label="Обновить" rounded text @click="refreshData" :loading="loading" />
        </div>
      </div>
    </div>

    <div class="grid mb-4">
      <div class="col-12 md:col-6 lg:col-3" v-for="card in summaryCards" :key="card.key">
        <div class="metric-card surface-card border-round shadow-1 p-3">
          <div class="flex justify-content-between align-items-start">
            <div>
              <span class="text-500 text-sm font-medium">{{ card.title }}</span>
              <div class="metric-value text-900 mt-2">{{ card.value }}</div>
            </div>
            <span class="metric-pill" :class="card.toneClass">{{ card.badge }}</span>
          </div>
          <div class="text-500 text-sm mt-3">{{ card.subtitle }}</div>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="col-12 lg:col-6">
        <div class="card p-4 border-round shadow-1 h-full">
          <div class="flex justify-content-between align-items-center mb-3">
            <h3 class="text-xl font-semibold m-0">CPU (последние 60 минут)</h3>
            <span class="text-500 text-sm">%</span>
          </div>
          <Chart type="line" :data="charts.cpu.data" :options="charts.cpu.options" class="h-20rem" />
        </div>
      </div>

      <div class="col-12 lg:col-6">
        <div class="card p-4 border-round shadow-1 h-full">
          <div class="flex justify-content-between align-items-center mb-3">
            <h3 class="text-xl font-semibold m-0">RAM (последние 60 минут)</h3>
            <span class="text-500 text-sm">%</span>
          </div>
          <Chart type="line" :data="charts.mem.data" :options="charts.mem.options" class="h-20rem" />
        </div>
      </div>

      <div class="col-12 lg:col-6 mt-3">
        <div class="card p-4 border-round shadow-1 h-full">
          <div class="flex justify-content-between align-items-center mb-3">
            <h3 class="text-xl font-semibold m-0">Сеть (KB/s)</h3>
            <span class="text-500 text-sm">Tx / Rx</span>
          </div>
          <Chart type="line" :data="charts.net.data" :options="charts.net.options" class="h-20rem" />
        </div>
      </div>

      <div class="col-12 lg:col-6 mt-3">
        <div class="card p-4 border-round shadow-1 h-full">
          <div class="flex justify-content-between align-items-center mb-3">
            <h3 class="text-xl font-semibold m-0">Ping (ms)</h3>
          </div>
          <Chart type="line" :data="charts.ping.data" :options="charts.ping.options" class="h-20rem" />
        </div>
      </div>

      <div class="col-12 mt-3">
        <div class="card p-4 border-round shadow-1">
          <div class="flex justify-content-between align-items-center mb-3">
            <h3 class="text-xl font-semibold m-0">Диски — занятость</h3>
            <span class="text-500 text-sm">Последние значения</span>
          </div>
          <Chart type="bar" :data="charts.disk.data" :options="charts.disk.options" class="h-18rem" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Chart from 'primevue/chart';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';
import Dropdown from 'primevue/dropdown';

const toast = useToast();
const loading = ref(false);
const pollingInterval = ref(null);
const lastUpdated = ref(null);

const AUTO_REFRESH_MS = 60 * 1000;
const SERIES_LIMIT = 5000;

const stepOptions = [
  { label: 'Минута', stepMinutes: 1, rangeMinutes: 120 },
  { label: 'Час', stepMinutes: 60, rangeMinutes: 24 * 60 },
  { label: 'День', stepMinutes: 1440, rangeMinutes: 30 * 24 * 60 },
  { label: 'Неделя', stepMinutes: 10080, rangeMinutes: 180 * 24 * 60 },
  { label: 'Месяц', stepMinutes: 43200, rangeMinutes: 365 * 24 * 60 }
];
const selectedStep = ref(stepOptions[2]);

const charts = ref({
  cpu: { data: null, options: null },
  mem: { data: null, options: null },
  net: { data: null, options: null },
  ping: { data: null, options: null },
  disk: { data: null, options: null }
});

const lastMetricLabel = computed(() => {
  if (!lastUpdated.value) return '—';
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'short',
    timeStyle: 'short'
  }).format(lastUpdated.value);
});

const latestValues = ref({
  cpu: null,
  mem: null,
  ping: null,
  netRecv: null
});

const summaryCards = computed(() => {
  const cpuVal = latestValues.value.cpu;
  const memVal = latestValues.value.mem;
  const pingVal = latestValues.value.ping;
  const netVal = latestValues.value.netRecv;

  return [
    {
      key: 'cpu',
      title: 'CPU сейчас',
      value: formatNumber(cpuVal, '%'),
      badge: cpuVal && cpuVal > 85 ? 'пик' : 'норма',
      toneClass: cpuVal && cpuVal > 85 ? 'pill-danger' : 'pill-ok',
      subtitle: 'Загрузка процессора'
    },
    {
      key: 'mem',
      title: 'RAM сейчас',
      value: formatNumber(memVal, '%'),
      badge: memVal && memVal > 85 ? 'пик' : 'норма',
      toneClass: memVal && memVal > 85 ? 'pill-danger' : 'pill-ok',
      subtitle: 'Использование памяти'
    },
    {
      key: 'ping',
      title: 'Ping сейчас',
      value: formatNumber(pingVal, 'ms'),
      badge: pingVal && pingVal > 80 ? 'плохо' : 'ok',
      toneClass: pingVal && pingVal > 80 ? 'pill-warn' : 'pill-ok',
      subtitle: 'Задержка до шлюза'
    },
    {
      key: 'net',
      title: 'Rx сейчас',
      value: formatNumber(netVal, 'KB/s'),
      badge: 'live',
      toneClass: 'pill-ok',
      subtitle: 'Входящий трафик'
    }
  ];
});

const rawSeries = ref({
  cpu: [],
  mem: [],
  ping: [],
  netSent: [],
  netRecv: [],
  disk: []
});

const formatNumber = (value, unit = '') => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toFixed(1)}${unit ? ` ${unit}` : ''}`;
};

const formatTime = (timestamp) => {
  const date = new Date(timestamp);
  return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
};

const initChartOptions = () => {
  const textColor = '#334155';
  const textColorSecondary = '#94a3b8';
  const surfaceBorder = '#e2e8f0';

  const base = {
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: textColor } } },
    scales: {
      x: { ticks: { color: textColorSecondary }, grid: { color: surfaceBorder } },
      y: { ticks: { color: textColorSecondary }, grid: { color: surfaceBorder } }
    }
  };

  charts.value.cpu.options = { ...base };
  charts.value.mem.options = { ...base };
  charts.value.net.options = { ...base };
  charts.value.ping.options = { ...base };
  charts.value.disk.options = {
    maintainAspectRatio: false,
    plugins: { legend: { labels: { color: textColor } } },
    scales: {
      x: { ticks: { color: textColorSecondary }, grid: { color: surfaceBorder } },
      y: { ticks: { color: textColorSecondary }, grid: { color: surfaceBorder } }
    }
  };
};

const fetchSeries = async (code, rangeMinutes, limit = SERIES_LIMIT) => {
  const rangeParam = rangeMinutes ? `&since_minutes=${rangeMinutes}` : '';
  const res = await apiClient.get(`metrics-raw/?code=${code}&ordering=-timestamp&limit=${limit}${rangeParam}`);
  const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
  const sorted = data.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  return sorted.map(item => ({
    time: item.timestamp,
    value: Number(item.value),
    labels: item.labels || {}
  }));
};

const fetchLastPoint = async (code) => {
  const res = await apiClient.get(`metrics-raw/?code=${code}&ordering=-timestamp&limit=1`);
  const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
  if (!data.length) return [];
  return [{
    time: data[0].timestamp,
    value: Number(data[0].value),
    labels: data[0].labels || {}
  }];
};

const fetchDiskLatest = async () => {
  const res = await apiClient.get('metrics-raw/?code=disk_usage_percent&ordering=-timestamp&limit=200');
  const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
  const latest = new Map();
  data.forEach(item => {
    const disk = item.labels?.disk || 'disk';
    if (!latest.has(disk)) {
      latest.set(disk, item);
    }
  });
  return Array.from(latest.entries()).map(([disk, item]) => ({
    disk,
    value: Number(item.value),
    time: item.timestamp
  })).sort((a, b) => a.disk.localeCompare(b.disk));
};

const bucketSeries = (series, stepMinutes) => {
  if (!stepMinutes || stepMinutes <= 1) return series;
  const stepMs = stepMinutes * 60 * 1000;
  const buckets = new Map();
  for (const point of series) {
    const ts = new Date(point.time).getTime();
    if (!Number.isFinite(ts)) continue;
    const bucket = Math.floor(ts / stepMs) * stepMs;
    const current = buckets.get(bucket) || { sum: 0, count: 0 };
    current.sum += point.value;
    current.count += 1;
    buckets.set(bucket, current);
  }
  return Array.from(buckets.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([bucket, info]) => ({
      time: new Date(bucket).toISOString(),
      value: info.count ? info.sum / info.count : 0
    }));
};

const rebuildCharts = () => {
  const step = selectedStep.value.stepMinutes;
  const cpuSeries = bucketSeries(rawSeries.value.cpu, step);
  const memSeries = bucketSeries(rawSeries.value.mem, step);
  const pingSeries = bucketSeries(rawSeries.value.ping, step);
  const netRecvSeries = bucketSeries(rawSeries.value.netRecv, step);
  const netSentSeries = bucketSeries(rawSeries.value.netSent, step);

  charts.value.cpu.data = {
    labels: cpuSeries.map(p => formatTime(p.time)),
    datasets: [{
      label: 'CPU %',
      data: cpuSeries.map(p => p.value),
      borderColor: '#2563eb',
      backgroundColor: 'rgba(37, 99, 235, 0.12)',
      fill: true,
      tension: 0.35
    }]
  };

  charts.value.mem.data = {
    labels: memSeries.map(p => formatTime(p.time)),
    datasets: [{
      label: 'RAM %',
      data: memSeries.map(p => p.value),
      borderColor: '#10b981',
      backgroundColor: 'rgba(16, 185, 129, 0.12)',
      fill: true,
      tension: 0.35
    }]
  };

  charts.value.net.data = {
    labels: netRecvSeries.map(p => formatTime(p.time)),
    datasets: [
      {
        label: 'Rx KB/s',
        data: netRecvSeries.map(p => p.value),
        borderColor: '#0ea5e9',
        backgroundColor: 'rgba(14, 165, 233, 0.15)',
        fill: true,
        tension: 0.35
      },
      {
        label: 'Tx KB/s',
        data: netSentSeries.map(p => p.value),
        borderColor: '#f97316',
        backgroundColor: 'rgba(249, 115, 22, 0.15)',
        fill: true,
        tension: 0.35
      }
    ]
  };

  charts.value.ping.data = {
    labels: pingSeries.map(p => formatTime(p.time)),
    datasets: [{
      label: 'Ping ms',
      data: pingSeries.map(p => p.value),
      borderColor: '#f43f5e',
      backgroundColor: 'rgba(244, 63, 94, 0.12)',
      fill: true,
      tension: 0.35
    }]
  };

  charts.value.disk.data = {
    labels: rawSeries.value.disk.map(p => p.disk),
    datasets: [{
      label: 'Занятость %',
      data: rawSeries.value.disk.map(p => p.value),
      backgroundColor: '#6366f1'
    }]
  };
};

const loadDashboardData = async (silent = false) => {
  if (!silent) loading.value = true;
  try {
    const rangeMinutes = selectedStep.value.rangeMinutes;
    const [cpu, mem, ping, netSent, netRecv, disk] = await Promise.all([
      fetchSeries('cpu_load_total', rangeMinutes),
      fetchSeries('mem_usage_percent', rangeMinutes),
      fetchSeries('ping_latency_gateway', rangeMinutes),
      fetchSeries('net_bytes_sent', rangeMinutes),
      fetchSeries('net_bytes_recv', rangeMinutes),
      fetchDiskLatest()
    ]);

    const cpuSafe = cpu.length ? cpu : await fetchLastPoint('cpu_load_total');
    const memSafe = mem.length ? mem : await fetchLastPoint('mem_usage_percent');
    const pingSafe = ping.length ? ping : await fetchLastPoint('ping_latency_gateway');
    const netSentSafe = netSent.length ? netSent : await fetchLastPoint('net_bytes_sent');
    const netRecvSafe = netRecv.length ? netRecv : await fetchLastPoint('net_bytes_recv');

    rawSeries.value.cpu = cpuSafe;
    rawSeries.value.mem = memSafe;
    rawSeries.value.ping = pingSafe;
    rawSeries.value.netSent = netSentSafe;
    rawSeries.value.netRecv = netRecvSafe;
    rawSeries.value.disk = disk;

    latestValues.value.cpu = cpuSafe.length ? cpuSafe[cpuSafe.length - 1].value : null;
    latestValues.value.mem = memSafe.length ? memSafe[memSafe.length - 1].value : null;
    latestValues.value.ping = pingSafe.length ? pingSafe[pingSafe.length - 1].value : null;
    latestValues.value.netRecv = netRecvSafe.length ? netRecvSafe[netRecvSafe.length - 1].value : null;

    const latestTs = [cpuSafe, memSafe, pingSafe, netSentSafe, netRecvSafe]
      .flat()
      .reduce((acc, item) => {
        const ts = new Date(item.time).getTime();
        return ts > acc ? ts : acc;
      }, 0);
    const diskTs = rawSeries.value.disk.reduce((acc, item) => {
      const ts = item.time ? new Date(item.time).getTime() : 0;
      return ts > acc ? ts : acc;
    }, 0);
    const combinedTs = Math.max(latestTs || 0, diskTs || 0);
    lastUpdated.value = combinedTs ? new Date(combinedTs) : null;

    rebuildCharts();
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось обновить мониторинг';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  } finally {
    if (!silent) loading.value = false;
  }
};

const refreshData = () => {
  loadDashboardData();
};

onMounted(() => {
  initChartOptions();
  loadDashboardData();
  pollingInterval.value = setInterval(() => {
    loadDashboardData(true);
  }, AUTO_REFRESH_MS);
});

watch(selectedStep, () => {
  loadDashboardData();
});

onBeforeUnmount(() => {
  if (pollingInterval.value) clearInterval(pollingInterval.value);
});
</script>

<style scoped>
.metric-card {
  min-height: 130px;
}
.metric-value {
  font-size: 1.6rem;
  font-weight: 600;
}
.metric-pill {
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.pill-ok {
  background: #dcfce7;
  color: #15803d;
}
.pill-warn {
  background: #ffedd5;
  color: #c2410c;
}
.pill-danger {
  background: #fee2e2;
  color: #b91c1c;
}
.step-select {
  min-width: 12rem;
}
</style>
