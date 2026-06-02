<template>
  <div :class="['system-settings-page', isEmbedded ? 'p-0' : 'p-4']">
    <Toast />

    <PageHeader
      v-if="!isEmbedded"
      title="Настройки системы"
      :refreshable="true"
      :loading="loading"
      help-title="Гайд: настройки системы"
      help-intro="На этой странице собраны общие служебные действия по мониторинговому контуру."
      :help-steps="helpSteps"
      help-note="Очистка истории удаляет только данные мониторинга и анализа. Настройки моделей, профили состояния и политики СППР сохраняются."
      @refresh="refreshPage"
    />

    <div v-if="showSummary" class="grid gap-3 mb-3 summary-grid">
      <div class="card summary-card">
        <span class="summary-label">Сырые метрики</span>
        <strong>{{ counts.raw_metrics ?? 0 }}</strong>
      </div>
      <div class="card summary-card">
        <span class="summary-label">Рассчитанные метрики</span>
        <strong>{{ counts.computed_metrics ?? 0 }}</strong>
      </div>
      <div class="card summary-card">
        <span class="summary-label">Запуски прогноза</span>
        <strong>{{ counts.forecast_runs ?? 0 }}</strong>
      </div>
      <div class="card summary-card">
        <span class="summary-label">Точки прогноза</span>
        <strong>{{ counts.forecast_points ?? 0 }}</strong>
      </div>
      <div class="card summary-card">
        <span class="summary-label">Оценки состояния</span>
        <strong>{{ counts.state_estimates ?? 0 }}</strong>
      </div>
      <div class="card summary-card">
        <span class="summary-label">Запуски СППР</span>
        <strong>{{ counts.decision_runs ?? 0 }}</strong>
      </div>
      <div class="card summary-card">
        <span class="summary-label">LSTM очередь</span>
        <strong>{{ counts.lstm_queue_jobs ?? 0 }}</strong>
      </div>
      <div class="card summary-card">
        <span class="summary-label">Отчеты верификации</span>
        <strong>{{ counts.evaluation_runs ?? 0 }}</strong>
      </div>
    </div>

    <FilterPanel v-if="showIntegrations" title="Интеграция удаленного LSTM">
      <div class="lstm-config-grid">
        <div class="field">
          <label class="field-label">IP LSTM ПК</label>
          <InputText
            v-model.trim="lstmConfig.lstm_host"
            class="w-full"
            placeholder="100.88.10.24"
            :disabled="lstmLoading || lstmSaving || lstmGenerating"
          />
          <small class="field-hint">IP или hostname LSTM компьютера внутри VPN/Tailscale.</small>
        </div>

        <div class="field">
          <label class="field-label">Порт LSTM API</label>
          <InputNumber
            v-model="lstmConfig.lstm_port"
            class="w-full"
            :min="1"
            :max="65535"
            :step="1"
            :use-grouping="false"
            :disabled="lstmLoading || lstmSaving || lstmGenerating"
          />
          <small class="field-hint">Обычно 8099, если не меняли на LSTM-ПК.</small>
        </div>

        <div class="field">
          <label class="field-label">HTTPS</label>
          <div class="switch-row">
            <InputSwitch
              v-model="lstmHttpsEnabled"
              :disabled="lstmLoading || lstmSaving || lstmGenerating"
            />
            <span>{{ lstmHttpsEnabled ? 'HTTPS' : 'HTTP' }}</span>
          </div>
        </div>

        <div class="field">
          <label class="field-label">Таймаут (сек.)</label>
          <InputNumber
            v-model="lstmConfig.timeout_sec"
            class="w-full"
            :min="1"
            :max="180"
            :step="1"
            :use-grouping="false"
            :disabled="lstmLoading || lstmSaving || lstmGenerating"
          />
          <small class="field-hint">Сколько ждать ответ от LSTM перед ошибкой запроса.</small>
        </div>

        <div class="field">
          <label class="field-label">Проверка SSL</label>
          <div class="switch-row">
            <InputSwitch
              v-model="lstmConfig.verify_ssl"
              :disabled="lstmLoading || lstmSaving || lstmGenerating"
            />
            <span>{{ lstmConfig.verify_ssl ? 'Включена (HTTPS сертификат проверяется)' : 'Выключена (обычно для HTTP внутри VPN)' }}</span>
          </div>
        </div>

        <div class="field">
          <label class="field-label">LSTM API URL (собирается автоматически)</label>
          <InputText
            :model-value="resolvedLstmBaseUrl"
            class="w-full"
            readonly
            :disabled="true"
          />
          <small class="field-hint">URL формируется из протокола, IP и порта.</small>
        </div>

        <div class="field field--token">
          <label class="field-label">LSTM API токен</label>
          <div class="token-row">
            <InputText
              v-model="lstmConfig.api_token"
              class="w-full"
              :type="showToken ? 'text' : 'password'"
              placeholder="Вставьте токен или сгенерируйте"
              :disabled="lstmLoading || lstmSaving || lstmGenerating"
            />
            <Button
              :label="showToken ? 'Скрыть' : 'Показать'"
              icon="pi pi-eye"
              text
              @click="showToken = !showToken"
            />
          </div>
          <small class="field-hint">
            После генерации скопируйте этот токен и вставьте его на LSTM-ПК в `LSTM_API_TOKEN`.
          </small>
          <small v-if="lstmConfig.has_token && lstmConfig.token_preview" class="field-hint">
            Текущий токен: {{ lstmConfig.token_preview }}
          </small>
        </div>
      </div>

      <div class="lstm-actions mt-2">
        <Button
          icon="pi pi-key"
          label="Сгенерировать токен"
          :loading="lstmGenerating"
          :disabled="lstmLoading || lstmSaving || lstmGenerating"
          @click="generateLstmToken"
        />
        <Button
          icon="pi pi-copy"
          label="Скопировать токен"
          outlined
          :disabled="!lstmConfig.api_token"
          @click="copyLstmToken"
        />
        <Button
          icon="pi pi-save"
          label="Сохранить настройки LSTM"
          severity="success"
          :loading="lstmSaving"
          :disabled="lstmLoading || lstmSaving || lstmGenerating"
          @click="saveLstmConfig"
        />
      </div>
    </FilterPanel>

    <FilterPanel v-if="showIntegrations" title="Параметры сервера и первого запуска">
      <div class="settings-note">
        Эти параметры дублируют то, что задаётся при установке в консоли. Менять их можно из GUI, но для портов, базы данных и ALLOWED_HOSTS обычно нужен перезапуск сервисов TechTracker.
      </div>

      <div class="env-section">
        <div class="env-section__head">
          <div>
            <strong>Сеть приложения</strong>
            <small>Где слушают backend/frontend и с каких адресов разрешён вход.</small>
          </div>
        </div>
        <div class="environment-grid">
          <div class="field field--wide">
            <label class="field-label">Разрешённые адреса Django</label>
            <InputText v-model.trim="environmentConfig.server.allowed_hosts" class="w-full" :disabled="environmentLoading || environmentSaving" />
            <small class="field-hint">Например: localhost,127.0.0.1,server-ip. Если адреса нет в списке, backend может отклонить запрос.</small>
          </div>
          <div class="field">
            <label class="field-label">Backend host</label>
            <InputText v-model.trim="environmentConfig.server.backend_host" class="w-full" :disabled="environmentLoading || environmentSaving" />
            <small class="field-hint">Обычно 0.0.0.0, чтобы backend был доступен с других ПК.</small>
          </div>
          <div class="field">
            <label class="field-label">Backend port</label>
            <InputNumber v-model="environmentConfig.server.backend_port" class="w-full" :min="1" :max="65535" :use-grouping="false" :disabled="environmentLoading || environmentSaving" />
          </div>
          <div class="field">
            <label class="field-label">Frontend port</label>
            <InputNumber v-model="environmentConfig.server.frontend_port" class="w-full" :min="1" :max="65535" :use-grouping="false" :disabled="environmentLoading || environmentSaving" />
          </div>
          <div class="field field--wide">
            <label class="field-label">Backend URL для frontend/worker</label>
            <InputText v-model.trim="environmentConfig.server.backend_url" class="w-full" :disabled="environmentLoading || environmentSaving" />
            <small class="field-hint">Обычно http://127.0.0.1:8000 на том же сервере.</small>
          </div>
        </div>
      </div>

      <div class="env-section">
        <div class="env-section__head">
          <div>
            <strong>База данных</strong>
            <small>Подключение Django к PostgreSQL. Пароль не показывается, его можно только заменить.</small>
          </div>
        </div>
        <div class="environment-grid">
          <div class="field">
            <label class="field-label">DB name</label>
            <InputText v-model.trim="environmentConfig.database.db_name" class="w-full" :disabled="environmentLoading || environmentSaving" />
          </div>
          <div class="field">
            <label class="field-label">DB user</label>
            <InputText v-model.trim="environmentConfig.database.db_user" class="w-full" :disabled="environmentLoading || environmentSaving" />
          </div>
          <div class="field">
            <label class="field-label">DB host</label>
            <InputText v-model.trim="environmentConfig.database.db_host" class="w-full" :disabled="environmentLoading || environmentSaving" />
          </div>
          <div class="field">
            <label class="field-label">DB port</label>
            <InputText v-model.trim="environmentConfig.database.db_port" class="w-full" :disabled="environmentLoading || environmentSaving" />
          </div>
          <div class="field field--wide">
            <label class="field-label">Новый DB password</label>
            <InputText v-model="environmentConfig.database.db_password" class="w-full" type="password" placeholder="Оставьте пустым, чтобы не менять" :disabled="environmentLoading || environmentSaving" />
            <small class="field-hint">
              Сейчас пароль {{ environmentConfig.database.has_password ? `задан (${environmentConfig.database.password_preview})` : 'не задан' }}. После смены пароля в .env.local пароль PostgreSQL-пользователя в самой БД автоматически не меняется.
            </small>
          </div>
        </div>
      </div>

      <div class="env-section">
        <div class="env-section__head">
          <div>
            <strong>Обновления и администратор</strong>
            <small>Настройки release-обновлений и справочная информация о первом администраторе.</small>
          </div>
        </div>
        <div class="environment-grid">
          <div class="field">
            <label class="field-label">APP_VERSION</label>
            <InputText v-model.trim="environmentConfig.updates.app_version" class="w-full" :disabled="environmentLoading || environmentSaving" />
          </div>
          <div class="field">
            <label class="field-label">Канал релизов</label>
            <InputText v-model.trim="environmentConfig.updates.release_channel" class="w-full" :disabled="environmentLoading || environmentSaving" />
          </div>
          <div class="field field--wide">
            <label class="field-label">Manifest URL</label>
            <InputText v-model.trim="environmentConfig.updates.manifest_url" class="w-full" :disabled="environmentLoading || environmentSaving" />
          </div>
          <div class="field">
            <label class="field-label">Обновления из UI</label>
            <div class="switch-row">
              <InputSwitch v-model="environmentConfig.updates.update_enabled" :disabled="environmentLoading || environmentSaving" />
              <span>{{ environmentConfig.updates.update_enabled ? 'Включены' : 'Выключены' }}</span>
            </div>
          </div>
          <div class="field">
            <label class="field-label">Timeout обновления, сек.</label>
            <InputNumber v-model="environmentConfig.updates.update_timeout_sec" class="w-full" :min="60" :max="86400" :use-grouping="false" :disabled="environmentLoading || environmentSaving" />
          </div>
          <div class="field">
            <label class="field-label">Первый admin username</label>
            <InputText v-model.trim="environmentConfig.admin.username" class="w-full" :disabled="environmentLoading || environmentSaving" />
          </div>
          <div class="field">
            <label class="field-label">Первый admin email</label>
            <InputText v-model.trim="environmentConfig.admin.email" class="w-full" :disabled="environmentLoading || environmentSaving" />
          </div>
        </div>
      </div>

      <div class="lstm-actions mt-2">
        <Button
          icon="pi pi-save"
          label="Сохранить параметры сервера"
          severity="success"
          :loading="environmentSaving"
          :disabled="environmentLoading || environmentSaving"
          @click="saveEnvironmentConfig"
        />
      </div>
    </FilterPanel>

    <FilterPanel v-if="showIntegrations" title="Версия и обновления приложения">
      <div class="release-grid">
        <div class="release-card">
          <span class="summary-label">Текущая версия</span>
          <strong>{{ releaseStatus.current_version || 'не указана' }}</strong>
          <small>Git: {{ releaseStatus.git_branch || 'n/a' }} {{ releaseStatus.git_commit || '' }}</small>
          <small v-if="releaseVersionSourceNote">{{ releaseVersionSourceNote }}</small>
        </div>
        <div class="release-card">
          <span class="summary-label">Последняя версия</span>
          <strong>{{ latestReleaseVersion }}</strong>
          <small>{{ releaseStatus.release_channel || 'single' }} канал</small>
        </div>
        <div class="release-card">
          <span class="summary-label">Состояние обновлений</span>
          <strong :class="updateAvailable ? 'text-warn' : 'text-ok'">
            {{ updateAvailable ? 'Есть обновление' : 'Обновлений нет' }}
          </strong>
          <small>{{ releaseStatus.update_enabled ? 'Запуск разрешён на сервере' : 'Запуск выключен' }}</small>
        </div>
        <div class="release-card">
          <span class="summary-label">Последнее задание</span>
          <strong>{{ lastUpdateJobLabel }}</strong>
          <small>{{ lastUpdateJobText }}</small>
        </div>
      </div>

      <div v-if="releaseBlockedReason" class="release-note release-note--warn">
        {{ releaseBlockedReason }}
      </div>

      <div v-if="releaseStatus.manifest_url" class="release-note">
        Manifest: {{ releaseStatus.manifest_url }}
      </div>
      <div v-else class="release-note release-note--warn">
        Manifest обновлений не настроен. Укажите `APP_RELEASE_MANIFEST_URL` на Windows Server.
      </div>

      <div v-if="releaseNotes.length" class="release-notes">
        <strong>Что изменится</strong>
        <ul>
          <li v-for="(note, index) in releaseNotes" :key="index">{{ note }}</li>
        </ul>
      </div>

      <div class="release-actions">
        <Button
          icon="pi pi-refresh"
          label="Проверить обновления"
          outlined
          :loading="releaseChecking"
          :disabled="releaseLoading || releaseChecking || releaseStarting"
          @click="checkReleaseUpdate"
        />
        <Button
          icon="pi pi-cloud-download"
          label="Запустить обновление"
          severity="success"
          :loading="releaseStarting"
          :disabled="!canStartUpdate || releaseChecking || releaseStarting"
          @click="startReleaseUpdate"
        />
      </div>

      <div class="update-jobs">
        <div class="update-jobs__head">
          <strong>Журнал обновлений</strong>
          <span>{{ updateJobs.length }} заданий</span>
        </div>
        <div v-if="!updateJobs.length" class="empty-inline">
          Заданий обновления пока нет.
        </div>
        <div v-else class="update-job-list">
          <div v-for="job in updateJobs.slice(0, 5)" :key="job.id" class="update-job-row">
            <div>
              <strong>#{{ job.id }} → {{ job.target_version || 'latest' }}</strong>
              <small>{{ formatDateTime(job.created_at) }}</small>
            </div>
            <span :class="['status-pill', `status-pill--${job.status}`]">{{ jobStatusLabel(job.status) }}</span>
          </div>
        </div>
      </div>
    </FilterPanel>

    <FilterPanel v-if="showHistory" title="Очистка истории мониторинга">
      <div class="danger-layout">
        <div class="danger-copy">
          <h4 class="m-0">Что будет удалено</h4>
          <ul class="danger-list">
            <li>Сырые и рассчитанные метрики мониторинга</li>
            <li>Все прогнозы SARIMA/LSTM/оркестра и оценки состояний</li>
            <li>Очередь LSTM и история запусков СППР</li>
            <li>Файлы верификации из `research/evaluation/run_*`</li>
          </ul>
          <p class="danger-note">
            Профили состояния, настройки СППР, критерии, действия и политики не удаляются.
          </p>
        </div>
        <div class="danger-actions">
          <Button
            icon="pi pi-trash"
            label="Очистить историю мониторинга"
            severity="danger"
            :loading="clearing"
            :disabled="clearing"
            @click="handleClearHistory"
          />
        </div>
      </div>
    </FilterPanel>
  </div>
