<template>
  <div class="agents-page page-shell">
    <Toast />

    <header class="agents-header">
      <div class="min-w-0">
        <h2>Агенты</h2>
        <p>Сервисные агенты Windows и управление сбором метрик.</p>
      </div>
      <Button icon="pi pi-refresh" label="Обновить" :loading="loadingAgents" @click="refreshData" />
    </header>

    <section class="summary-grid" aria-label="Сводка агентов">
      <div class="summary-tile">
        <span>Всего</span>
        <strong>{{ agents.length }}</strong>
      </div>
      <div class="summary-tile">
        <span>Online</span>
        <strong>{{ summary.online }}</strong>
      </div>
      <div class="summary-tile">
        <span>Ошибки</span>
        <strong>{{ summary.error }}</strong>
      </div>
      <div class="summary-tile">
        <span>Команды</span>
        <strong>{{ summary.pending }}</strong>
      </div>
    </section>

    <div class="agents-layout">
      <section class="surface-panel agent-list-panel">
        <div class="panel-head">
          <div>
            <h3>Список агентов</h3>
            <span>{{ filteredAgents.length }} из {{ agents.length }}</span>
          </div>
          <InputText v-model.trim="search" placeholder="Поиск" class="search-input" />
        </div>

        <DataTable
          :value="filteredAgents"
          dataKey="id"
          :loading="loadingAgents"
          stripedRows
          responsiveLayout="scroll"
          scrollable
          scrollHeight="34rem"
          class="agents-table"
          @row-click="selectAgent($event.data)"
        >
          <template #empty>
            <div class="empty-state">
              <i class="pi pi-server" />
              <span>Агенты пока не зарегистрированы.</span>
            </div>
          </template>
          <Column header="Устройство" style="min-width: 230px">
            <template #body="{ data }">
              <button
                type="button"
                :class="['agent-row-button', { active: selectedAgent?.id === data.id }]"
                @click.stop="selectAgent(data)"
              >
                <span class="agent-device">{{ data.device_name || data.host_name || 'Без имени' }}</span>
                <span class="agent-serial">{{ data.device_serial || 'серийный номер не задан' }}</span>
              </button>
            </template>
          </Column>
          <Column header="Статус" style="width: 130px">
            <template #body="{ data }">
              <Tag :value="healthLabel(data.health_state)" :severity="healthSeverity(data.health_state)" />
            </template>
          </Column>
          <Column header="Обновлено" style="min-width: 150px">
            <template #body="{ data }">{{ formatTime(data.last_seen_at) }}</template>
          </Column>
        </DataTable>
      </section>

      <section class="surface-panel agent-detail-panel">
        <template v-if="selectedAgent">
          <div class="detail-head">
            <div class="min-w-0">
              <div class="detail-title-row">
                <h3>{{ selectedAgent.device_name || selectedAgent.host_name || 'Агент' }}</h3>
                <Tag :value="healthLabel(selectedAgent.health_state)" :severity="healthSeverity(selectedAgent.health_state)" />
              </div>
              <p>{{ selectedAgent.device_serial || 'серийный номер не задан' }}</p>
            </div>
            <div class="detail-actions">
              <Button
                icon="pi pi-sync"
                label="Перезапустить"
                severity="warning"
                outlined
                :loading="actionLoading.restart"
                @click="restartAgent"
              />
            </div>
          </div>

          <div class="info-grid">
            <div class="info-row">
              <span>Устройство</span>
              <strong>{{ deviceCaption(selectedAgent) }}</strong>
            </div>
            <div class="info-row">
              <span>Служба</span>
              <strong>{{ selectedAgent.service_name || 'TechTrackerAgent' }}</strong>
            </div>
            <div class="info-row">
              <span>Статус службы</span>
              <strong>{{ selectedAgent.service_status || '—' }}</strong>
            </div>
            <div class="info-row">
              <span>Версия агента</span>
              <strong>{{ selectedAgent.agent_version || '—' }}</strong>
            </div>
            <div class="info-row">
              <span>Последний статус</span>
              <strong>{{ formatTime(selectedAgent.last_seen_at) }}</strong>
            </div>
            <div class="info-row">
              <span>Последнее обновление</span>
              <strong>{{ updateCaption(selectedAgent) }}</strong>
            </div>
          </div>

          <section class="section-block">
            <div class="section-title">
              <h4>Обновление агента</h4>
              <Tag :value="updateStatusLabel(selectedAgent.last_update_status)" :severity="updateSeverity(selectedAgent.last_update_status)" />
            </div>
            <div class="update-form">
              <div class="field-block">
                <label>Целевая версия</label>
                <InputText v-model.trim="updateForm.target_version" placeholder="например 0.2.0" />
              </div>
              <div class="field-block field-wide">
                <label>URL установщика</label>
                <InputText v-model.trim="updateForm.installer_url" placeholder="https://..." />
              </div>
              <Button
                icon="pi pi-download"
                label="Поставить обновление"
                :loading="actionLoading.update"
                @click="queueUpdate"
              />
            </div>
            <p v-if="selectedAgent.last_update_message" class="status-message">
              {{ selectedAgent.last_update_message }}
            </p>
          </section>

          <section class="section-block">
            <div class="section-title">
              <h4>Метрики</h4>
              <Button
                icon="pi pi-save"
                label="Сохранить"
                :disabled="!hasMetricChanges"
                :loading="actionLoading.metrics"
                @click="saveMetrics"
              />
            </div>
            <div class="metric-list">
              <label v-for="metric in metricCatalog" :key="metric.name" class="metric-row">
                <Checkbox
                  :modelValue="isMetricEnabled(metric.name)"
                  :binary="true"
                  @update:modelValue="toggleMetric(metric.name, $event)"
                />
                <span class="metric-text">
                  <strong>{{ metric.title }}</strong>
                  <span>{{ metric.description }}</span>
                  <em>{{ metric.setup }}</em>
                </span>
              </label>
            </div>
          </section>

          <section class="section-block">
            <div class="section-title">
              <h4>Команды</h4>
              <Button icon="pi pi-history" label="Обновить" text :loading="loadingCommands" @click="loadCommands(selectedAgent.id)" />
            </div>
            <DataTable
              :value="commands"
              dataKey="id"
              :loading="loadingCommands"
              responsiveLayout="scroll"
              stripedRows
              class="commands-table"
            >
              <template #empty>
                <div class="empty-state empty-state-inline">Команд пока нет.</div>
              </template>
              <Column field="id" header="ID" style="width: 80px" />
              <Column header="Команда" style="min-width: 140px">
                <template #body="{ data }">{{ commandLabel(data.command) }}</template>
              </Column>
              <Column header="Статус" style="width: 150px">
                <template #body="{ data }">
                  <Tag :value="commandStatusLabel(data.status)" :severity="commandSeverity(data.status)" />
                </template>
              </Column>
              <Column header="Создана" style="min-width: 160px">
                <template #body="{ data }">{{ formatTime(data.created_at) }}</template>
              </Column>
              <Column header="Результат" style="min-width: 240px">
                <template #body="{ data }">
                  <span class="command-result">{{ data.result_message || '—' }}</span>
                </template>
              </Column>
            </DataTable>
          </section>
        </template>

        <div v-else class="empty-detail">
          <i class="pi pi-server" />
          <span>Выберите агента из списка.</span>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Checkbox from 'primevue/checkbox';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import InputText from 'primevue/inputtext';
