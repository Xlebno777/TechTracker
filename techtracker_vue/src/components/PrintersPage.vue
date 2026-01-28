<template>
  <div class="p-4 printers-page page-shell">
    <div class="flex justify-content-between align-items-center mb-4">
      <h2 class="text-2xl font-bold m-0 text-900">Принтеры</h2>
      <Button icon="pi pi-refresh" rounded text @click="fetchFavoritePrinters" :loading="loadingPrinters" />
    </div>

    <div class="card p-4 mb-4 shadow-1 border-round bg-white">
      <div class="grid formgrid p-fluid align-items-end">
        <div class="col-12 md:col-8 mb-3">
          <label class="font-semibold block mb-2">Выбор принтера</label>
          <Dropdown
            v-model="selectedPrinterId"
            :options="favoritePrinters"
            optionLabel="name"
            optionValue="id"
            showClear
            placeholder="Выберите принтер из избранного"
          />
        </div>
        <div class="col-12 md:col-4 mb-3">
          <div class="printer-meta">
            <div class="text-600 text-sm">IP</div>
            <div class="font-medium text-900">{{ selectedPrinter?.ip_address || '—' }}</div>
          </div>
        </div>
      </div>
    </div>

    <DataTable
      :value="printJobs"
      :loading="loadingJobs"
      paginator
      :rows="10"
      stripedRows
      responsiveLayout="scroll"
      class="tech-table shadow-2 border-round"
    >
      <template #empty>
        <div class="p-3 text-center">
          <span v-if="!selectedPrinterId">Выберите принтер, чтобы увидеть историю печати.</span>
          <span v-else>История печати пуста.</span>
        </div>
      </template>

      <Column field="document_name" header="Документ" style="min-width: 260px" />
      <Column field="pages" header="Страниц" style="width: 120px" />
      <Column field="user_name" header="Пользователь" style="min-width: 160px" />
      <Column field="printer_name" header="Принтер" style="min-width: 200px" />
      <Column header="Дата" field="timestamp" style="min-width: 200px">
        <template #body="{ data }">
          {{ new Date(data.timestamp).toLocaleDateString('ru-RU', {day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit'}) }}
        </template>
      </Column>
      <Column v-if="auth.isAdmin" header="Действия" style="width: 110px">
        <template #body="{ data }">
          <Button icon="pi pi-trash" text rounded severity="danger" @click="deleteJob(data)" />
        </template>
      </Column>
    </DataTable>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import apiClient from '@/api';
import { useAuthStore } from '@/stores/auth';

import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Dropdown from 'primevue/dropdown';
import Button from 'primevue/button';

const favoritePrinters = ref([]);
const selectedPrinterId = ref(null);
const printJobs = ref([]);
const loadingPrinters = ref(false);
const loadingJobs = ref(false);
const auth = useAuthStore();

const selectedPrinter = computed(() =>
  favoritePrinters.value.find(p => p.id === selectedPrinterId.value)
);

const fetchFavoritePrinters = async () => {
  loadingPrinters.value = true;
  try {
    const res = await apiClient.get('devices/favorite_printers/');
    favoritePrinters.value = res.data || [];

    if (selectedPrinterId.value) {
      const stillExists = favoritePrinters.value.some(p => p.id === selectedPrinterId.value);
      if (!stillExists) {
        selectedPrinterId.value = null;
        printJobs.value = [];
      }
    }
  } finally {
    loadingPrinters.value = false;
  }
};

const fetchPrintJobs = async (deviceId) => {
  if (!deviceId) {
    printJobs.value = [];
    return;
  }
  loadingJobs.value = true;
  try {
    const res = await apiClient.get('printjob/', {
      params: {
        device: deviceId,
        ordering: '-id'
      }
    });
    printJobs.value = res.data || [];
  } finally {
    loadingJobs.value = false;
  }
};

const deleteJob = async (job) => {
  if (!job?.id) return;
  const ok = window.confirm('Удалить запись о печати?');
  if (!ok) return;
  await apiClient.delete(`printjob/${job.id}/`);
  printJobs.value = printJobs.value.filter(j => j.id !== job.id);
};

watch(selectedPrinterId, (val) => {
  fetchPrintJobs(val);
});

onMounted(async () => {
  await fetchFavoritePrinters();
});
</script>

<style scoped>
.printer-meta {
  border: 1px dashed #e2e8f0;
  border-radius: 8px;
  padding: 0.75rem 1rem;
}
</style>
