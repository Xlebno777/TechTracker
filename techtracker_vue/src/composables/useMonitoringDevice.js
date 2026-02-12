import { computed, ref, watch } from 'vue';
import apiClient from '@/api';

const STORAGE_KEY = 'monitoring_selected_device_id';

const monitoringDevices = ref([]);
const selectedMonitoringDeviceId = ref(null);
const loadingMonitoringDevices = ref(false);
const initialized = ref(false);

const unwrap = (res) => (Array.isArray(res.data) ? res.data : (res.data?.results || []));

const normalizeId = (value) => {
  const id = Number(value);
  return Number.isFinite(id) ? id : null;
};

const selectInitialDevice = () => {
  const availableIds = new Set(monitoringDevices.value.map((item) => item.id));
  const current = normalizeId(selectedMonitoringDeviceId.value);
  if (current && availableIds.has(current)) {
    selectedMonitoringDeviceId.value = current;
    return;
  }

  const saved = normalizeId(localStorage.getItem(STORAGE_KEY));
  if (saved && availableIds.has(saved)) {
    selectedMonitoringDeviceId.value = saved;
    return;
  }

  selectedMonitoringDeviceId.value = monitoringDevices.value.length
    ? monitoringDevices.value[0].id
    : null;
};

const loadMonitoringDevices = async ({ force = false } = {}) => {
  if (loadingMonitoringDevices.value) return;
  if (initialized.value && !force) return;

  loadingMonitoringDevices.value = true;
  try {
    const res = await apiClient.get('agent-status/?status=ok&ordering=-updated_at&limit=5000');
    const rows = unwrap(res);
    const uniq = new Map();
    for (const row of rows) {
      if (!row?.device) continue;
      if (uniq.has(row.device)) continue;
      const name = row.device_name || `ID ${row.device}`;
      const serial = row.device_serial || '';
      uniq.set(row.device, {
        id: row.device,
        name,
        serial,
        label: serial ? `${name} (${serial})` : name,
      });
    }
    monitoringDevices.value = Array.from(uniq.values()).sort((a, b) => a.name.localeCompare(b.name));
    selectInitialDevice();
    initialized.value = true;
  } catch (e) {
    monitoringDevices.value = [];
    selectedMonitoringDeviceId.value = null;
    initialized.value = true;
  } finally {
    loadingMonitoringDevices.value = false;
  }
};

watch(selectedMonitoringDeviceId, (value) => {
  const id = normalizeId(value);
  if (id) {
    localStorage.setItem(STORAGE_KEY, String(id));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
});

const selectedMonitoringDevice = computed(() => (
  monitoringDevices.value.find((item) => item.id === normalizeId(selectedMonitoringDeviceId.value)) || null
));

const selectedMonitoringSerial = computed(() => selectedMonitoringDevice.value?.serial || '');

export function useMonitoringDevice() {
  return {
    monitoringDevices,
    selectedMonitoringDeviceId,
    selectedMonitoringDevice,
    selectedMonitoringSerial,
    loadingMonitoringDevices,
    loadMonitoringDevices,
  };
}
