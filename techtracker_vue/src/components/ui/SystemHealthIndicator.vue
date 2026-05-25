<template>
  <button
    v-if="visible"
    type="button"
    class="system-health-indicator"
    :class="`system-health-indicator--${status}`"
    :title="tooltipText"
    @click="goToHealthPage"
  >
    <span class="status-dot" />
    <span class="status-text">Система: {{ statusLabel }}</span>
    <i v-if="loadingSummary" class="pi pi-spin pi-spinner" />
  </button>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useSystemHealth } from '@/composables/useSystemHealth';

const router = useRouter();
const auth = useAuthStore();
const { loadingSummary, status, statusLabel, topWarnings, loadSystemSummary } = useSystemHealth();
let timer = null;

const visible = computed(() => auth.isAuthenticated && auth.canRoute('SystemHealth'));
const tooltipText = computed(() => {
  if (!topWarnings.value.length) return 'Состояние системы: критичных предупреждений нет';
  return topWarnings.value.map((item) => item.message).join('\n');
});

function refreshSilently(force = false) {
  if (!visible.value) return;
  loadSystemSummary({ force }).catch(() => {});
}

function goToHealthPage() {
  router.push({ name: 'SystemHealth' });
}

onMounted(() => {
  refreshSilently(false);
  timer = setInterval(() => refreshSilently(true), 60_000);
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

<style scoped>
.system-health-indicator {
  min-height: 2.15rem;
  border: 1px solid #dbe6f1;
  border-radius: 999px;
  padding: 0.25rem 0.7rem;
  background: #ffffff;
  color: #475569;
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font: inherit;
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.system-health-indicator:hover {
  border-color: #94a3b8;
  background: #f8fafc;
}

.status-dot {
  width: 0.58rem;
  height: 0.58rem;
  border-radius: 999px;
  background: #94a3b8;
  box-shadow: 0 0 0 3px rgba(148, 163, 184, 0.15);
}

.system-health-indicator--ok .status-dot {
  background: #22c55e;
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.16);
}

.system-health-indicator--warning {
  color: #92400e;
  border-color: #fbbf24;
  background: #fffbeb;
}

.system-health-indicator--warning .status-dot {
  background: #f59e0b;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.18);
}

.system-health-indicator--critical {
  color: #991b1b;
  border-color: #f87171;
  background: #fef2f2;
}

.system-health-indicator--critical .status-dot {
  background: #ef4444;
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.18);
}

@media (max-width: 760px) {
  .system-health-indicator {
    justify-content: center;
    width: 100%;
  }
}
</style>
