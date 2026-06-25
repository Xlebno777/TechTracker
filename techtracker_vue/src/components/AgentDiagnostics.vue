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
            <div class="agent-update-card">
              <div class="agent-update-facts">
                <div>
                  <span>Версия агента</span>
                  <strong>{{ selectedAgent.agent_version || 'не определена' }}</strong>
                </div>
                <div>
                  <span>Новейшая версия</span>
                  <strong>{{ latestAgentVersionLabel }}</strong>
                </div>
                <div>
                  <span>Asset</span>
                  <strong>{{ agentInstaller?.installer_asset_name || 'не проверялся' }}</strong>
                </div>
              </div>
              <div class="agent-update-actions">
                <p :class="['status-message', agentUpdateStateClass]">{{ agentUpdateStateLabel }}</p>
                <div class="agent-update-buttons">
                  <Button
                    icon="pi pi-refresh"
                    label="Проверить"
                    outlined
                    :loading="actionLoading.checkUpdate"
                    :disabled="actionLoading.checkUpdate || actionLoading.update"
                    @click="checkAgentUpdate"
                  />
                  <Button
                    icon="pi pi-download"
                    label="Обновить"
                    severity="success"
                    :loading="actionLoading.update"
                    :disabled="!canQueueAgentUpdate || actionLoading.checkUpdate || actionLoading.update"
                    @click="queueUpdate"
                  />
                </div>
              </div>
            </div>
            <p v-if="agentInstaller?.detail" class="status-message status-message-warn">
              {{ agentInstaller.detail }}
            </p>
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
              <Column header="Действия" style="width: 190px">
                <template #body="{ data }">
                  <div class="command-actions">
                    <Button
                      v-if="canCancelCommand(data)"
                      icon="pi pi-ban"
                      label="Отменить"
                      size="small"
                      severity="warning"
                      outlined
                      :loading="actionLoading.commandAction === 'cancel' && actionLoading.commandId === data.id"
                      :disabled="Boolean(actionLoading.commandAction)"
                      @click="cancelCommand(data)"
                    />
                    <Button
                      icon="pi pi-trash"
                      label="Удалить"
                      size="small"
                      severity="danger"
                      text
                      :loading="actionLoading.commandAction === 'delete' && actionLoading.commandId === data.id"
                      :disabled="Boolean(actionLoading.commandAction)"
                      @click="deleteCommand(data)"
                    />
                  </div>
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
import apiClient, { describeApiError } from '@/api';
import Button from 'primevue/button';
import Checkbox from 'primevue/checkbox';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import InputText from 'primevue/inputtext';
import Tag from 'primevue/tag';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';
import { useConfirmAction } from '@/composables/useConfirmAction';

const toast = useToast();
const { confirmAction } = useConfirmAction();

const agents = ref([]);
const commands = ref([]);
const metricCatalog = ref([]);
const agentInstaller = ref(null);
const selectedAgent = ref(null);
const selectedEnabledTasks = ref([]);
const search = ref('');
const loadingAgents = ref(false);
const loadingCommands = ref(false);
const actionLoading = ref({
  restart: false,
  update: false,
  checkUpdate: false,
  metrics: false,
  commandId: null,
  commandAction: '',
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

const latestAgentVersionLabel = computed(() => {
  if (actionLoading.value.checkUpdate) return 'проверяем';
  return agentInstaller.value?.latest_version || 'не проверялась';
});

const agentVersionCompare = computed(() => {
  const current = selectedAgent.value?.agent_version;
  const latest = agentInstaller.value?.latest_version;
  if (!current || !latest) return null;
  return compareVersions(current, latest);
});

const canQueueAgentUpdate = computed(() => (
  Boolean(selectedAgent.value)
  && agentInstaller.value?.status === 'ok'
  && Boolean(agentInstaller.value?.download_url)
  && Boolean(agentInstaller.value?.latest_version)
  && agentVersionCompare.value !== 0
));

const agentUpdateStateLabel = computed(() => {
  if (actionLoading.value.checkUpdate) return 'Проверяем последнюю версию агента в GitHub Releases.';
  if (!agentInstaller.value) return 'Нажмите «Проверить», чтобы получить последнюю версию агента.';
  if (agentInstaller.value.status && agentInstaller.value.status !== 'ok') return 'Не удалось получить release агента. Подробность показана ниже.';
  if (!selectedAgent.value?.agent_version) return 'Версия установленного агента не определена. Можно поставить последнюю найденную версию.';
  if (agentVersionCompare.value < 0) return 'Доступно обновление агента.';
  if (agentVersionCompare.value === 0) return 'На устройстве установлена актуальная версия агента.';
  if (agentVersionCompare.value > 0) return 'Установленная версия агента новее опубликованного release.';
  return 'Сравнение версий пока недоступно.';
});

const agentUpdateStateClass = computed(() => {
  if (agentInstaller.value?.status && agentInstaller.value.status !== 'ok') return 'text-error';
  if (agentVersionCompare.value < 0) return 'text-warn';
  if (agentVersionCompare.value === 0) return 'text-ok';
  return 'text-muted';
});

const compareVersions = (left, right) => {
  const parse = (value) => String(value || '')
    .trim()
    .replace(/^v/i, '')
    .split(/[.-]/)
    .map((part) => Number.parseInt(part, 10))
    .map((part) => (Number.isFinite(part) ? part : 0));
  const a = parse(left);
  const b = parse(right);
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    const current = a[index] || 0;
    const latest = b[index] || 0;
    if (current < latest) return -1;
    if (current > latest) return 1;
  }
  return 0;
};

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
  cancelled: 'Отменено',
}[value] || 'Нет задач');