import Tag from 'primevue/tag';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';

const toast = useToast();

const agents = ref([]);
const commands = ref([]);
const metricCatalog = ref([]);
const selectedAgent = ref(null);
const selectedEnabledTasks = ref([]);
const search = ref('');
const loadingAgents = ref(false);
const loadingCommands = ref(false);
const actionLoading = ref({
  restart: false,
  update: false,
  metrics: false,
});
const updateForm = ref({
  target_version: '',
  installer_url: '',
});

const normalizeList = (value) => (Array.isArray(value) ? value : []);

const enabledTasksFromAgent = (agent) => normalizeList(agent?.metrics_config?.enabled_tasks).map(String);

const sortedTasks = (items) => [...new Set(normalizeList(items).map(String))].sort();

const filteredAgents = computed(() => {
  const q = search.value.toLowerCase();
  if (!q) return agents.value;
  return agents.value.filter((agent) => [
    agent.device_name,
    agent.device_serial,
    agent.host_name,
    agent.service_name,
    agent.agent_version,
  ].some((value) => String(value || '').toLowerCase().includes(q)));
});

const summary = computed(() => agents.value.reduce((acc, agent) => {
  const health = agent.health_state || agent.status || 'unknown';
  if (health === 'online') acc.online += 1;
  if (health === 'error') acc.error += 1;
  acc.pending += Number(agent.pending_commands_count || 0);
  return acc;
}, { online: 0, error: 0, pending: 0 }));

