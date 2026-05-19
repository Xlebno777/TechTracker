import { computed, ref } from 'vue';
import apiClient from '@/api';
import { useMonitoringDeviceStore } from '@/stores/monitoringDevice';

const monitoringDevices = ref([]);
const loadingMonitoringDevices = ref(false);
const initialized = ref(false);

const unwrap = (res) => (Array.isArray(res.data) ? res.data : (res.data?.results || []));

const normalizeId = (value) => {
  const id = Number(value);
  return Number.isFinite(id) ? id : null;
};

export function useMonitoringDevice() {
  const monitoringDeviceStore = useMonitoringDeviceStore();
  monitoringDeviceStore.hydrate();

  const selectedMonitoringDeviceId = computed({
    get: () => monitoringDeviceStore.selectedDeviceId,
    set: (value) => monitoringDeviceStore.setSelectedDeviceId(value),
  });

  const selectedMonitoringDevice = computed(() => (
    monitoringDevices.value.find((item) => item.id === normalizeId(selectedMonitoringDeviceId.value)) || null
  ));

  const selectedMonitoringSerial = computed(() => selectedMonitoringDevice.value?.serial || '');

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
      monitoringDeviceStore.syncWithAvailableIds(monitoringDevices.value.map((item) => item.id));
      initialized.value = true;
    } catch (e) {
      monitoringDevices.value = [];
      monitoringDeviceStore.setSelectedDeviceId(null);
      initialized.value = true;
    } finally {
      loadingMonitoringDevices.value = false;
    }
  };

  return {
    monitoringDevices,
    selectedMonitoringDeviceId,
    selectedMonitoringDevice,
    selectedMonitoringSerial,
    loadingMonitoringDevices,
    loadMonitoringDevices,
  };
}