</template>

<script setup>
import { computed, defineProps, onBeforeUnmount, onMounted, ref } from 'vue';
import apiClient, { describeApiError } from '@/api';
import Button from 'primevue/button';
import InputNumber from 'primevue/inputnumber';
import InputSwitch from 'primevue/inputswitch';
import InputText from 'primevue/inputtext';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';
import PageHeader from '@/components/ui/PageHeader.vue';
import FilterPanel from '@/components/ui/FilterPanel.vue';
import { useConfirmAction } from '@/composables/useConfirmAction';

const props = defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
  mode: {
    type: String,
    default: 'all',
  },
});
const isEmbedded = computed(() => Boolean(props.embedded));

const toast = useToast();
const { confirmAction } = useConfirmAction();

const loading = ref(false);
const clearing = ref(false);
const counts = ref({});
const lstmLoading = ref(false);
const lstmSaving = ref(false);
const lstmGenerating = ref(false);
const showToken = ref(false);
const environmentLoading = ref(false);
const environmentSaving = ref(false);
const releaseLoading = ref(false);
const releaseChecking = ref(false);
const releaseStarting = ref(false);
const releaseStatus = ref({});
const releaseCheck = ref({});
const updateJobs = ref([]);
const ACTIVE_JOB_STATUSES = new Set(['queued', 'running']);
const TERMINAL_JOB_STATUSES = new Set(['completed', 'failed', 'skipped']);
let releasePollTimer = null;
const lstmConfig = ref({
  base_url: 'http://127.0.0.1:8099',
  scheme: 'http',
  lstm_host: '127.0.0.1',
  lstm_port: 8099,
  api_token: '',
  timeout_sec: 20,
  verify_ssl: false,
  has_token: false,
  token_preview: '',
});
const environmentConfig = ref({
  server: {
    allowed_hosts: 'localhost,127.0.0.1',
    backend_host: '0.0.0.0',
    backend_port: 8000,
    frontend_port: 8080,
    backend_url: 'http://127.0.0.1:8000',
  },
  database: {
    db_name: '',
    db_user: '',
    db_host: 'localhost',
    db_port: '5432',
    has_password: false,
    password_preview: '',
    db_password: '',
  },
  updates: {
    app_version: '0.1.0',
    release_channel: 'single',
    manifest_url: '',
    update_enabled: false,
    update_timeout_sec: 3600,
  },
  admin: {
    username: '',
    email: '',
  },
});

