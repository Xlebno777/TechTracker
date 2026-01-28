<template>
  <div class="form-container page-shell">
    <div class="card p-5 shadow-2 border-round bg-white form-card">
      <h2 class="text-center mb-5 text-800">Создание заявки</h2>
      
      <form @submit.prevent="submitRequest" class="p-fluid">
        <!-- Сообщение -->
        <div class="field mb-4">
          <label for="message" class="font-semibold mb-2 block">Сообщение</label>
          <Textarea 
            id="message" 
            v-model="form.message" 
            rows="4" 
            autoResize 
            placeholder="Опишите проблему..." 
            class="w-full" 
            :class="{'p-invalid': submitted && !form.message}"
          />
          <small v-if="submitted && !form.message" class="p-error">Введите сообщение</small>
        </div>

        <!-- Устройство -->
        <div class="field mb-4">
          <label for="device" class="font-semibold mb-2 block">Устройство</label>
          <Dropdown 
            id="device" 
            v-model="form.device" 
            :options="devices" 
            optionLabel="name" 
            optionValue="id" 
            placeholder="Выберите устройство" 
            filter 
            class="w-full"
            :class="{'p-invalid': submitted && !form.device}"
          />
          <small v-if="submitted && !form.device" class="p-error">Выберите устройство</small>
        </div>

        <!-- Приоритет -->
        <div class="field mb-5">
          <label for="priority" class="font-semibold mb-2 block">Приоритет</label>
          <Dropdown 
            id="priority" 
            v-model="form.priority" 
            :options="priorityOptions" 
            optionLabel="label" 
            optionValue="value" 
            class="w-full" 
          />
        </div>

        <!-- Кнопки -->
        <div class="flex justify-content-center gap-3">
          <Button label="Отмена" icon="pi pi-times" severity="secondary" outlined @click="$router.push('/devices')" />
          <Button type="submit" label="Отправить" icon="pi pi-send" :loading="loading" />
        </div>
      </form>
    </div>
    <Toast />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import apiClient from '@/api';
import { useToast } from 'primevue/usetoast';
import Textarea from 'primevue/textarea';
import Dropdown from 'primevue/dropdown';
import Button from 'primevue/button';
import Toast from 'primevue/toast';

const router = useRouter();
const toast = useToast();

const devices = ref([]);
const loading = ref(false);
const submitted = ref(false); // Для валидации

// Начальное состояние формы
const form = ref({ 
  message: '', 
  device: null, 
  priority: 'medium' // Значение по умолчанию должно совпадать с value в priorityOptions
});

const priorityOptions = [
    { label: 'Низкий', value: 'low' },
    { label: 'Средний', value: 'medium' },
    { label: 'Высокий', value: 'high' },
    { label: 'Критический', value: 'critical' }
];

const fetchDevices = async () => {
    try {
        const res = await apiClient.get('devices/');
        devices.value = res.data;
    } catch (e) {
        console.error(e);
        toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось загрузить список устройств' });
    }
};

const submitRequest = async () => {
    submitted.value = true;

    // Валидация
    if (!form.value.message || !form.value.device) {
        toast.add({ severity: 'warn', summary: 'Внимание', detail: 'Заполните обязательные поля', life: 3000 });
        return;
    }

    loading.value = true;
    
    // Формируем чистый payload
    const payload = {
        message: form.value.message,
        device: form.value.device,
        priority: form.value.priority, // Убедимся, что отправляется строка 'high', 'medium' и т.д.
        log_type: 'request'
    };

    try {
        await apiClient.post('logs/', payload);
        toast.add({ severity: 'success', summary: 'Успех', detail: 'Заявка отправлена', life: 2000 });
        
        // Небольшая задержка для UX перед переходом
        setTimeout(() => router.push('/devices'), 1000);
    } catch (e) {
        console.error(e);
        toast.add({ severity: 'error', summary: 'Ошибка', detail: 'Не удалось отправить заявку', life: 3000 });
    } finally {
        loading.value = false;
    }
};

onMounted(() => {
    fetchDevices();
});
</script>

<style scoped>
.form-container {
    width: 100%;
    margin: 0;
    padding: 0;
}
.form-card {
    width: 100%;
}
</style>
