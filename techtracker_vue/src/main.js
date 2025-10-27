import { createApp } from 'vue'
import App from './App.vue'
import router from './router' // Импортируем router

// 👇 Добавь эту строку для подключения Bootstrap CSS
import 'bootstrap/dist/css/bootstrap.min.css'

const app = createApp(App)
app.use(router) // Используем router
app.mount('#app')