const helpSteps = [
  'Сверху видно, сколько сейчас накоплено мониторинговых данных и отчетов.',
  'В блоке интеграции LSTM задайте IP/порт LSTM-ПК, сгенерируйте токен и сохраните параметры подключения.',
  'В блоке параметров сервера можно изменить те же значения, которые вводились в консольном установщике; часть изменений применится после перезапуска сервисов.',
  'В блоке версий проверяйте manifest релиза и запускайте обновление только после резервной копии сервера.',
  'Кнопка очистки удаляет только историю мониторинга и анализа, но не настройки системы.',
  'После очистки нужно заново собрать метрики, прогнозы и СППР-запуски для нового цикла анализа.',
];

const showIntegrations = computed(() => props.mode === 'all' || props.mode === 'integrations');
const showHistory = computed(() => props.mode === 'all' || props.mode === 'history');
const showSummary = computed(() => props.mode === 'all' || props.mode === 'history');

const lstmHttpsEnabled = computed({
  get: () => String(lstmConfig.value.scheme || 'http').toLowerCase() === 'https',
  set: (value) => {
    lstmConfig.value.scheme = value ? 'https' : 'http';
  },
});

const resolvedLstmBaseUrl = computed(() => {
  const scheme = String(lstmConfig.value.scheme || 'http').toLowerCase() === 'https' ? 'https' : 'http';
  let host = String(lstmConfig.value.lstm_host || '').trim() || '127.0.0.1';
  const portRaw = Number(lstmConfig.value.lstm_port);
  const defaultPort = scheme === 'https' ? 443 : 80;
  const port = Number.isFinite(portRaw) && portRaw > 0 ? Math.round(portRaw) : defaultPort;
  if (host.includes(':') && !host.startsWith('[') && !host.endsWith(']')) {
    host = `[${host}]`;
  }
  return `${scheme}://${host}:${port}`;
});

