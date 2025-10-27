// frontend/src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'
import DeviceList from '../components/DeviceList.vue'
import DeviceForm from '../components/DeviceForm.vue'

const routes = [
  {
    path: '/',
    redirect: '/devices' // Перенаправляем с главной на список устройств
  },
  {
    path: '/devices',
    name: 'DeviceList',
    component: DeviceList
  },
  {
    path: '/device/create',
    name: 'DeviceCreate',
    component: DeviceForm
    // props: { deviceId: null } // Явно передаем null для deviceId
  },
  {
    path: '/device/edit/:deviceId',
    name: 'DeviceEdit',
    component: DeviceForm,
    props: true // Передаем :deviceId как prop в компонент
  }
]

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes
})

export default router