const hasMetricChanges = computed(() => {
  const current = sortedTasks(enabledTasksFromAgent(selectedAgent.value)).join('|');
  const draft = sortedTasks(selectedEnabledTasks.value).join('|');
  return current !== draft;
});

const formatTime = (value) => {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
};

const healthLabel = (value) => ({
  online: 'Online',
  error: 'Ошибка',
  offline: 'Offline',
  unknown: 'Unknown',
}[value] || 'Unknown');

const healthSeverity = (value) => ({
  online: 'success',
  error: 'danger',
  offline: 'warning',
  unknown: 'secondary',
}[value] || 'secondary');

const updateStatusLabel = (value) => ({
  idle: 'Нет задач',
  pending: 'В очереди',
  running: 'Выполняется',
  success: 'Успешно',
  failed: 'Ошибка',
}[value] || 'Нет задач');

const updateSeverity = (value) => ({
  idle: 'secondary',
  pending: 'warning',
  running: 'info',
  success: 'success',
  failed: 'danger',
}[value] || 'secondary');

const commandLabel = (value) => ({
  restart: 'Перезапуск',
  update: 'Обновление',
  set_metrics: 'Метрики',
}[value] || value || '—');

const commandStatusLabel = (value) => ({
  pending: 'В очереди',
  acknowledged: 'Принята',
  running: 'Выполняется',
  success: 'Успешно',
  failed: 'Ошибка',
  cancelled: 'Отменена',
}[value] || value || '—');

const commandSeverity = (value) => ({
  pending: 'warning',
  acknowledged: 'info',
  running: 'info',
  success: 'success',
  failed: 'danger',
  cancelled: 'secondary',
}[value] || 'secondary');

const deviceCaption = (agent) => {
  const parts = [
    agent.device_name || agent.host_name || '—',
    agent.device_serial,
    agent.device_ip_address || agent.ip_address,
    agent.device_location,
  ].filter(Boolean);
  return parts.join(' · ');
};

const updateCaption = (agent) => {
  if (agent.last_update_completed_at) return formatTime(agent.last_update_completed_at);
  if (agent.last_update_started_at) return formatTime(agent.last_update_started_at);
  return updateStatusLabel(agent.last_update_status);
};

const setSelectedAgentData = (agent) => {
  selectedAgent.value = agent;
  selectedEnabledTasks.value = enabledTasksFromAgent(agent);
  updateForm.value.target_version = agent?.desired_version || '';
  updateForm.value.installer_url = '';
};

const selectAgent = async (agent) => {
  if (!agent) return;
  setSelectedAgentData(agent);
  await loadCommands(agent.id);
};

const isMetricEnabled = (name) => selectedEnabledTasks.value.includes(name);

const toggleMetric = (name, enabled) => {
  const current = new Set(selectedEnabledTasks.value);
  if (enabled) current.add(name);
  else current.delete(name);
  selectedEnabledTasks.value = [...current];
};

const loadMetricCatalog = async () => {
  const res = await apiClient.get('agents/metric-catalog/');
  metricCatalog.value = normalizeList(res.data?.metrics);
};

