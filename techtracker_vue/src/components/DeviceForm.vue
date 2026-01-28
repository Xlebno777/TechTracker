<template>
  <div class="device-form p-fluid p-p-3 page-shell">
    <h2 class="mb-4" style="font-size: 1.5rem; font-weight: 600; color: #2c3e50;">
      {{ isEditing ? 'Редактировать' : 'Добавить' }} устройство
    </h2>

    <!-- Форма устройства -->
    <form @submit.prevent="handleSubmit">
      <!-- Название -->
      <div class="p-field p-mb-3">
        <label for="name" class="p-d-block p-font-bold p-text-lg">Название</label>
        <InputText id="name" v-model="form.name" required class="p-inputtext-lg" />
      </div>

      <!-- Серийный номер -->
      <div class="p-field p-mb-3">
        <label for="serial_number" class="p-d-block p-font-bold p-text-lg">Серийный номер</label>
        <InputText id="serial_number" v-model="form.serial_number" required class="p-inputtext-lg" />
      </div>

      <!-- Инвентарный номер -->
      <div class="p-field p-mb-3">
        <label for="asset_number" class="p-d-block p-font-bold p-text-lg">Инвентарный номер</label>
        <InputText id="asset_number" v-model="form.asset_number" class="p-inputtext-lg" />
      </div>

      <!-- Тип устройства -->
      <div class="p-field p-mb-3">
        <label for="device_type" class="p-d-block p-font-bold p-text-lg">Тип устройства</label>
        <Dropdown
          id="device_type"
          v-model="form.device_type"
          :options="deviceTypes"
          optionLabel="name"
          optionValue="id"
          placeholder="Выберите тип"
          required
          class="p-inputtext-lg"
        />
      </div>

      <!-- Статус -->
      <div class="p-field p-mb-3">
        <label for="status" class="p-d-block p-font-bold p-text-lg">Статус</label>
        <Dropdown
          id="status"
          v-model="form.status"
          :options="statusOptions"
          optionLabel="label"
          optionValue="value"
          placeholder="Выберите статус"
          required
          class="p-inputtext-lg"
        />
      </div>

      <!-- Местоположение -->
      <div class="p-field p-mb-3">
        <label for="location" class="p-d-block p-font-bold p-text-lg">Местоположение</label>
        <Dropdown
          id="location"
          v-model="form.location"
          :options="locations"
          optionLabel="name"
          optionValue="id"
          placeholder="Выберите местоположение"
          required
          class="p-inputtext-lg"
        />
      </div>

      <!-- IP-адрес -->
      <div class="p-field p-mb-3">
        <label for="ip_address" class="p-d-block p-font-bold p-text-lg">IP-адрес</label>
        <InputText id="ip_address" v-model="form.ip_address" class="p-inputtext-lg" />
      </div>

      <!-- MAC-адрес -->
      <div class="p-field p-mb-3">
        <label for="mac_address" class="p-d-block p-font-bold p-text-lg">MAC-адрес</label>
        <InputText id="mac_address" v-model="form.mac_address" class="p-inputtext-lg" />
      </div>

      <!-- Владелец -->
      <div class="p-field p-mb-3">
        <label for="owner" class="p-d-block p-font-bold p-text-lg">Владелец</label>
        <Dropdown
          id="owner"
          v-model="form.owner"
          :options="users"
          optionLabel="username"
          optionValue="id"
          placeholder="Нет владельца"
          showClear
          class="p-inputtext-lg"
        />
      </div>

      <!-- Назначен пользователю -->
      <div class="p-field p-mb-3">
        <label for="assigned_to" class="p-d-block p-font-bold p-text-lg">Назначен пользователю</label>
        <Dropdown
          id="assigned_to"
          v-model="form.assigned_to"
          :options="users"
          optionLabel="username"
          optionValue="id"
          placeholder="Не назначен"
          showClear
          class="p-inputtext-lg"
        />
      </div>

      <!-- Заметки -->
      <div class="p-field p-mb-3">
        <label for="notes" class="p-d-block p-font-bold p-text-lg">Заметки</label>
        <Textarea id="notes" v-model="form.notes" rows="3" autoResize class="p-inputtextarea-lg" />
      </div>

      <!-- Специфичные поля -->
      <div
        v-if="
          selectedDeviceType &&
          ['Ноутбук', 'Настольный ПК', 'Моноблок'].includes(selectedDeviceType.name)
        "
        class="p-mt-3 p-pb-3"
      >
        <h4 class="p-mb-3 p-font-bold">Спецификации ПК</h4>
        <div class="p-field p-mb-3">
          <label for="cpu" class="p-d-block p-font-bold p-text-lg">Процессор</label>
          <InputText id="cpu" v-model="form.computer_specs.cpu" class="p-inputtext-lg" />
        </div>
        <div class="p-field p-mb-3">
          <label for="ram_gb" class="p-d-block p-font-bold p-text-lg">ОЗУ (ГБ)</label>
          <InputNumber id="ram_gb" v-model="form.computer_specs.ram_gb" class="p-inputtext-lg" />
        </div>
      </div>

      <div
        v-if="
          selectedDeviceType &&
          (selectedDeviceType.name.includes('Принтер') ||
            selectedDeviceType.name.includes('Сканер'))
        "
        class="p-mt-3 p-pb-3"
      >
        <h4 class="p-mb-3 p-font-bold">Спецификации МФУ</h4>
        <div class="p-field p-mb-3">
          <label for="printer_type" class="p-d-block p-font-bold p-text-lg">Тип принтера</label>
          <Dropdown
            id="printer_type"
            v-model="form.printer_scanner_specs.printer_type"
            :options="printerTypes"
            optionLabel="label"
            optionValue="value"
            placeholder="Выберите тип"
            class="p-inputtext-lg"
          />
        </div>
        <div class="p-field-checkbox p-mb-3">
          <Checkbox
            inputId="color_printing"
            v-model="form.printer_scanner_specs.color_printing"
            binary
          />
          <label for="color_printing" class="p-font-bold p-text-lg">Цветная печать</label>
        </div>
      </div>

      <div
        v-if="
          selectedDeviceType &&
          ['Коммутатор', 'Маршрутизатор', 'Точка доступа'].some(type =>
            selectedDeviceType.name.includes(type)
          )
        "
        class="p-mt-3 p-pb-3"
      >
        <h4 class="p-mb-3 p-font-bold">Сетевые характеристики</h4>
        <div class="p-field p-mb-3">
          <label for="ports_count" class="p-d-block p-font-bold p-text-lg">Количество портов</label>
          <InputNumber id="ports_count" v-model="form.network_specs.ports_count" class="p-inputtext-lg" />
        </div>
      </div>

      <!-- Кнопки -->
      <div class="p-d-flex p-ai-center p-mt-4">
        <Button
          type="submit"
          label="Сохранить"
          icon="pi pi-check"
          class="p-button-success p-button-lg p-mr-2"
          :loading="loading"
        />

        <Button
          v-if="isEditing && canDeleteDevice()"
          label="Удалить"
          icon="pi pi-trash"
          class="p-button-danger p-button-lg p-mr-2"
          @click="handleDelete"
          :disabled="loading"
        />

        <Button
          label="Отмена"
          icon="pi pi-times"
          class="p-button-secondary p-button-lg"
          @click="$router.push('/devices')"
          severity="secondary"
        />
      </div>
    </form>

    <!-- PrimeVue Confirm и Toast -->
    <ConfirmDialog />
    <Toast />

    <!-- Ошибка -->
    <Message
      v-if="error"
      severity="error"
      :closable="false"
      class="p-mt-4"
      :text="`Ошибка: ${error}`"
    />
  </div>
