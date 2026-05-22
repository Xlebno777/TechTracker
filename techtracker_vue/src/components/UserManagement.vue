<template>
  <div class="users-page p-4">
    <Toast />
    <PageHeader
      title="Пользователи"
      subtitle="Управление пользователями, группами, правами доступа и API-ключами для будущих агентов."
      :refreshable="true"
      :loading="loading"
      help-title="Гайд: управление пользователями"
      help-intro="Эта страница повторяет основные административные действия Django, но в удобном интерфейсе TechTracker."
      :help-steps="helpSteps"
      help-note="API-ключ показывается полностью только сразу после генерации. После обновления страницы будет видна только маска."
      @refresh="loadAll"
    />

    <div class="users-dashboard">
      <div class="stat-card">
        <span>Пользователи</span>
        <strong>{{ users.length }}</strong>
      </div>
      <div class="stat-card">
        <span>Активные</span>
        <strong>{{ activeUsersCount }}</strong>
      </div>
      <div class="stat-card">
        <span>Группы</span>
        <strong>{{ groups.length }}</strong>
      </div>
      <div class="stat-card">
        <span>Доступные права</span>
        <strong>{{ permissions.length }}</strong>
      </div>
    </div>

    <div class="management-grid">
      <FilterPanel title="Пользователи" description="Создание, редактирование групп, статусов и персональных прав.">
        <template #actions>
          <Button icon="pi pi-plus" label="Новый пользователь" @click="startCreateUser" />
        </template>

        <div class="toolbar-row">
          <span class="p-input-icon-left search-box">
            <i class="pi pi-search" />
            <InputText v-model.trim="userSearch" placeholder="Поиск по пользователям" />
          </span>
        </div>

        <DataTable
          :value="filteredUsers"
          dataKey="id"
          responsiveLayout="scroll"
          size="small"
          :rowClass="userRowClass"
          class="safe-table"
        >
          <Column field="username" header="Пользователь" sortable>
            <template #body="{ data }">
              <div class="main-cell">
                <strong>{{ data.username }}</strong>
                <small>{{ fullName(data) || data.email || 'Имя не задано' }}</small>
              </div>
            </template>
          </Column>
          <Column header="Группы">
            <template #body="{ data }">
              <div class="tag-list">
                <span v-for="group in data.groups" :key="group.id" class="soft-tag">{{ group.name }}</span>
                <span v-if="!data.groups?.length" class="muted">нет групп</span>
              </div>
            </template>
          </Column>
          <Column header="Статус" style="width: 150px">
            <template #body="{ data }">
              <div class="status-stack">
                <span :class="['status-pill', data.is_active ? 'status-pill--ok' : 'status-pill--danger']">
                  {{ data.is_active ? 'Активен' : 'Отключен' }}
                </span>
                <span v-if="data.is_superuser" class="status-pill status-pill--warn">superuser</span>
                <span v-else-if="data.is_staff" class="status-pill status-pill--info">staff</span>
              </div>
            </template>
          </Column>
          <Column header="Ключ" style="width: 145px">
            <template #body="{ data }">
              <span :class="['status-pill', data.has_token ? 'status-pill--ok' : 'status-pill--neutral']">
                {{ data.has_token ? data.token_preview : 'нет' }}
              </span>
            </template>
          </Column>
          <Column header="Действия" style="width: 170px">
            <template #body="{ data }">
              <div class="row-actions">
                <Button icon="pi pi-pencil" text rounded severity="info" @click="editUser(data)" />
                <Button icon="pi pi-key" text rounded severity="success" @click="generateUserToken(data)" />
                <Button icon="pi pi-trash" text rounded severity="danger" @click="deleteUser(data)" />
              </div>
            </template>
          </Column>
        </DataTable>
      </FilterPanel>

      <FilterPanel title="Группы" description="Группы объединяют пользователей и наборы разрешений.">
        <template #actions>
          <Button icon="pi pi-sparkles" label="Базовые группы" outlined @click="bootstrapGroups" />
          <Button icon="pi pi-plus" label="Новая группа" @click="startCreateGroup" />
        </template>

        <div class="toolbar-row">
          <span class="p-input-icon-left search-box">
            <i class="pi pi-search" />
            <InputText v-model.trim="groupSearch" placeholder="Поиск по группам" />
          </span>
        </div>

        <DataTable
          :value="filteredGroups"
          dataKey="id"
          responsiveLayout="scroll"
          size="small"
          class="safe-table"
        >
          <Column field="name" header="Группа" sortable>
            <template #body="{ data }">
              <div class="main-cell">
                <strong>{{ data.name }}</strong>
                <small>Пользователей: {{ data.users_count ?? 0 }}</small>
              </div>
            </template>
          </Column>
          <Column header="Права">
            <template #body="{ data }">
              <span class="muted">{{ data.permissions_detail?.length || 0 }} разрешений</span>
            </template>
          </Column>
          <Column header="Действия" style="width: 130px">
            <template #body="{ data }">
              <div class="row-actions">
                <Button icon="pi pi-pencil" text rounded severity="info" @click="editGroup(data)" />
                <Button icon="pi pi-trash" text rounded severity="danger" @click="deleteGroup(data)" />
              </div>
            </template>
          </Column>
        </DataTable>
      </FilterPanel>
    </div>

    <Dialog v-model:visible="userDialogVisible" modal :header="userForm.id ? 'Редактирование пользователя' : 'Новый пользователь'" :style="{ width: 'min(920px, 96vw)' }">
      <div class="dialog-grid">
        <div class="field">
          <label>Логин</label>
          <InputText v-model.trim="userForm.username" placeholder="agent_metrics_01" />
        </div>
        <div class="field">
          <label>Email</label>
          <InputText v-model.trim="userForm.email" placeholder="user@example.local" />
        </div>
        <div class="field">
          <label>Имя</label>
          <InputText v-model.trim="userForm.first_name" />
        </div>
        <div class="field">
          <label>Фамилия</label>
          <InputText v-model.trim="userForm.last_name" />
        </div>
        <div class="field field--wide">
          <label>{{ userForm.id ? 'Новый пароль' : 'Пароль' }}</label>
          <Password v-model="userForm.password" toggleMask :feedback="false" placeholder="Оставьте пустым, если пароль не нужен" />
          <small>Для агентского пользователя можно оставить пустым и использовать только API-ключ.</small>
        </div>
        <div class="switch-card">
          <InputSwitch v-model="userForm.is_active" />
          <div><strong>Активен</strong><small>Пользователь может входить и использовать API.</small></div>
        </div>
        <div class="switch-card">
          <InputSwitch v-model="userForm.is_staff" />
          <div><strong>Staff</strong><small>Доступ к административным возможностям Django.</small></div>
        </div>
        <div class="switch-card">
          <InputSwitch v-model="userForm.is_superuser" />
          <div><strong>Superuser</strong><small>Полный доступ ко всем правам. Использовать осторожно.</small></div>
        </div>
        <div class="field field--wide">
          <label>Группы</label>
          <MultiSelect
            v-model="userForm.group_ids"
            :options="groups"
            optionLabel="name"
            optionValue="id"
            display="chip"
            filter
            placeholder="Выберите группы"
          />
        </div>
        <div class="field field--wide">
          <label>Персональные права</label>
          <MultiSelect
            v-model="userForm.user_permission_ids"
            :options="permissionOptions"
            optionLabel="label"
            optionValue="id"
            display="chip"
            filter
            placeholder="Обычно лучше задавать права через группы"
          />
          <small>Персональные права нужны редко. Для агентов обычно достаточно группы `Agent`, `PrinterAgents`, `MetricsAgents` или `VMAgents`.</small>
        </div>
      </div>
      <template #footer>
        <Button label="Отмена" text @click="userDialogVisible = false" />
        <Button label="Сохранить пользователя" icon="pi pi-save" :loading="savingUser" @click="saveUser" />
      </template>
    </Dialog>

    <Dialog v-model:visible="groupDialogVisible" modal :header="groupForm.id ? 'Редактирование группы' : 'Новая группа'" :style="{ width: 'min(860px, 96vw)' }">
      <div class="dialog-grid">
        <div class="field field--wide">
          <label>Название группы</label>
          <InputText v-model.trim="groupForm.name" placeholder="MetricsAgents" />
        </div>
        <div class="field field--wide">
          <label>Права группы</label>
          <MultiSelect
            v-model="groupForm.permissions"
            :options="permissionOptions"
            optionLabel="label"
            optionValue="id"
            display="chip"
            filter
            placeholder="Выберите Django permissions"
          />
          <small>Для большинства экранов TechTracker дополнительно используются группы `Admins`, `Users`, `Agent`, `PrinterAgents`, `MetricsAgents`, `VMAgents`.</small>
        </div>
      </div>
      <template #footer>
        <Button label="Отмена" text @click="groupDialogVisible = false" />
        <Button label="Сохранить группу" icon="pi pi-save" :loading="savingGroup" @click="saveGroup" />
      </template>
    </Dialog>

    <Dialog v-model:visible="tokenDialogVisible" modal header="API-ключ пользователя" :style="{ width: 'min(720px, 96vw)' }">
      <div class="token-result">
        <p>Ключ показан полностью только сейчас. Используйте его при установке агента или сервиса.</p>
        <code>{{ generatedToken }}</code>
        <div class="token-actions">
          <Button icon="pi pi-copy" label="Скопировать ключ" @click="copyGeneratedToken" />
          <Button label="Закрыть" outlined @click="tokenDialogVisible = false" />
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import apiClient from '@/api';
import Button from 'primevue/button';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import Dialog from 'primevue/dialog';
import InputSwitch from 'primevue/inputswitch';
import InputText from 'primevue/inputtext';
import MultiSelect from 'primevue/multiselect';
import Password from 'primevue/password';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';
import PageHeader from '@/components/ui/PageHeader.vue';
import FilterPanel from '@/components/ui/FilterPanel.vue';