const latestReleaseVersion = computed(() => (
  releaseCheck.value?.latest_version
  || releaseCheck.value?.manifest?.version
  || releaseStatus.value?.latest_version
  || 'не проверялась'
));

const releaseVersionSourceNote = computed(() => {
  const configured = releaseStatus.value?.configured_version;
  const versionFile = releaseStatus.value?.version_file;
  if (!configured || !versionFile || configured === versionFile) return '';
  return `env: ${configured}, VERSION: ${versionFile}`;
});

const updateAvailable = computed(() => Boolean(
  releaseCheck.value?.update_available || releaseStatus.value?.update_available,
));

const releaseNotes = computed(() => {
  const notes = releaseCheck.value?.manifest?.notes || releaseStatus.value?.manifest?.notes || [];
  return Array.isArray(notes) ? notes.filter(Boolean) : [];
});

const releaseBlockedReason = computed(() => (
  releaseStatus.value?.blocked_reason || ''
));

const canStartUpdate = computed(() => (
  Boolean(releaseStatus.value?.can_start_update) && updateAvailable.value
));

const lastUpdateJobLabel = computed(() => {
  const job = releaseStatus.value?.last_job || updateJobs.value?.[0];
  if (!job) return 'не запускалось';
  return jobStatusLabel(job.status);
});

