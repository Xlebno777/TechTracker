import { computed, ref } from 'vue';
import apiClient from '@/api';

const SUMMARY_TTL_MS = 30_000;

const summary = ref(null);
const details = ref(null);
const loadingSummary = ref(false);
const loadingDetails = ref(false);
const error = ref('');
const lastSummaryAt = ref(0);
let summaryPromise = null;
let detailsPromise = null;

function normalizeStatus(value) {
  const status = String(value || '').toLowerCase();
  if (['ok', 'warning', 'critical'].includes(status)) return status;
  return 'unknown';
}

async function loadSystemSummary({ force = false, includeLstm = true } = {}) {
  const now = Date.now();
  if (!force && summary.value && now - lastSummaryAt.value < SUMMARY_TTL_MS) {
    return summary.value;
  }
  if (summaryPromise) return summaryPromise;
  loadingSummary.value = true;
  error.value = '';
  summaryPromise = apiClient
    .get(`system-health/summary/?lstm=${includeLstm ? '1' : '0'}`)
    .then((res) => {
      summary.value = res.data || null;
      lastSummaryAt.value = Date.now();
      return summary.value;
    })
    .catch((err) => {
      error.value = err?.response?.data?.detail || err?.message || 'Не удалось получить состояние системы';
      throw err;
    })
    .finally(() => {
      loadingSummary.value = false;
      summaryPromise = null;
    });
  return summaryPromise;
}

async function loadSystemDetails({ includeLstm = true } = {}) {
  if (detailsPromise) return detailsPromise;
  loadingDetails.value = true;
  error.value = '';
  detailsPromise = apiClient
    .get(`system-health/details/?lstm=${includeLstm ? '1' : '0'}`)
    .then((res) => {
      details.value = res.data || null;
      summary.value = res.data || summary.value;
      lastSummaryAt.value = Date.now();
      return details.value;
    })
    .catch((err) => {
      error.value = err?.response?.data?.detail || err?.message || 'Не удалось получить детали состояния системы';
      throw err;
    })
    .finally(() => {
      loadingDetails.value = false;
      detailsPromise = null;
    });
  return detailsPromise;
}

const status = computed(() => normalizeStatus(summary.value?.status || details.value?.status));
const statusLabel = computed(() => {
  if (status.value === 'ok') return 'Норма';
  if (status.value === 'warning') return 'Внимание';
  if (status.value === 'critical') return 'Критично';
  return 'Нет данных';
});
const topWarnings = computed(() => {
  const rows = Array.isArray(summary.value?.warnings) ? summary.value.warnings : [];
  return rows.slice(0, 3);
});

export function useSystemHealth() {
  return {
    summary,
    details,
    loadingSummary,
    loadingDetails,
    error,
    status,
    statusLabel,
    topWarnings,
    loadSystemSummary,
    loadSystemDetails,
  };
}