const toast = useToast();
const loading = ref(false);
const users = ref([]);
const groups = ref([]);
const permissions = ref([]);
const userSearch = ref('');
const groupSearch = ref('');
const userDialogVisible = ref(false);
const groupDialogVisible = ref(false);
const tokenDialogVisible = ref(false);
const savingUser = ref(false);
const savingGroup = ref(false);
const generatedToken = ref('');

const helpSteps = [
  'Создавайте обычных пользователей для работы с интерфейсом и агентских пользователей для внешних сервисов.',
  'Группы удобнее персональных прав: `Admins` для администраторов, `Users` для ограниченного доступа, `Agent` для общих агентов.',
  '`PrinterAgents`, `MetricsAgents`, `VMAgents` можно использовать для разделения будущих установщиков агентов.',
  'API-ключ генерируется кнопкой с ключом в строке пользователя и затем вставляется в установщик агента.',
  'Не выдавайте `superuser`, если достаточно группы `Admins` или конкретной агентской группы.',
];

const emptyUserForm = () => ({
  id: null,
  username: '',
  first_name: '',
  last_name: '',
  email: '',
  password: '',
  is_active: true,
  is_staff: false,
  is_superuser: false,
  group_ids: [],
  user_permission_ids: [],
});
const emptyGroupForm = () => ({ id: null, name: '', permissions: [] });
const userForm = ref(emptyUserForm());
const groupForm = ref(emptyGroupForm());

