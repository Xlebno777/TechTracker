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
          <form @submit.prevent="submitAuth">
            <div class="p-fluid p-formgrid p-grid">

              <!-- Username -->
              <div class="p-field p-col-12 inputtext">
                <label for="username" class="form-label">Имя пользователя</label>
                <span class="p-input-icon-left">
                  <InputText
                    id="username"
                    v-model="form.username"
                    required
                    placeholder="Введите логин"
                    fluid
                    class="p-inputtext-lg"
                  />
                </span>
              </div>

              <!-- Password -->
              <div class="p-field p-col-12 inputtext">
                <label for="password" class="form-label">Пароль</label>
                <Password
                  id="password"
                  v-model="form.password"
                  required
                  :feedback="false"
                  toggleMask
                  fluid
                  inputClass="p-inputtext-lg"
                  placeholder="Введите пароль"
                />
              </div>

              <!-- Submit button -->
              <div class="p-col-12 p-mt-3">
                <Button
                  type="submit"
                  label="Войти"
                  icon="pi pi-sign-in"
                  class="p-button-rounded p-button-primary p-button-lg w-full"
                  :loading="loading"
                />
              </div>
            </div>
          </form>

          <Message
            v-if="error"
            severity="error"
            class="p-mt-3"
          >
            {{ error }}
          </Message>
        </template>
      </Card>
    </div>
  </div>
</template>

<script>
import apiClient from '@/api';
import Card from "primevue/card";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import Button from "primevue/button";
import Message from "primevue/message";

export default {
  name: "AuthPage",
  components: {
    Card,
    InputText,
    Password,
    Button,
    Message
  },
  data() {
    return {
      form: {
        username: "",
        password: "",
      },
      loading: false,
      error: null,
    };
  },
  methods: {
    async submitAuth() {
      this.loading = true;
      this.error = null;

      try {
        const response = await apiClient.post("auth/login/", {
          username: this.form.username,
          password: this.form.password,
        });

        const token = response.data.key;
        if (token) {
          localStorage.setItem("auth_token", token);

          // ✅ Сразу после логина грузим данные пользователя
          const userResponse = await apiClient.get("users/me/");
          localStorage.setItem("current_user", JSON.stringify(userResponse.data));

          // 🔥 Обновляем глобальное состояние в App.vue
          this.$root.refreshUser?.();
        }

        // ✅ Обновляем App.vue через event (обработаю ниже)
        this.$emit('auth-success')

        this.$router.push("/devices");
      } catch (err) {
        console.error("Ошибка аутентификации:", err);
        let errorMessage = 'Произошла ошибка.';
        if (err.response) {
          if (err.response.status === 400) {
            errorMessage = 'Неверное имя пользователя или пароль.';
          } else if (err.response.status === 403) {
            errorMessage = 'Доступ запрещён.';
          } else if (err.response.status === 500) {
            errorMessage = 'Внутренняя ошибка сервера.';
          }
        }
        this.error = errorMessage;
      } finally {
        this.loading = false;
      }
    },
  },
};
</script>

<style scoped>
.auth-wrapper {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #e3eeff, #f7faff, #eef3ff);
  background-size: 200% 200%;
  animation: gradientMove 8s ease infinite;
  padding: 1rem;
}

@keyframes gradientMove {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

.auth-card-container {
  width: 100%;
  max-width: 430px;
}

.auth-card {
  border-radius: 18px;
  padding: 1rem;
  box-shadow: 0 10px 35px rgba(0, 0, 0, 0.08);
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  animation: fadeIn 0.6s ease-out;
}

.auth-title {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.4rem;
  font-weight: 600;
  color: #1f2937;
}

.form-label {
  font-weight: 600;
  margin-bottom: 0.4rem;
  display: block;
}

.inputtext{
  margin-bottom: 2rem;
  margin-top: 2rem;
}

.w-full {
  width: 100%;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
