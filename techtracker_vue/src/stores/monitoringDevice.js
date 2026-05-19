import { defineStore } from 'pinia';

const STORAGE_KEY = 'monitoring_selected_device_id';

const normalizeId = (value) => {
  const id = Number(value);
  return Number.isFinite(id) ? id : null;
};

const canUseStorage = () => typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';

export const useMonitoringDeviceStore = defineStore('monitoringDevice', {
  state: () => ({
    selectedDeviceId: null,
    hydrated: false,
  }),

  actions: {
    hydrate() {
      if (this.hydrated) return;
      if (canUseStorage()) {
        this.selectedDeviceId = normalizeId(window.localStorage.getItem(STORAGE_KEY));
      }
      this.hydrated = true;
    },

    setSelectedDeviceId(value) {
      const id = normalizeId(value);
      this.selectedDeviceId = id;
      if (!canUseStorage()) return;
      if (id) {
        window.localStorage.setItem(STORAGE_KEY, String(id));
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    },

    syncWithAvailableIds(rawIds) {
      const ids = Array.from(
        new Set(
          (Array.isArray(rawIds) ? rawIds : [])
            .map((value) => normalizeId(value))
            .filter((value) => value)
        )
      );

      if (!ids.length) {
        this.setSelectedDeviceId(null);
        return;
      }

      if (!this.selectedDeviceId || !ids.includes(this.selectedDeviceId)) {
        this.setSelectedDeviceId(ids[0]);
      }
    },
  },
});