const activeUsersCount = computed(() => users.value.filter((item) => item.is_active).length);
const permissionOptions = computed(() => permissions.value.map((item) => ({
  ...item,
  label: `${item.app_label}.${item.codename} — ${item.name}`,
})));

const filteredUsers = computed(() => {
  const q = userSearch.value.toLowerCase();
  if (!q) return users.value;
  return users.value.filter((item) => [
    item.username,
    item.first_name,
    item.last_name,
    item.email,
    ...(item.groups || []).map((group) => group.name),
  ].join(' ').toLowerCase().includes(q));
});

const filteredGroups = computed(() => {
  const q = groupSearch.value.toLowerCase();
  if (!q) return groups.value;
  return groups.value.filter((item) => [
    item.name,
    ...(item.permissions_detail || []).map((perm) => `${perm.app_label}.${perm.codename}`),
  ].join(' ').toLowerCase().includes(q));
});

function normalizeList(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  return [];
}

async function loadAll() {
  loading.value = true;
  try {
    const [usersRes, groupsRes, permissionsRes] = await Promise.all([
      apiClient.get('managed-users/'),
      apiClient.get('managed-groups/'),
      apiClient.get('auth-permissions/'),
    ]);
    users.value = normalizeList(usersRes.data);
    groups.value = normalizeList(groupsRes.data);
    permissions.value = normalizeList(permissionsRes.data);
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить пользователей и группы', life: 4500 });
  } finally {
    loading.value = false;
  }
}