</template>

<script>
import apiClient from '@/api';
import { useConfirm } from 'primevue/useconfirm';
import { useToast } from 'primevue/usetoast';
import InputText from 'primevue/inputtext';
import Textarea from 'primevue/textarea';
import InputNumber from 'primevue/inputnumber';
import Dropdown from 'primevue/dropdown';
import Checkbox from 'primevue/checkbox';
import Button from 'primevue/button';
import ConfirmDialog from 'primevue/confirmdialog';
import Toast from 'primevue/toast';
import Message from 'primevue/message';

export default {
  name: 'DeviceForm',
  components: {
    InputText,
    Textarea,
    InputNumber,
    Dropdown,
    Checkbox,
    Button,
    ConfirmDialog,
    Toast,
    Message
  },
  setup() {
    const confirm = useConfirm();
    const toast = useToast();
    return { confirm, toast };
  },
  props: {
    deviceId: { type: String, default: null }
  },
  data() {
    return {
      form: {
        name: '',
        serial_number: '',
        asset_number: '',
        device_type: '',
        status: 'active',
        location: '',
        ip_address: '',
        mac_address: '',
        notes: '',
        owner: null,
        assigned_to: null,
        computer_specs: { cpu: '', ram_gb: null },
        printer_scanner_specs: { printer_type: '', color_printing: false },
        network_specs: { ports_count: null }
      },
      statusOptions: [
        { label: 'В работе', value: 'active' },
        { label: 'В ремонте', value: 'in_repair' },
        { label: 'Списано', value: 'retired' },
        { label: 'На складе', value: 'in_stock' },
        { label: 'В резерве', value: 'reserved' }
      ],
      printerTypes: [
        { label: 'Лазерный', value: 'laser' },
        { label: 'Струйный', value: 'inkjet' },
        { label: 'Матричный', value: 'matrix' }
      ],
      deviceTypes: [],
      locations: [],
      users: [],
      currentUser: null,
      loading: false,
      error: null,
      isEditing: false
    };
  },
  computed: {
    selectedDeviceType() {
      return this.deviceTypes.find(t => t.id === this.form.device_type);
    }
  },
  methods: {
    hasGroup(groupName) {
      return this.currentUser?.groups?.some(g => g.name === groupName);
    },
    canDeleteDevice() {
      return this.hasGroup('Admins');
    },
    async fetchCurrentUser() {
      try {
        const res = await apiClient.get('users/me/');
        this.currentUser = res.data;
      } catch (e) {
        console.error('Ошибка загрузки пользователя', e);
      }
    },
    async fetchUsers() {
      try {
        const res = await apiClient.get('users/');
        this.users = res.data;
      } catch (e) {
        console.error('Ошибка загрузки пользователей', e);
      }
    },
    async fetchDeviceTypesAndLocations() {
      try {
        const [types, locs] = await Promise.all([
          apiClient.get('devicetypes/'),
          apiClient.get('locations/')
        ]);
        this.deviceTypes = types.data;
        this.locations = locs.data;
      } catch {
        this.error = 'Не удалось загрузить справочники.';
      }
    },
    async fetchDeviceForEdit(id) {
      this.loading = true;
      try {
        const res = await apiClient.get(`devices/${id}/`);
        const d = res.data;
        this.form = {
          ...d,
          device_type: d.device_type?.id,
          location: d.location?.id,
          owner: d.owner?.id || null,
          assigned_to: d.assigned_to?.id || null,
          computer_specs: d.computer_specs || { cpu: '', ram_gb: null },
          printer_scanner_specs: d.printer_scanner_specs || {
            printer_type: '',
            color_printing: false
          },
          network_specs: d.network_specs || { ports_count: null }
        };
        this.isEditing = true;
      } catch {
        this.error = 'Не удалось загрузить устройство для редактирования.';
      } finally {
        this.loading = false;
      }
    },
    async handleSubmit() {
      this.loading = true;
      this.error = null;
      const url = this.isEditing
        ? `devices/${this.deviceId}/`
        : 'devices/';
      const method = this.isEditing ? 'put' : 'post';
      const payload = {
        ...this.form,
        device_type: this.form.device_type ? parseInt(this.form.device_type) : null,
        location: this.form.location ? parseInt(this.form.location) : null,
        owner: this.form.owner ? parseInt(this.form.owner) : null,
        assigned_to: this.form.assigned_to ? parseInt(this.form.assigned_to) : null
      };

      try {
        await apiClient[method](url, payload);
        this.toast.add({
          severity: 'success',
          summary: this.isEditing ? 'Обновлено' : 'Создано',
          detail: 'Устройство сохранено успешно',
          life: 3000
        });
        this.$router.push('/devices');
      } catch (err) {
        console.error('Ошибка при сохранении:', err);
        this.error = err.response?.data?.detail || 'Ошибка при сохранении.';
      } finally {
        this.loading = false;
      }
    },
    handleDelete() {
      this.confirm.require({
        message: `Удалить устройство "${this.form.name}"?`,
        header: 'Подтверждение удаления',
        icon: 'pi pi-exclamation-triangle',
        acceptLabel: 'Удалить',
        rejectLabel: 'Отмена',
        acceptClass: 'p-button-danger',
        rejectClass: 'p-button-secondary p-button-outlined',
        accept: async () => {
          try {
            await apiClient.delete(`devices/${this.deviceId}/`);
            this.toast.add({
              severity: 'success',
              summary: 'Удалено',
              detail: 'Устройство успешно удалено',
              life: 3000
            });
            this.$router.push('/devices');
          } catch (e) {
            this.toast.add({
              severity: 'error',
              summary: 'Ошибка',
              detail: 'Не удалось удалить устройство',
              life: 3000
            });
          }
        },
        reject: () => {
          this.toast.add({
            severity: 'info',
            summary: 'Отменено',
            detail: 'Удаление отменено',
            life: 2000
          });
        }
      });
    }
  },
  async mounted() {
    await this.fetchCurrentUser();
    await this.fetchDeviceTypesAndLocations();
    await this.fetchUsers();
    if (this.deviceId) await this.fetchDeviceForEdit(this.deviceId);
  }
};
</script>

