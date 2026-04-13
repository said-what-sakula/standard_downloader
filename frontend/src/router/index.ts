import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../pages/Dashboard.vue'
import LogPage from '../pages/LogPage.vue'
import SchedulePage from '../pages/SchedulePage.vue'
import ConfigPage from '../pages/ConfigPage.vue'
import RecordsPage from '../pages/RecordsPage.vue'

const routes = [
  { path: '/',          redirect: '/records' },
  { path: '/records',   name: 'Records',   component: RecordsPage },
  { path: '/dashboard', name: 'Dashboard', component: Dashboard },
  { path: '/logs',      name: 'Logs',      component: LogPage },
  { path: '/schedule',  name: 'Schedule',  component: SchedulePage },
  { path: '/config',    name: 'Config',    component: ConfigPage },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