function fullName(user) {
  return [user.first_name, user.last_name].filter(Boolean).join(' ');
}

function startCreateUser() {
  userForm.value = emptyUserForm();
  userDialogVisible.value = true;
}

function editUser(user) {
  userForm.value = {
    id: user.id,
    username: user.username || '',
    first_name: user.first_name || '',
    last_name: user.last_name || '',
    email: user.email || '',
    password: '',
    is_active: Boolean(user.is_active),
    is_staff: Boolean(user.is_staff),
    is_superuser: Boolean(user.is_superuser),
    group_ids: (user.groups || []).map((group) => group.id),
    user_permission_ids: (user.user_permissions || []).map((perm) => perm.id),
  };
  userDialogVisible.value = true;
}

function startCreateGroup() {
  groupForm.value = emptyGroupForm();
  groupDialogVisible.value = true;
}

function editGroup(group) {
  groupForm.value = {
    id: group.id,
    name: group.name || '',
    permissions: (group.permissions_detail || []).map((perm) => perm.id),
  };
  groupDialogVisible.value = true;
}

async function saveUser() {
  if (!userForm.value.username) {
    toast.add({ severity: 'warn', summary: 'Проверка', detail: 'Укажите логин пользователя', life: 3000 });
    return;
  }
  savingUser.value = true;
  try {
    const payload = { ...userForm.value };
    if (!payload.password) delete payload.password;
    if (payload.id) {
      await apiClient.patch(`managed-users/${payload.id}/`, payload);
    } else {
      delete payload.id;
      await apiClient.post('managed-users/', payload);
    }
    userDialogVisible.value = false;
    toast.add({ severity: 'success', summary: 'Сохранено', detail: 'Пользователь сохранен', life: 2500 });
    await loadAll();
  } catch (error) {
    const detail = error?.response?.data?.detail || JSON.stringify(error?.response?.data || {}) || 'Не удалось сохранить пользователя';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 5000 });
  } finally {
    savingUser.value = false;
  }
}

async function saveGroup() {
  if (!groupForm.value.name) {
    toast.add({ severity: 'warn', summary: 'Проверка', detail: 'Укажите название группы', life: 3000 });
    return;
  }
  savingGroup.value = true;
  try {
    const payload = { name: groupForm.value.name, permissions: groupForm.value.permissions || [] };
    if (groupForm.value.id) {
      await apiClient.patch(`managed-groups/${groupForm.value.id}/`, payload);
    } else {
      await apiClient.post('managed-groups/', payload);
    }
    groupDialogVisible.value = false;
    toast.add({ severity: 'success', summary: 'Сохранено', detail: 'Группа сохранена', life: 2500 });
    await loadAll();
  } catch (error) {
    const detail = error?.response?.data?.detail || JSON.stringify(error?.response?.data || {}) || 'Не удалось сохранить группу';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 5000 });
  } finally {
    savingGroup.value = false;
  }
}

async function deleteUser(user) {
  if (!window.confirm(`Удалить пользователя ${user.username}?`)) return;
  try {
    await apiClient.delete(`managed-users/${user.id}/`);
    toast.add({ severity: 'success', summary: 'Удалено', detail: 'Пользователь удален', life: 2500 });
    await loadAll();
  } catch (error) {
    const detail = error?.response?.data?.detail || 'Не удалось удалить пользователя';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  }
}

async function deleteGroup(group) {
  if (!window.confirm(`Удалить группу ${group.name}?`)) return;
  try {
    await apiClient.delete(`managed-groups/${group.id}/`);
    toast.add({ severity: 'success', summary: 'Удалено', detail: 'Группа удалена', life: 2500 });
    await loadAll();
  } catch (error) {
    const detail = error?.response?.data?.detail || 'Не удалось удалить группу';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  }
}