const lastUpdateJobText = computed(() => {
  const job = releaseStatus.value?.last_job || updateJobs.value?.[0];
  if (!job) return 'Журнал пуст';
  const version = job.target_version ? `версия ${job.target_version}` : 'latest';
  return `${version}, ${formatDateTime(job.updated_at || job.created_at)}`;
});

function latestUpdateJob() {
  return releaseStatus.value?.last_job || updateJobs.value?.[0] || null;
}

function isActiveUpdateJob(job) {
  return ACTIVE_JOB_STATUSES.has(String(job?.status || '').toLowerCase());
}

function isTerminalUpdateJob(job) {
  return TERMINAL_JOB_STATUSES.has(String(job?.status || '').toLowerCase());
}

function stopReleasePolling() {
  if (releasePollTimer) {
    clearInterval(releasePollTimer);
    releasePollTimer = null;
  }
}

function startReleasePolling() {
  if (releasePollTimer) return;
  releasePollTimer = window.setInterval(() => {
    pollReleaseUpdateStatus();
  }, 5000);
}

async function loadSummary() {
  loading.value = true;
  try {
    const res = await apiClient.get('monitoring-system/summary/');
    counts.value = res.data || {};
  } catch (err) {
    counts.value = {};
    toast.add({ severity: 'error', summary: 'Ошибка сводки', detail: describeApiError(err, 'Не удалось загрузить сводку по системе'), life: 9000 });
  } finally {
    loading.value = false;
  }
}

async function loadLstmConfig() {
  lstmLoading.value = true;
  try {
    const res = await apiClient.get('monitoring-system/lstm-config/');
    lstmConfig.value = {
      base_url: res.data?.base_url || 'http://127.0.0.1:8099',
      scheme: res.data?.scheme || 'http',
      lstm_host: res.data?.lstm_host || '127.0.0.1',
      lstm_port: Number(res.data?.lstm_port ?? 8099),
      api_token: res.data?.api_token || '',
      timeout_sec: Number(res.data?.timeout_sec ?? 20),
      verify_ssl: Boolean(res.data?.verify_ssl),
      has_token: Boolean(res.data?.has_token),
      token_preview: res.data?.token_preview || '',
    };
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Ошибка LSTM', detail: describeApiError(err, 'Не удалось загрузить настройки LSTM'), life: 9000 });
  } finally {
    lstmLoading.value = false;
  }
}

function normalizeEnvironmentConfig(data = {}) {
  const server = data.server || {};
  const database = data.database || {};
  const updates = data.updates || {};
  const admin = data.admin || {};
  return {
    server: {
      allowed_hosts: server.allowed_hosts || 'localhost,127.0.0.1',
      backend_host: server.backend_host || '0.0.0.0',
      backend_port: Number(server.backend_port ?? 8000),
      frontend_port: Number(server.frontend_port ?? 8080),
      backend_url: server.backend_url || 'http://127.0.0.1:8000',
    },
    database: {
      db_name: database.db_name || '',
      db_user: database.db_user || '',
      db_host: database.db_host || 'localhost',
      db_port: String(database.db_port || '5432'),
      has_password: Boolean(database.has_password),
      password_preview: database.password_preview || '',
      db_password: '',
    },
    updates: {
      app_version: updates.app_version || '0.1.0',
      release_channel: updates.release_channel || 'single',
      manifest_url: updates.manifest_url || '',
      update_enabled: Boolean(updates.update_enabled),
      update_timeout_sec: Number(updates.update_timeout_sec ?? 3600),
    },
    admin: {
      username: admin.username || '',
      email: admin.email || '',
    },
  };
}

async function loadEnvironmentConfig({ silent = false } = {}) {
  environmentLoading.value = true;
  try {
    const res = await apiClient.get('monitoring-system/environment-config/');
    environmentConfig.value = normalizeEnvironmentConfig(res.data || {});
  } catch (err) {
    if (!silent) {
      toast.add({ severity: 'error', summary: 'Ошибка параметров сервера', detail: describeApiError(err, 'Не удалось загрузить параметры сервера'), life: 9000 });
    }
  } finally {
    environmentLoading.value = false;
  }
}