const loadAgents = async () => {
  loadingAgents.value = true;
  try {
    const res = await apiClient.get('agents/?ordering=-last_seen_at');
    const rows = Array.isArray(res.data) ? res.data : (res.data?.results || []);
    agents.value = rows;
    const selectedId = selectedAgent.value?.id;
    const nextSelected = rows.find((agent) => agent.id === selectedId) || rows[0] || null;
    if (nextSelected) {
      setSelectedAgentData(nextSelected);
      await loadCommands(nextSelected.id);
    } else {
      selectedAgent.value = null;
      commands.value = [];
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось загрузить агентов';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  } finally {
    loadingAgents.value = false;
  }
};

const loadCommands = async (agentId) => {
  if (!agentId) return;
  loadingCommands.value = true;
  try {
    const res = await apiClient.get(`agents/${agentId}/commands/`);
    commands.value = Array.isArray(res.data) ? res.data : (res.data?.results || []);
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось загрузить команды агента';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  } finally {
    loadingCommands.value = false;
  }
};

const refreshData = async () => {
  await Promise.all([loadMetricCatalog(), loadAgents()]);
};

const restartAgent = async () => {
  if (!selectedAgent.value) return;
  const agentId = selectedAgent.value.id;
  actionLoading.value.restart = true;
  try {
    await apiClient.post(`agents/${agentId}/restart/`, { reason: 'manual-ui' });
    toast.add({ severity: 'success', summary: 'Команда создана', detail: 'Перезапуск поставлен в очередь.', life: 3000 });
    await loadAgents();
    await loadCommands(agentId);
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось создать команду перезапуска';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  } finally {
    actionLoading.value.restart = false;
  }
};

const queueUpdate = async () => {
  if (!selectedAgent.value) return;
  const agentId = selectedAgent.value.id;
  actionLoading.value.update = true;
  try {
    await apiClient.post(`agents/${agentId}/update/`, {
      target_version: updateForm.value.target_version,
      installer_url: updateForm.value.installer_url,
    });
    toast.add({ severity: 'success', summary: 'Команда создана', detail: 'Обновление поставлено в очередь.', life: 3000 });
    await loadAgents();
    await loadCommands(agentId);
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось создать команду обновления';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  } finally {
    actionLoading.value.update = false;
  }
};

const saveMetrics = async () => {
  if (!selectedAgent.value) return;
  const agentId = selectedAgent.value.id;
  actionLoading.value.metrics = true;
  try {
    const res = await apiClient.post(`agents/${agentId}/set-metrics/`, {
      enabled_tasks: selectedEnabledTasks.value,
    });
    if (res.data?.agent) setSelectedAgentData(res.data.agent);
    toast.add({ severity: 'success', summary: 'Команда создана', detail: 'Конфигурация метрик поставлена в очередь.', life: 3000 });
    await loadAgents();
    await loadCommands(agentId);
  } catch (e) {
    const detail = e?.response?.data?.detail || 'Не удалось сохранить метрики';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4000 });
  } finally {
    actionLoading.value.metrics = false;
  }
};

onMounted(() => {
  refreshData();
});
</script>

<style scoped>
.agents-page {
  padding: 1rem;
}

.agents-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.agents-header h2,
.agents-header p,
.panel-head h3,
.detail-head h3,
.section-title h4 {
  margin: 0;
}

.agents-header h2 {
  color: #0f172a;
  font-size: 1.65rem;
  font-weight: 800;
}