async function generateUserToken(user) {
  if (!window.confirm(`Сгенерировать новый API-ключ для ${user.username}? Старый ключ перестанет работать.`)) return;
  try {
    const res = await apiClient.post(`managed-users/${user.id}/generate-token/`, {});
    generatedToken.value = res.data?.token || '';
    tokenDialogVisible.value = true;
    toast.add({ severity: 'success', summary: 'Ключ создан', detail: 'Скопируйте ключ из открытого окна', life: 3500 });
    await loadAll();
  } catch (error) {
    const detail = error?.response?.data?.detail || 'Не удалось сгенерировать ключ';
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 4500 });
  }
}

async function bootstrapGroups() {
  try {
    await apiClient.post('managed-groups/bootstrap-defaults/', {});
    toast.add({ severity: 'success', summary: 'Группы проверены', detail: 'Базовые группы созданы или уже существовали', life: 3000 });
    await loadAll();
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось создать базовые группы', life: 4500 });
  }
}

async function copyGeneratedToken() {
  try {
    await navigator.clipboard.writeText(generatedToken.value);
    toast.add({ severity: 'success', summary: 'Скопировано', detail: 'API-ключ скопирован', life: 2200 });
  } catch {
    toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось скопировать ключ', life: 3200 });
  }
}

function userRowClass(user) {
  return user.is_active ? '' : 'row-disabled';
}

onMounted(loadAll);
</script>

<style scoped>
.users-page {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  min-width: 0;
}

.users-dashboard {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr));
  gap: 0.75rem;
}

.stat-card {
  border: 1px solid #dbe3ef;
  border-radius: 14px;
  padding: 0.85rem;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.stat-card span,
.muted {
  color: #64748b;
  font-size: 0.86rem;
}

.stat-card strong {
  color: #0f172a;
  font-size: 1.35rem;
}

.management-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.85fr);
  gap: 0.85rem;
  align-items: start;
  min-width: 0;
}

.toolbar-row {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  min-width: 0;
}

.search-box {
  width: min(100%, 360px);
}

.main-cell {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
}

.main-cell strong {
  color: #0f172a;
  overflow-wrap: anywhere;
}

.main-cell small {
  color: #64748b;
  overflow-wrap: anywhere;
}

.tag-list,
.status-stack,
.row-actions,
.token-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}

.soft-tag,
.status-pill {
  border-radius: 999px;
  padding: 0.24rem 0.55rem;
  font-size: 0.78rem;
  font-weight: 800;
  white-space: nowrap;
}

.soft-tag {
  background: #eff6ff;
  color: #1d4ed8;
}

.status-pill--ok {
  background: #dcfce7;
  color: #166534;
}

.status-pill--danger {
  background: #fee2e2;
  color: #991b1b;
}

.status-pill--warn {
  background: #fef3c7;
  color: #92400e;
}

.status-pill--info {
  background: #dbeafe;
  color: #1d4ed8;
}

.status-pill--neutral {
  background: #e2e8f0;
  color: #475569;
}

.dialog-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
  min-width: 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  min-width: 0;
}

.field--wide {
  grid-column: 1 / -1;
}

.field label {
  color: #475569;
  font-weight: 700;
  font-size: 0.86rem;
}

.field small {
  color: #64748b;
}

.switch-card {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 0.75rem;
  display: flex;
  gap: 0.7rem;
  align-items: flex-start;
  background: #f8fafc;
  min-width: 0;
}

.switch-card div {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.switch-card strong {
  color: #0f172a;
}

.switch-card small {
  color: #64748b;
}

.token-result {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.token-result p {
  margin: 0;
  color: #334155;
}

.token-result code {
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  padding: 0.85rem;
  background: #eff6ff;
  color: #0f172a;
  overflow-wrap: anywhere;
  line-height: 1.45;
}

.safe-table :deep(.p-datatable-wrapper) {
  overflow: auto;
}

.safe-table :deep(.p-datatable-table) {
  min-width: 760px;
}

.users-page :deep(.p-inputtext),
.users-page :deep(.p-password),
.users-page :deep(.p-password-input),
.users-page :deep(.p-multiselect) {
  width: 100%;
  min-width: 0;
}

:deep(.row-disabled) {
  opacity: 0.62;
}

@media (max-width: 1120px) {
  .management-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .dialog-grid {
    grid-template-columns: 1fr;
  }

  .toolbar-row,
  .search-box {
    width: 100%;
  }
}
</style>
