import { createApp } from 'vue'
import App from './App.vue'
import router from './router' // Импортируем router
import PrimeVue from 'primevue/config';
import ToastService from 'primevue/toastservice';
import ConfirmationService from 'primevue/confirmationservice';

// 🎨 Подключаем тему для PrimeVue v4
import Theme from '@primevue/themes/lara';
// Или другая тема, например: import Aura from '@primevue/themes/nora';

import 'primeicons/primeicons.css';                 // Иконки
import 'primeflex/primeflex.css';                   // (опционально) утилиты верстки

const app = createApp(App)

app.use(router) // Используем router
app.use(PrimeVue, {
    theme: {
        preset: Theme,// Указываем выбранную тему
        options: {
            darkModeSelector: '.dark', // (опционально) класс для тёмного режима
            cssLayer: false,           // (опционально) использовать CSS layers
        }
    }
});
app.use(ToastService);
app.use(ConfirmationService);

app.mount('#app')