async function saveEnvironmentConfig() {
  environmentSaving.value = true;
  try {
    const payload = {
      server: {
        allowed_hosts: environmentConfig.value.server.allowed_hosts,
        backend_host: environmentConfig.value.server.backend_host,
        backend_port: Number(environmentConfig.value.server.backend_port || 8000),
        frontend_port: Number(environmentConfig.value.server.frontend_port || 8080),
        backend_url: environmentConfig.value.server.backend_url,
      },
      database: {
        db_name: environmentConfig.value.database.db_name,
        db_user: environmentConfig.value.database.db_user,
        db_host: environmentConfig.value.database.db_host,
        db_port: environmentConfig.value.database.db_port,
        db_password: environmentConfig.value.database.db_password || '',
      },
      updates: {
        app_version: environmentConfig.value.updates.app_version,
        release_channel: environmentConfig.value.updates.release_channel,
        manifest_url: environmentConfig.value.updates.manifest_url,
        update_enabled: Boolean(environmentConfig.value.updates.update_enabled),
        update_timeout_sec: Number(environmentConfig.value.updates.update_timeout_sec || 3600),
      },
      admin: {
        username: environmentConfig.value.admin.username,
        email: environmentConfig.value.admin.email,
      },
    };
    const res = await apiClient.post('monitoring-system/save-environment-config/', payload);
    environmentConfig.value = normalizeEnvironmentConfig(res.data?.config || {});
    toast.add({
      severity: 'success',
      summary: 'Сохранено',
      detail: res.data?.detail || 'Параметры сервера сохранены.',
      life: 4500,
    });
    await loadReleaseStatus();
  } catch (err) {
    const detail = describeApiError(err, 'Не удалось сохранить параметры сервера');
    toast.add({ severity: 'error', summary: 'Ошибка сохранения сервера', detail, life: 10000 });
  } finally {
    environmentSaving.value = false;
  }
}

async function saveLstmConfig() {
  lstmSaving.value = true;
  try {
    const payload = {
      base_url: resolvedLstmBaseUrl.value,
      scheme: lstmConfig.value.scheme,
      lstm_host: lstmConfig.value.lstm_host,
      lstm_port: Number(lstmConfig.value.lstm_port || 8099),
      api_token: lstmConfig.value.api_token,
      timeout_sec: Number(lstmConfig.value.timeout_sec || 20),
      verify_ssl: Boolean(lstmConfig.value.verify_ssl),
    };
    const res = await apiClient.post('monitoring-system/save-lstm-config/', payload);
    const cfg = res.data?.config || {};
    lstmConfig.value = {
      base_url: cfg.base_url || payload.base_url,
      scheme: cfg.scheme || payload.scheme || 'http',
      lstm_host: cfg.lstm_host || payload.lstm_host || '127.0.0.1',
      lstm_port: Number(cfg.lstm_port ?? payload.lstm_port ?? 8099),
      api_token: cfg.api_token || payload.api_token || '',
      timeout_sec: Number(cfg.timeout_sec ?? payload.timeout_sec ?? 20),
      verify_ssl: Boolean(cfg.verify_ssl ?? payload.verify_ssl),
      has_token: Boolean(cfg.has_token),
      token_preview: cfg.token_preview || '',
    };
    toast.add({
      severity: 'success',
      summary: 'Сохранено',
      detail: res.data?.detail || 'Настройки LSTM сохранены.',
      life: 3000,
    });
  } catch (err) {
    const detail = describeApiError(err, 'Не удалось сохранить настройки LSTM');
    toast.add({ severity: 'error', summary: 'Ошибка сохранения LSTM', detail, life: 10000 });
  } finally {
    lstmSaving.value = false;
  }
}

async function generateLstmToken() {
  lstmGenerating.value = true;
  try {
    const res = await apiClient.post('monitoring-system/generate-lstm-token/', { bytes: 32, save: true });
    const cfg = res.data?.config || {};
    lstmConfig.value = {
      base_url: cfg.base_url || resolvedLstmBaseUrl.value,
      scheme: cfg.scheme || lstmConfig.value.scheme || 'http',
      lstm_host: cfg.lstm_host || lstmConfig.value.lstm_host || '127.0.0.1',
      lstm_port: Number(cfg.lstm_port ?? lstmConfig.value.lstm_port ?? 8099),
      api_token: res.data?.generated_token || cfg.api_token || '',
      timeout_sec: Number(cfg.timeout_sec ?? lstmConfig.value.timeout_sec ?? 20),
      verify_ssl: Boolean(cfg.verify_ssl ?? lstmConfig.value.verify_ssl),
      has_token: Boolean(cfg.has_token || res.data?.generated_token),
      token_preview: cfg.token_preview || '',
    };
    showToken.value = true;
    toast.add({
      severity: 'success',
      summary: 'Токен сгенерирован',
      detail: 'Новый токен сохранён в .env.local. Скопируйте его и вставьте в LSTM_API_TOKEN на LSTM-ПК.',
      life: 5000,
    });
  } catch (err) {
    const detail = describeApiError(err, 'Не удалось сгенерировать токен');
    toast.add({ severity: 'error', summary: 'Ошибка генерации токена', detail, life: 10000 });
  } finally {
    lstmGenerating.value = false;
  }
}

async function copyLstmToken() {
  const token = String(lstmConfig.value.api_token || '').trim();
  if (!token) {
    toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Токен пустой', life: 2500 });
    return;
  }
  try {
    await navigator.clipboard.writeText(token);
    toast.add({ severity: 'success', summary: 'Скопировано', detail: 'Токен скопирован в буфер обмена', life: 2200 });
  } catch {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось скопировать токен', life: 3200 });
  }
}

function jobStatusLabel(statusValue) {
  const map = {
    queued: 'В очереди',
    running: 'Выполняется',
    completed: 'Успешно',
    failed: 'Ошибка',
    skipped: 'Пропущено',
  };
  return map[String(statusValue || '').toLowerCase()] || 'неизвестно';
}

function formatDateTime(value) {
  if (!value) return 'дата не указана';
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value));
  } catch {
    return String(value);
  }
}

