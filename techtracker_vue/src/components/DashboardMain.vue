<template>
  <div class="dashboard p-4 page-shell">
    <Toast />
    <div class="flex flex-wrap justify-content-between align-items-start gap-3 mb-4">
      <div>
        <h2 class="text-2xl font-bold m-0 text-900">Дашборд вычисляемых метрик</h2>
        <p class="text-500 m-0">Агрегации уровня 2, пересчёт по расписанию (раз в час)</p>
      </div>
      <div class="flex flex-column align-items-end gap-2">
        <span class="text-500 text-sm">Обновлено: {{ lastMetricLabel }}</span>
        <Button icon="pi pi-refresh" label="Обновить" rounded text @click="refreshData" :loading="loading" />
      </div>
    </div>

    <div v-if="hasAgentError" class="card p-3 border-round warning-banner mb-3">
      <div class="text-red-600 font-semibold mb-1">Ошибка отправки метрик</div>
      <div class="text-600 text-sm">
        {{ agentError?.message || 'Не удалось отправить метрики. Проверьте работу службы агента.' }}
      </div>
      <div class="text-500 text-xs mt-1">
        Последнее обновление: {{ formatAgentTime(agentError?.updated_at) }}
      </div>
    </div>

    <div v-if="!hasData && !loading" class="card p-4 border-round empty-state">
      <div class="text-900 text-lg font-semibold mb-2">Нет вычисленных метрик</div>
      <div class="text-500">Запусти команду на сервере: <b>python manage.py compute_derived_metrics</b></div>
    </div>

    <!-- Сводные карточки -->
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
      <!-- Тренды -->
      <div class="col-12 lg:col-6">
        <div class="card p-4 border-round shadow-1 h-full">
          <div class="flex justify-content-between align-items-center mb-3">
            <h3 class="text-xl font-semibold m-0">Тренды</h3>
            <span class="text-500 text-sm">окно 24ч / 7д</span>
          </div>
          <div class="metric-list">
            <div v-for="item in trendItems" :key="item.key" class="metric-row">
              <div>
                <div class="text-900 font-medium">{{ item.label }}</div>
                <div class="text-500 text-sm">{{ item.hint }}</div>
              </div>
              <div class="metric-row-value" :class="item.toneClass">{{ item.value }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Стабильность -->
      <div class="col-12 lg:col-6">
        <div class="card p-4 border-round shadow-1 h-full">
          <div class="flex justify-content-between align-items-center mb-3">
            <h3 class="text-xl font-semibold m-0">Стабильность</h3>
            <span class="text-500 text-sm">пики и вариативность</span>
          </div>
          <div class="metric-list">
            <div v-for="item in stabilityItems" :key="item.key" class="metric-row">
              <div>
                <div class="text-900 font-medium">{{ item.label }}</div>
                <div class="text-500 text-sm">{{ item.hint }}</div>
              </div>
              <div class="metric-row-value" :class="item.toneClass">{{ item.value }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- RAID / Диски -->
      <div class="col-12 mt-3">
        <div class="card p-4 border-round shadow-1">
          <div class="flex justify-content-between align-items-center mb-3">
            <div>
              <h3 class="text-xl font-semibold m-0">StorCLI: состояние дисков</h3>
              <p class="text-500 m-0">Предиктивные отказы, перегревы и ошибки за 24 часа</p>
            </div>
          </div>
          <div class="table-wrap">
            <table class="metric-table">
              <thead>
                <tr>
                  <th>Диск</th>
                  <th>Модель</th>
                  <th>Серийный</th>
                  <th>Ошибки 24ч</th>
                  <th>Pred Fail 24ч</th>
                  <th>Перегрев 24ч</th>
                  <th>SMART Alert</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in diskRows" :key="row.drive">
                  <td>{{ row.drive }}</td>
                  <td>{{ row.model || '—' }}</td>
                  <td>{{ row.serial || '—' }}</td>
                  <td :class="row.errorDelta > 0 ? 'text-red-500' : 'text-500'">{{ formatCount(row.errorDelta) }}</td>
                  <td :class="row.predFailDelta > 0 ? 'text-red-500' : 'text-500'">{{ formatCount(row.predFailDelta) }}</td>
                  <td :class="row.overheatRatio > 0 ? 'text-orange-500' : 'text-500'">{{ formatPercent(row.overheatRatio) }}</td>
                  <td :class="row.smartAlert > 0 ? 'text-red-500' : 'text-500'">{{ row.smartAlert > 0 ? 'ALERT' : 'OK' }}</td>
                </tr>
                <tr v-if="diskRows.length === 0">
                  <td colspan="7" class="text-500">Нет данных по дискам.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Виртуальные машины -->
      <div class="col-12 mt-3">
        <div class="card p-4 border-round shadow-1">
          <div class="flex justify-content-between align-items-center mb-3">
            <div>
              <h3 class="text-xl font-semibold m-0">Hyper-V: доступность ВМ</h3>
              <p class="text-500 m-0">Доля времени в работе + пиковые нагрузки за 24ч</p>
            </div>
          </div>
          <div class="table-wrap">
            <table class="metric-table">
              <thead>
                <tr>
                  <th>ВМ</th>
                  <th>Доступность 24ч</th>
                  <th>CPU peak 24ч</th>
                  <th>RAM peak 24ч</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in vmRows" :key="row.vm">
                  <td>{{ row.vm }}</td>
                  <td :class="row.availability < 0.95 ? 'text-red-500' : 'text-green-500'">{{ formatPercent(row.availability) }}</td>
                  <td>{{ formatNumber(row.cpuPeak, '%') }}</td>
                  <td>{{ formatNumber(row.memPeak, '%') }}</td>
                </tr>
                <tr v-if="vmRows.length === 0">
                  <td colspan="4" class="text-500">Нет данных по ВМ.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';

const toast = useToast();
const loading = ref(false);
const metrics = ref([]);
const lastUpdated = ref(null);
const pollingInterval = ref(null);
const agentError = ref(null);

const AUTO_REFRESH_MS = 60 * 60 * 1000;

const lastMetricLabel = computed(() => {
  if (!lastUpdated.value) return '—';
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'short',
    timeStyle: 'short'
  }).format(lastUpdated.value);
});