<style scoped>
.device-form {
  width: 100%;
  margin: 0;
  padding: 2rem;
  background-color: #ffffff;
  border-radius: 1rem;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.05);
  font-family: 'Inter', 'Segoe UI', Roboto, sans-serif;
  transition: all 0.3s ease;
}

.device-form:hover {
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
}

/* Заголовок */
.device-form h2 {
  font-size: 1.75rem;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 2rem;
  text-align: center;
}

/* Метки (labels) */
.device-form label {
  display: block;
  font-weight: 600;
  color: #334155;
  margin-bottom: 0.5rem;
  font-size: 1.05rem;
}

/* Поля ввода */
.device-form .p-inputtext,
.device-form .p-dropdown,
.device-form .p-inputtextarea {
  width: 100%;
  font-size: 1rem;
  padding: 0.8rem 1rem;
  border-radius: 0.5rem;
}

/* Отступы между полями */
.p-field {
  margin-bottom: 1.5rem;
}

/* Спецификации (разделители) */
.device-form h4 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1e293b;
  margin-top: 2rem;
  margin-bottom: 1rem;
  border-left: 4px solid #3b82f6;
  padding-left: 0.5rem;
}

/* Кнопки */
.device-form .p-button {
  font-weight: 600;
  border-radius: 0.5rem;
  transition: transform 0.2s ease;
  margin-inline: 1rem;
}

.device-form .p-button:hover {
  transform: translateY(-2px);
}

/* Основная кнопка */
.device-form .p-button-success {
  background-color: #22c55e !important;
  border: none;
  
}

.device-form .p-button-success:hover {
  background-color: #16a34a !important;
}

/* Вторичная кнопка */
.device-form .p-button-secondary {
  background-color: #e2e8f0 !important;
  color: #334155 !important;
  border: none;
}

.device-form .p-button-secondary:hover {
  background-color: #cbd5e1 !important;
  color: #1e293b !important;
}

/* Кнопка удаления */
.device-form .p-button-danger {
  background-color: #ef4444 !important;
  border: none;
}

.device-form .p-button-danger:hover {
  background-color: #dc2626 !important;
}

/* Сообщения */
.p-message {
  font-size: 1rem;
  border-radius: 0.5rem;
}

/* Сетка PrimeFlex */
@media (min-width: 768px) {
  .device-form form {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem 2rem;
  }

  .device-form form > div.col-12,
  .device-form form > div.p-field.p-mb-3:nth-last-child(-n+2) {
    grid-column: 1 / -1;
  }

  .device-form .p-d-flex {
    grid-column: 1 / -1;
    justify-content: center;
    gap: 1rem;
  }
}
</style>