async function loadReleaseStatus({ silent = false } = {}) {
  releaseLoading.value = true;
  try {
    const [statusRes, jobsRes] = await Promise.all([
      apiClient.get('application-updates/status/'),
      apiClient.get('application-updates/'),
    ]);
    releaseStatus.value = statusRes.data || {};
    updateJobs.value = Array.isArray(jobsRes.data) ? jobsRes.data : (jobsRes.data?.results || []);
  } catch (err) {
    if (!silent) {
      toast.add({ severity: 'error', summary: 'Ошибка версии приложения', detail: describeApiError(err, 'Не удалось загрузить информацию о версии приложения'), life: 10000 });
    }
  } finally {
    releaseLoading.value = false;
  }
}

async function checkReleaseUpdate({ notify = true } = {}) {
  if (notify) releaseChecking.value = true;
  try {
    const res = await apiClient.post('application-updates/check/', {});
    releaseCheck.value = res.data || {};
    releaseStatus.value = {
      ...releaseStatus.value,
      ...res.data,
    };
    const detail = res.data?.update_available
      ? `Доступна версия ${res.data?.latest_version || 'latest'}`
      : 'Установлена актуальная версия.';
    if (notify) {
      toast.add({ severity: res.data?.update_available ? 'warn' : 'success', summary: 'Проверка завершена', detail, life: 3500 });
    }
    await loadReleaseStatus({ silent: !notify });
  } catch (err) {
    const detail = describeApiError(err, 'Не удалось проверить обновления');
    if (notify) {
      toast.add({ severity: 'error', summary: 'Ошибка проверки обновлений', detail, life: 10000 });
    }
  } finally {
    if (notify) releaseChecking.value = false;
  }
}

async function pollReleaseUpdateStatus() {
  const previousJob = latestUpdateJob();
  await loadReleaseStatus({ silent: true });
  const job = latestUpdateJob();
  if (isActiveUpdateJob(job)) return;
  if (!previousJob && !job) return;
  if (!isTerminalUpdateJob(job)) return;

  stopReleasePolling();
  await loadEnvironmentConfig({ silent: true });
  await checkReleaseUpdate({ notify: false });

  const statusValue = String(job.status || '').toLowerCase();
  if (statusValue === 'completed') {
    toast.add({
      severity: 'success',
      summary: 'Обновление завершено',
      detail: 'Версия приложения, APP_VERSION и проверка latest синхронизированы автоматически.',
      life: 7000,
    });
  } else if (statusValue === 'failed') {
    toast.add({
      severity: 'error',
      summary: 'Обновление завершилось ошибкой',
      detail: job.error || 'Откройте журнал обновлений для деталей.',
      life: 10000,
    });
  }
}

async function startReleaseUpdate() {
  const confirmed = await confirmAction({
    header: 'Запустить обновление приложения',
    message: 'Backend запустит серверный PowerShell-скрипт обновления. Убедитесь, что на Windows Server настроена резервная копия и APP_UPDATE_ENABLED=1.',
    acceptLabel: 'Запустить',
    acceptSeverity: 'success',
  });
  if (!confirmed) return;

  releaseStarting.value = true;
  try {
    const res = await apiClient.post('application-updates/start-update/', {});
    toast.add({
      severity: 'success',
      summary: 'Обновление поставлено в очередь',
      detail: `Задание #${res.data?.id || ''} запущено на сервере. Статус будет обновляться автоматически.`,
      life: 4500,
    });
    releaseCheck.value = {};
    await loadReleaseStatus({ silent: true });
    startReleasePolling();
  } catch (err) {
    const detail = describeApiError(err, 'Не удалось запустить обновление');
    toast.add({ severity: 'error', summary: 'Ошибка запуска обновления', detail, life: 10000 });
  } finally {
    releaseStarting.value = false;
  }
}

async function handleClearHistory() {
  const confirmed = await confirmAction({
    header: 'Очистить историю мониторинга',
    message: 'Будут удалены метрики, прогнозы, состояния, запуски СППР и отчеты верификации. Действие необратимо.',
    acceptLabel: 'Очистить',
    acceptSeverity: 'danger',
  });
  if (!confirmed) return;

  clearing.value = true;
  try {
    const res = await apiClient.post('monitoring-system/clear-history/');
    toast.add({
      severity: 'success',
      summary: 'История очищена',
      detail: res.data?.detail || 'Мониторинговая история удалена.',
      life: 3500,
    });
    if (showSummary.value || showHistory.value) {
      await loadSummary();
    }
  } catch (err) {
    const detail = describeApiError(err, 'Не удалось очистить историю мониторинга');
    toast.add({ severity: 'error', summary: 'Ошибка очистки истории', detail, life: 10000 });
  } finally {
    clearing.value = false;
  }
}

async function refreshPage() {
  const jobs = [];
  if (showSummary.value || showHistory.value) {
    jobs.push(loadSummary());
  }
  if (showIntegrations.value) {
    jobs.push(loadLstmConfig());
    jobs.push(loadEnvironmentConfig());
    jobs.push(loadReleaseStatus());
  }
  await Promise.all(jobs);
}

onMounted(async () => {
  await refreshPage();
  if (isActiveUpdateJob(latestUpdateJob())) {
    startReleasePolling();
  }
});

onBeforeUnmount(() => {
  stopReleasePolling();
});
</script>

<style scoped>
.system-settings-page {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: 100%;
  min-width: 0;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr));
  min-width: 0;
}