const updateSeverity = (value) => ({
  idle: 'secondary',
  pending: 'warning',
  running: 'info',
  success: 'success',
  failed: 'danger',
  cancelled: 'secondary',
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
  try {
    const res = await apiClient.get('agents/metric-catalog/');
    metricCatalog.value = normalizeList(res.data?.metrics);
  } catch (e) {
    metricCatalog.value = [];
    toast.add({ severity: 'error', summary: 'Ошибка загрузки метрик', detail: describeApiError(e, 'Не удалось загрузить каталог метрик'), life: 10000 });
  }
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
    toast.add({ severity: 'error', summary: 'Ошибка загрузки агентов', detail: describeApiError(e, 'Не удалось загрузить агентов'), life: 10000 });
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
    toast.add({ severity: 'error', summary: 'Ошибка команд агента', detail: describeApiError(e, 'Не удалось загрузить команды агента'), life: 10000 });
  } finally {
    loadingCommands.value = false;
  }
};

const refreshData = async () => {
  await Promise.all([loadMetricCatalog(), loadAgents(), checkAgentUpdate({ silent: true })]);
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
    toast.add({ severity: 'error', summary: 'Ошибка команды', detail: describeApiError(e, 'Не удалось создать команду перезапуска'), life: 10000 });
  } finally {
    actionLoading.value.restart = false;
  }
};

const queueUpdate = async () => {
  if (!selectedAgent.value) return;
  if (!agentInstaller.value?.download_url) {
    await checkAgentUpdate({ silent: true });
  }
  if (!agentInstaller.value?.download_url) {
    toast.add({
      severity: 'warn',
      summary: 'Обновление недоступно',
      detail: agentInstaller.value?.detail || 'Сначала нужно успешно проверить release агента.',
      life: 7000,
    });
    return;
  }
  const agentId = selectedAgent.value.id;
  actionLoading.value.update = true;
  try {
    await apiClient.post(`agents/${agentId}/update/`, {
      target_version: agentInstaller.value.latest_version || '',
      installer_url: agentInstaller.value.download_url || '',
    });
    toast.add({
      severity: 'success',
      summary: 'Команда создана',
      detail: `Обновление агента до версии ${agentInstaller.value.latest_version || 'latest'} поставлено в очередь.`,
      life: 3500,
    });
    await loadAgents();
    await loadCommands(agentId);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка обновления агента', detail: describeApiError(e, 'Не удалось создать команду обновления'), life: 10000 });
  } finally {
    actionLoading.value.update = false;
  }
};