const hasData = computed(() => metrics.value.length > 0);
const hasAgentError = computed(() => !!agentError.value);

const normalizeLabelKey = (labels) => {
  if (!labels) return '';
  return Object.keys(labels)
    .sort()
    .map((key) => `${key}:${labels[key]}`)
    .join('|');
};

const metricsSorted = computed(() => {
  const copy = [...metrics.value];
  copy.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  return copy;
});

const latestMetricsMap = computed(() => {
  const map = new Map();
  for (const item of metricsSorted.value) {
    const key = `${item.code}|${item.window || ''}|${normalizeLabelKey(item.labels)}`;
    if (!map.has(key)) {
      map.set(key, item);
    }
  }
  return map;
});

const listByCode = (code, window = null) => {
  return Array.from(latestMetricsMap.value.values()).filter((item) => {
    if (item.code !== code) return false;
    if (window && item.window !== window) return false;
    return true;
  });
};

const getSingleValue = (code, window = null) => {
  const item = listByCode(code, window)[0];
  return item ? Number(item.value) : null;
};

const formatSigned = (value, unit = '') => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}${unit ? ` ${unit}` : ''}`;
};

const formatNumber = (value, unit = '') => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toFixed(1)}${unit ? ` ${unit}` : ''}`;
};

const formatCount = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return Math.round(value).toString();
};

const formatPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(1)}%`;
};

const formatAgentTime = (value) => {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      dateStyle: 'short',
      timeStyle: 'short'
    }).format(new Date(value));
  } catch (e) {
    return value;
  }
};

const summaryCards = computed(() => {
  const cpuTrend = getSingleValue('cpu_trend_24h', '24h');
  const memTrend = getSingleValue('mem_trend_24h', '24h');
  const diskRates = listByCode('disk_fill_rate_7d', '7d').map((m) => Number(m.value));
  const diskMax = diskRates.length ? Math.max(...diskRates) : null;
  const resets = getSingleValue('uptime_reset_count_7d', '7d');

  return [
    {
      key: 'cpu',
      title: 'CPU тренд (24ч)',
      value: formatSigned(cpuTrend, '%/h'),
      badge: cpuTrend && cpuTrend > 0 ? 'рост' : 'стабильный',
      toneClass: cpuTrend && cpuTrend > 0 ? 'pill-warn' : 'pill-ok',
      subtitle: 'Наклон нагрузки процессора'
    },
    {
      key: 'mem',
      title: 'RAM тренд (24ч)',
      value: formatSigned(memTrend, '%/h'),
      badge: memTrend && memTrend > 0 ? 'рост' : 'стабильный',
      toneClass: memTrend && memTrend > 0 ? 'pill-warn' : 'pill-ok',
      subtitle: 'Рост потребления памяти'
    },
    {
      key: 'disk',
      title: 'Заполнение дисков',
      value: formatSigned(diskMax, '%/day'),
      badge: diskMax && diskMax > 1 ? 'быстро' : 'норма',
      toneClass: diskMax && diskMax > 1 ? 'pill-warn' : 'pill-ok',
      subtitle: 'Макс. скорость заполнения'
    },
    {
      key: 'uptime',
      title: 'Перезагрузки (7д)',
      value: formatCount(resets),
      badge: resets && resets > 0 ? 'нестабильно' : 'ok',
      toneClass: resets && resets > 0 ? 'pill-danger' : 'pill-ok',
      subtitle: 'Число падений uptime'
    }
  ];
});

const trendItems = computed(() => {
  const netTrend = getSingleValue('net_traffic_trend_24h', '24h');
  const diskRates = listByCode('disk_fill_rate_7d', '7d').map((m) => Number(m.value));
  const diskAvg = diskRates.length ? (diskRates.reduce((a, b) => a + b, 0) / diskRates.length) : null;

  return [
    {
      key: 'cpu',
      label: 'Тренд CPU (24ч)',
      value: formatSigned(getSingleValue('cpu_trend_24h', '24h'), '%/h'),
      hint: 'Рост или спад нагрузки',
      toneClass: (getSingleValue('cpu_trend_24h', '24h') || 0) > 0 ? 'text-red-500' : 'text-green-500'
    },
    {
      key: 'mem',
      label: 'Тренд RAM (24ч)',
      value: formatSigned(getSingleValue('mem_trend_24h', '24h'), '%/h'),
      hint: 'Подозрения на утечки',
      toneClass: (getSingleValue('mem_trend_24h', '24h') || 0) > 0 ? 'text-orange-500' : 'text-green-500'
    },
    {
      key: 'disk',
      label: 'Заполнение дисков (avg 7д)',
      value: formatSigned(diskAvg, '%/day'),
      hint: 'Средняя скорость роста занятости',
      toneClass: diskAvg && diskAvg > 1 ? 'text-red-500' : 'text-500'
    },
    {
      key: 'net',
      label: 'Тренд сети (24ч)',
      value: formatSigned(netTrend, 'KB/s/h'),
      hint: 'Рост/падение трафика',
      toneClass: netTrend && netTrend > 0 ? 'text-blue-500' : 'text-500'
    }
  ];
});

const stabilityItems = computed(() => {
  const memLeak = getSingleValue('mem_leak_prob', '24h');
  return [
    {
      key: 'cpuSpike',
      label: 'Пики CPU (1ч)',
      value: formatCount(getSingleValue('cpu_spike_count_1h', '1h')),
      hint: 'Количество всплесков > 90%',
      toneClass: (getSingleValue('cpu_spike_count_1h', '1h') || 0) > 5 ? 'text-red-500' : 'text-500'
    },
    {
      key: 'pingSpike',
      label: 'Пики ping (1ч)',
      value: formatCount(getSingleValue('ping_spike_count_1h', '1h')),
      hint: 'Пики выше 95‑го перцентиля',
      toneClass: (getSingleValue('ping_spike_count_1h', '1h') || 0) > 5 ? 'text-red-500' : 'text-500'
    },
    {
      key: 'pingJitter',
      label: 'Jitter ping (1ч)',
      value: formatNumber(getSingleValue('ping_jitter_1h', '1h'), 'ms'),
      hint: 'Стабильность канала',
      toneClass: (getSingleValue('ping_jitter_1h', '1h') || 0) > 20 ? 'text-orange-500' : 'text-500'
    },
    {
      key: 'tempVar',
      label: 'Вариативность температуры (24ч)',
      value: formatNumber(getSingleValue('temp_variance_24h', '24h'), 'C²'),
      hint: 'Скачки температуры',
      toneClass: (getSingleValue('temp_variance_24h', '24h') || 0) > 25 ? 'text-orange-500' : 'text-500'
    },
    {
      key: 'swap',
      label: 'Swap активен (24ч)',
      value: formatPercent(getSingleValue('swap_active_ratio_24h', '24h')),
      hint: 'Доля времени использования swap',
      toneClass: (getSingleValue('swap_active_ratio_24h', '24h') || 0) > 0.1 ? 'text-red-500' : 'text-500'
    },
    {
      key: 'leak',
      label: 'Риск утечки памяти',
      value: memLeak && memLeak > 0 ? 'Высокий' : 'Нет признаков',
      hint: 'Корреляция uptime и RAM',
      toneClass: memLeak && memLeak > 0 ? 'text-red-500' : 'text-green-500'
    }
  ];
});

const diskRows = computed(() => {
  const rows = new Map();
  const feed = (code, window, field) => {
    listByCode(code, window).forEach((metric) => {
      const drive = metric.labels?.drive || 'unknown';
      const row = rows.get(drive) || {
        drive,
        model: metric.labels?.model,
        serial: metric.labels?.serial,
        errorDelta: 0,
        predFailDelta: 0,
        overheatRatio: 0,
        smartAlert: 0
      };
      row[field] = Number(metric.value);
      rows.set(drive, row);
    });
  };

  feed('storcli_error_delta_24h', '24h', 'errorDelta');
  feed('storcli_pred_fail_delta_24h', '24h', 'predFailDelta');
  feed('storcli_overheat_ratio_24h', '24h', 'overheatRatio');
  feed('storcli_smart_alert_active', '24h', 'smartAlert');

  return Array.from(rows.values()).sort((a, b) => a.drive.localeCompare(b.drive));
});

const vmRows = computed(() => {
  const rows = new Map();
  const feed = (code, window, field) => {
    listByCode(code, window).forEach((metric) => {
      const name = metric.labels?.vm || 'unknown';
      const row = rows.get(name) || { vm: name, availability: null, cpuPeak: null, memPeak: null };
      row[field] = Number(metric.value);
      rows.set(name, row);
    });
  };

  feed('vm_availability_24h', '24h', 'availability');
  feed('vm_cpu_peak_24h', '24h', 'cpuPeak');
  feed('vm_mem_peak_24h', '24h', 'memPeak');

  return Array.from(rows.values()).sort((a, b) => a.vm.localeCompare(b.vm));
});

const loadDashboardData = async (silent = false) => {
  if (!silent) {
    loading.value = true;
  }
  try {
    const res = await apiClient.get('metrics-computed/?ordering=-timestamp');
    const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
    metrics.value = data;
    if (data.length > 0) {
      const maxTs = data.reduce((acc, item) => {
        const ts = new Date(item.timestamp).getTime();
        return ts > acc ? ts : acc;
      }, 0);
      lastUpdated.value = maxTs ? new Date(maxTs) : new Date();
    } else {
      lastUpdated.value = new Date();
    }
    const statusRes = await apiClient.get('agent-status/?status=error&ordering=-updated_at');
    const statusData = Array.isArray(statusRes.data) ? statusRes.data : (statusRes.data?.results || []);
    agentError.value = statusData.length ? statusData[0] : null;
  } catch (e) {
    console.error('Ошибка обновления дашборда', e);
  } finally {
    if (!silent) {
      loading.value = false;
    }
  }
};

const refreshData = async () => {
  loading.value = true;
  try {
    await apiClient.post('metrics-computed/recompute/');
    await loadDashboardData(true);
    toast.add({ severity: 'success', summary: 'Обновлено', detail: 'Метрики пересчитаны', life: 3000 });
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось пересчитать метрики';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  loadDashboardData();
  pollingInterval.value = setInterval(() => {
    loadDashboardData(true);
  }, AUTO_REFRESH_MS);
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
.metric-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #eef1f5;
  padding-bottom: 0.75rem;
}
.metric-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.metric-row-value {
  font-weight: 600;
}
.table-wrap {
  overflow-x: auto;
}
.metric-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 720px;
}
.metric-table th,
.metric-table td {
  text-align: left;
  padding: 0.75rem 0.5rem;
  border-bottom: 1px solid #eef1f5;
  font-size: 0.95rem;
}
.metric-table th {
  color: #6b7280;
  font-weight: 600;
}
.empty-state {
  background: #f8fafc;
  border: 1px dashed #cbd5f5;
}
.warning-banner {
  background: #fff1f2;
  border: 1px solid #fecdd3;
}
</style>