.summary-card {
  padding: 0.9rem;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}

.summary-label {
  font-size: 0.82rem;
  color: #64748b;
  overflow-wrap: anywhere;
}

.lstm-config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
  gap: 0.9rem;
  min-width: 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  min-width: 0;
}

.field--token {
  grid-column: 1 / -1;
}

.field-label {
  font-size: 0.82rem;
  color: #475569;
  font-weight: 600;
}

.field-hint {
  font-size: 0.8rem;
  color: #64748b;
}

.switch-row {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  min-height: 2.25rem;
  color: #334155;
  font-size: 0.92rem;
}

.token-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.5rem;
  align-items: center;
  min-width: 0;
}

.lstm-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.settings-note {
  border: 1px solid #dbeafe;
  border-radius: 12px;
  padding: 0.85rem;
  background: #eff6ff;
  color: #334155;
  margin-bottom: 0.9rem;
  line-height: 1.35;
}

.env-section {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #f8fafc;
  padding: 0.9rem;
  margin-bottom: 0.9rem;
  min-width: 0;
}

.env-section__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.8rem;
  margin-bottom: 0.85rem;
  min-width: 0;
}

.env-section__head > div {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}

.env-section__head strong {
  color: #1e293b;
}

.env-section__head small {
  color: #64748b;
  overflow-wrap: anywhere;
}

.environment-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr));
  gap: 0.9rem;
  min-width: 0;
}

.field--wide {
  grid-column: span 2;
}

.release-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 210px), 1fr));
  gap: 0.8rem;
  min-width: 0;
}

.release-card {
  border: 1px solid #dbe3ef;
  border-radius: 12px;
  padding: 0.85rem;
  background: #f8fafc;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}

.release-card strong {
  color: #1e293b;
  overflow-wrap: anywhere;
}

.release-card small,
.update-job-row small {
  color: #64748b;
  overflow-wrap: anywhere;
}

.text-ok {
  color: #16a34a !important;
}

.text-warn {
  color: #d97706 !important;
}

.release-note {
  margin-top: 0.8rem;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  padding: 0.75rem;
  color: #334155;
  background: #eff6ff;
  overflow-wrap: anywhere;
}

.release-note--warn {
  border-color: #fed7aa;
  background: #fff7ed;
  color: #9a3412;
}

.release-notes {
  margin-top: 0.8rem;
  border: 1px solid #dbe3ef;
  border-radius: 12px;
  padding: 0.85rem;
  background: #fff;
}

.release-notes ul {
  margin: 0.45rem 0 0;
  padding-left: 1.2rem;
  color: #334155;
}

.release-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-top: 0.9rem;
}

.update-jobs {
  margin-top: 0.9rem;
  border: 1px solid #dbe3ef;
  border-radius: 12px;
  padding: 0.85rem;
  background: #fff;
  min-width: 0;
}

.update-jobs__head,
.update-job-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.8rem;
  min-width: 0;
}

.update-jobs__head span {
  color: #64748b;
  font-size: 0.86rem;
}

.update-job-list {
  display: grid;
  gap: 0.55rem;
  margin-top: 0.65rem;
}

.update-job-row {
  border-top: 1px solid #e2e8f0;
  padding-top: 0.55rem;
}

.update-job-row > div {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.status-pill {
  border-radius: 999px;
  padding: 0.25rem 0.55rem;
  font-size: 0.78rem;
  font-weight: 700;
  background: #e2e8f0;
  color: #334155;
  white-space: nowrap;
}

.status-pill--completed {
  background: #dcfce7;
  color: #166534;
}

.status-pill--running,
.status-pill--queued {
  background: #dbeafe;
  color: #1d4ed8;
}

.status-pill--failed {
  background: #fee2e2;
  color: #b91c1c;
}

.status-pill--skipped {
  background: #fef3c7;
  color: #92400e;
}

.empty-inline {
  margin-top: 0.55rem;
  color: #64748b;
  font-size: 0.92rem;
}

.danger-layout {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
  gap: 1rem;
  align-items: start;
  min-width: 0;
}

.danger-copy {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
  min-width: 0;
}

.danger-list {
  margin: 0;
  padding-left: 1.2rem;
  color: #334155;
  display: grid;
  gap: 0.35rem;
}

.danger-note {
  margin: 0;
  color: #64748b;
  font-size: 0.92rem;
}

.danger-actions {
  display: flex;
  justify-content: flex-end;
  align-items: flex-start;
  min-width: 0;
}

.system-settings-page :deep(.p-inputtext),
.system-settings-page :deep(.p-inputnumber),
.system-settings-page :deep(.p-inputnumber-input),
.system-settings-page :deep(.p-inputtextarea),
.system-settings-page :deep(.p-dropdown) {
  width: 100%;
  min-width: 0;
}

.system-settings-page :deep(.p-datatable-wrapper) {
  overflow: auto;
}

.system-settings-page :deep(.p-button) {
  max-width: 100%;
}

@media (max-width: 920px) {
  .token-row {
    grid-template-columns: 1fr;
  }

  .danger-layout {
    grid-template-columns: 1fr;
  }

  .field--wide {
    grid-column: 1 / -1;
  }

  .danger-actions {
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .lstm-actions {
    width: 100%;
  }

  .lstm-actions :deep(.p-button),
  .release-actions :deep(.p-button) {
    width: 100%;
    justify-content: center;
  }

  .update-jobs__head,
  .update-job-row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
