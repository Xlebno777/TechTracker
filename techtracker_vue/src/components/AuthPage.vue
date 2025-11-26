<template>
  <div class="auth-wrapper">
    <div class="auth-card-container">
      <Card class="auth-card">
        <template #title>
          <div class="auth-title">
            <i class="pi pi-lock" style="font-size: 1.6rem; margin-right: 0.5rem;"></i>
            <span>Вход в систему</span>
          </div>
        </template>

        <template #content>
          <form @submit.prevent="handleSubmit">
            <div class="p-fluid">
              <div class="field mb-4">
                <label for="username" class="font-semibold block mb-2">Имя пользователя</label>
                <InputText id="username" v-model="form.username" class="w-full p-inputtext-lg" placeholder="Введите логин" />
              </div>

              <div class="field mb-4">
                <label for="password" class="font-semibold block mb-2">Пароль</label>
                <Password id="password" v-model="form.password" :feedback="false" toggleMask class="w-full" inputClass="w-full p-inputtext-lg" placeholder="Введите пароль" />
              </div>

              <Button type="submit" label="Войти" icon="pi pi-sign-in" class="w-full p-button-lg" :loading="loading" />
            </div>
          </form>

          <Message v-if="error" severity="error" class="mt-3" :closable="false">{{ error }}</Message>
        </template>
      </Card>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import Card from "primevue/card";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import Button from "primevue/button";
import Message from "primevue/message";

const router = useRouter();
const auth = useAuthStore();

const form = ref({ username: "", password: "" });
const loading = ref(false);
const error = ref(null);

const handleSubmit = async () => {
  loading.value = true;
  error.value = null;
  try {
    await auth.login(form.value.username, form.value.password);
    router.push("/devices");
  } catch (err) {
    console.error(err);
    error.value = "Неверное имя пользователя или пароль";
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
.auth-wrapper {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at center, #f0f9ff 0%, #e0f2fe 100%);
}

.auth-card-container {
  width: 100%;
  max-width: 400px;
  padding: 1rem;
}

.auth-card {
  border: none;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.08);
  border-radius: 16px;
}

.auth-title {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #0f172a;
  margin-bottom: 1rem;
}
</style>