const checkAgentUpdate = async ({ silent = false } = {}) => {
  actionLoading.value.checkUpdate = !silent;
  try {
    const res = await apiClient.get('agent-installer/');
    agentInstaller.value = res.data || null;
    if (!silent) {
      const status = agentInstaller.value?.status;
      const detail = status === 'ok'
        ? `Последняя версия агента: ${agentInstaller.value?.latest_version || 'не указана'}.`
        : (agentInstaller.value?.detail || 'GitHub Releases агента ответил с ошибкой.');
      toast.add({
        severity: status === 'ok' ? 'success' : 'error',
        summary: status === 'ok' ? 'Release агента проверен' : 'Ошибка проверки release агента',
        detail,
        life: status === 'ok' ? 3500 : 10000,
      });
    }
  } catch (e) {
    const detail = describeApiError(e, 'Не удалось проверить release агента');
    agentInstaller.value = {
      status: 'error',
      detail,
    };
    if (!silent) {
      toast.add({ severity: 'error', summary: 'Ошибка проверки release агента', detail, life: 10000 });
    }
  } finally {
    actionLoading.value.checkUpdate = false;
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
    toast.add({ severity: 'error', summary: 'Ошибка настройки метрик', detail: describeApiError(e, 'Не удалось сохранить метрики'), life: 10000 });
  } finally {
    actionLoading.value.metrics = false;
  }
};

const canCancelCommand = (command) => ['pending', 'acknowledged', 'running'].includes(String(command?.status || '').toLowerCase());

const cancelCommand = async (command) => {
  if (!command?.id || !selectedAgent.value) return;
  const confirmed = await confirmAction({
    header: 'Отменить команду агента',
    message: `Команда #${command.id} будет помечена как отмененная. Агент больше не сможет записать по ней результат.`,
    acceptLabel: 'Отменить команду',
    acceptSeverity: 'warning',
  });
  if (!confirmed) return;

  actionLoading.value.commandId = command.id;
  actionLoading.value.commandAction = 'cancel';
  try {
    await apiClient.post(`agents/commands/${command.id}/cancel/`, {});
    toast.add({ severity: 'success', summary: 'Команда отменена', detail: `Команда #${command.id} прервана.`, life: 3000 });
    await loadAgents();
    await loadCommands(selectedAgent.value.id);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка отмены команды', detail: describeApiError(e, 'Не удалось отменить команду агента'), life: 10000 });
  } finally {
    actionLoading.value.commandId = null;
    actionLoading.value.commandAction = '';
  }
};

const deleteCommand = async (command) => {
  if (!command?.id || !selectedAgent.value) return;
  const confirmed = await confirmAction({
    header: 'Удалить команду агента',
    message: `Команда #${command.id} будет удалена из журнала. Это действие нельзя отменить.`,
    acceptLabel: 'Удалить',
    acceptSeverity: 'danger',
  });
  if (!confirmed) return;

  actionLoading.value.commandId = command.id;
  actionLoading.value.commandAction = 'delete';
  try {
    await apiClient.delete(`agents/commands/${command.id}/`);
    toast.add({ severity: 'success', summary: 'Команда удалена', detail: `Команда #${command.id} удалена из журнала.`, life: 3000 });
    await loadAgents();
    await loadCommands(selectedAgent.value.id);
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Ошибка удаления команды', detail: describeApiError(e, 'Не удалось удалить команду агента'), life: 10000 });
  } finally {
    actionLoading.value.commandId = null;
    actionLoading.value.commandAction = '';
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

.agent-update-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.85rem;
  align-items: center;
  margin-top: 0.8rem;
  padding: 0.85rem;
  border: 1px solid #dbe4ef;
  border-radius: 8px;
  background: #f8fafc;
  min-width: 0;
}

.agent-update-facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
  min-width: 0;
}

.agent-update-facts div {
  min-width: 0;
}

.agent-update-facts span {
  display: block;
  color: #64748b;
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
}

.agent-update-facts strong {
  display: block;
  color: #0f172a;
  margin-top: 0.25rem;
  overflow-wrap: anywhere;
}

.agent-update-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.55rem;
  min-width: 14rem;
}

.agent-update-buttons,
.command-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.45rem;
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

.agent-update-actions .status-message {
  margin: 0;
  text-align: right;
  max-width: 28rem;
}

.status-message-warn {
  border: 1px solid #fed7aa;
  border-radius: 8px;
  padding: 0.55rem 0.65rem;
  background: #fff7ed;
  color: #9a3412;
}

.text-muted {
  color: #64748b;
}

.text-warn {
  color: #b45309;
}

.text-ok {
  color: #15803d;
}

.text-error {
  color: #b91c1c;
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
  .agent-update-buttons :deep(.p-button),
  .command-actions :deep(.p-button) {
    width: 100%;
  }

  .agent-update-card,
  .agent-update-facts {
    grid-template-columns: 1fr;
  }

  .agent-update-actions {
    align-items: stretch;
    min-width: 0;
  }

  .agent-update-actions .status-message {
    text-align: left;
  }
}
</style>