.agents-header p {
  color: #64748b;
  margin-top: 0.25rem;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.summary-tile {
  min-width: 0;
  padding: 1rem;
  border: 1px solid #dbe4ef;
  border-radius: 8px;
  background: #fff;
}

.summary-tile span {
  display: block;
  color: #64748b;
  font-size: 0.85rem;
}

.summary-tile strong {
  display: block;
  color: #0f172a;
  font-size: 1.65rem;
  line-height: 1.2;
  margin-top: 0.25rem;
}

.agents-layout {
  display: grid;
  grid-template-columns: minmax(320px, 430px) minmax(0, 1fr);
  gap: 1rem;
  align-items: start;
}

.surface-panel {
  min-width: 0;
  border: 1px solid #dbe4ef;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.agent-list-panel,
.agent-detail-panel {
  padding: 1rem;
}

.panel-head,
.detail-head,
.section-title,
.update-form {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.panel-head {
  margin-bottom: 0.75rem;
}

.panel-head h3,
.detail-head h3,
.section-title h4 {
  color: #0f172a;
  font-size: 1.05rem;
  font-weight: 800;
}

.panel-head span,
.detail-head p {
  display: block;
  color: #64748b;
  margin: 0.2rem 0 0;
  font-size: 0.88rem;
}

.search-input {
  width: min(14rem, 45%);
  min-width: 9rem;
}

.agent-row-button {
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  text-align: left;
  padding: 0.25rem 0;
  cursor: pointer;
}

.agent-row-button.active .agent-device {
  color: #0369a1;
}

.agent-device,
.agent-serial {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-device {
  color: #0f172a;
  font-weight: 700;
}

.agent-serial {
  color: #64748b;
  font-size: 0.8rem;
  margin-top: 0.1rem;
}

.detail-head {
  align-items: flex-start;
  padding-bottom: 1rem;
  border-bottom: 1px solid #e2e8f0;
}

.detail-title-row,
.detail-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  min-width: 0;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0;
  margin-top: 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

.info-row {
  min-width: 0;
  padding: 0.85rem 1rem;
  border-bottom: 1px solid #e2e8f0;
}

.info-row:nth-child(odd) {
  border-right: 1px solid #e2e8f0;
}

.info-row:nth-last-child(-n + 2) {
  border-bottom: 0;
}

.info-row span,
.field-block label {
  display: block;
  color: #64748b;
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
}

.info-row strong {
  display: block;
  min-width: 0;
  color: #0f172a;
  font-size: 0.95rem;
  line-height: 1.35;
  margin-top: 0.25rem;
  overflow-wrap: anywhere;
}

.section-block {
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid #e2e8f0;
}

.update-form {
  align-items: end;
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-top: 0.8rem;
}

.field-block {
  min-width: 13rem;
  flex: 1 1 13rem;
}

.field-wide {
  flex-basis: 20rem;
}

.field-block label {
  margin-bottom: 0.35rem;
}

.field-block :deep(.p-inputtext) {
  width: 100%;
}

.status-message {
  color: #475569;
  margin: 0.75rem 0 0;
  overflow-wrap: anywhere;
}

.metric-list {
  margin-top: 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

.metric-row {
  display: grid;
  grid-template-columns: 1.6rem minmax(0, 1fr);
  gap: 0.65rem;
  padding: 0.8rem 1rem;
  border-bottom: 1px solid #e2e8f0;
  cursor: pointer;
}

.metric-row:last-child {
  border-bottom: 0;
}

.metric-text {
  min-width: 0;
  display: grid;
  gap: 0.2rem;
}

.metric-text strong {
  color: #0f172a;
}

.metric-text span {
  color: #475569;
}

.metric-text em {
  color: #64748b;
  font-style: normal;
  font-size: 0.88rem;
  overflow-wrap: anywhere;
}

.command-result {
  display: inline-block;
  max-width: 32rem;
  overflow-wrap: anywhere;
  color: #475569;
}

.empty-state,
.empty-detail {
  min-height: 12rem;
  display: grid;
  place-items: center;
  gap: 0.5rem;
  color: #64748b;
  text-align: center;
}

.empty-state-inline {
  min-height: 4rem;
}

.empty-state i,
.empty-detail i {
  color: #94a3b8;
  font-size: 1.8rem;
}

.min-w-0 {
  min-width: 0;
}

@media (max-width: 1180px) {
  .agents-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 760px) {
  .agents-page {
    padding: 0;
  }

  .agents-header,
  .panel-head,
  .detail-head,
  .section-title {
    align-items: stretch;
    flex-direction: column;
  }

  .summary-grid,
  .info-grid {
    grid-template-columns: 1fr;
  }

  .info-row,
  .info-row:nth-child(odd),
  .info-row:nth-last-child(-n + 2) {
    border-right: 0;
    border-bottom: 1px solid #e2e8f0;
  }

  .info-row:last-child {
    border-bottom: 0;
  }

  .search-input,
  .detail-actions :deep(.p-button),
  .section-title :deep(.p-button),
  .update-form :deep(.p-button) {
    width: 100%;
  }
}
</style>
