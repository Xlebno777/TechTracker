<template>
  <div class="request-form p-fluid p-p-4">
    <h2 class="form-title">{{ isEditing ? 'Редактировать заявку' : 'Создать заявку' }}</h2>

    <form @submit.prevent="submitRequest">
      <div class="p-field p-mb-3">
        <label for="message" class="p-field-label">Сообщение</label>
        <Textarea
          id="message"
          v-model="form.message"
          rows="4"
          autoResize
          placeholder="Опишите проблему или запрос..."
        />
      </div>

      <div class="p-field p-mb-3">
        <label for="device" class="p-field-label">Устройство</label>
        <Dropdown
          id="device"
          v-model="form.device"
          :options="devices"
          optionLabel="name"
          optionValue="id"
          placeholder="Выберите устройство"
          required
        />
      </div>

      <div class="p-field p-mb-3">
        <label for="priority" class="p-field-label">Приоритет</label>
        <Dropdown
          id="priority"
          v-model="form.priority"
          :options="priorityOptions"
          optionLabel="label"
          optionValue="value"
        />
      </div>

      <!-- Кнопки -->
      <div class="form-buttons">
        <Button
          type="submit"
          label="Сохранить"
          class="p-button p-button-success"
          icon="pi pi-check"
          :loading="loading"
        />
        <Button
          label="Отмена"
          icon="pi pi-times"
          class="p-button p-button-secondary"
          @click="$router.push('/devices')"
        />
      </div>
    </form>

    <Message v-if="error" severity="error" :text="error" class="p-mt-3" />
    <Toast />
  </div>
</template>

<script>
import apiClient from '@/api';
import Textarea from 'primevue/textarea';
import Dropdown from 'primevue/dropdown';
import Button from 'primevue/button';
import Message from 'primevue/message';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';

export default {
  name: 'RequestForm',
  components: {
    Textarea,
    Dropdown,
    Button,
    Message,
    Toast,
  },
  data() {
    return {
      isEditing: false,
      form: {
        message: '',
        device: null,
        priority: 'medium',
      },
      devices: [],
      priorityOptions: [
        { label: 'Низкий', value: 'low' },
        { label: 'Средний', value: 'medium' },
        { label: 'Высокий', value: 'high' },
        { label: 'Критический', value: 'critical' },
      ],
      loading: false,
      error: null,
    };
  },
  setup() {
    const toast = useToast();
    return { toast };
  },
  methods: {
    async fetchDevices() {
      const res = await apiClient.get('devices/');
      this.devices = res.data;
    },
    async submitRequest() {
      this.loading = true;
      try {
        await apiClient.post('logs/', {
          ...this.form,
          log_type: 'request',
        });
        this.toast.add({
          severity: 'success',
          summary: 'Успех',
          detail: 'Заявка успешно отправлена',
          life: 3000,
        });
        this.$router.push('/devices');
      } catch (err) {
        this.error = 'Ошибка при создании заявки.';
      } finally {
        this.loading = false;
      }
    },
  },
  async mounted() {
    await this.fetchDevices();
  },
};
</script>

<style scoped>
.request-form {
  max-width: 600px;
  margin: 0 auto;
  background: rgba(255, 255, 255, 0.85);
  padding: 2rem 2.5rem;
  border-radius: 1rem;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.05);
  backdrop-filter: blur(10px);
  font-family: 'Inter', sans-serif;
}

.form-title {
  text-align: center;
  margin-bottom: 1.5rem;
  font-weight: 600;
  font-size: 1.5rem;
  color: #2c3e50;
}

.p-field-label {
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: #374151;
}

.p-inputtext,
.p-dropdown,
.p-inputtextarea {
  border-radius: 0.5rem;
  padding: 0.75rem;
}

.form-buttons {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  margin-top: 2rem;
}
</style>
