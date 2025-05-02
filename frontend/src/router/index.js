// src/router/index.js
import { createRouter, createWebHistory } from 'vue-router';
import HomeView from '../views/HomeView.vue';

const routes = [
  {
    path: '/',
    name: 'home',
    component: HomeView,
  },
  {
    path: '/nodes',
    name: 'nodes',
    component: () => import('../views/NodesView.vue'),
  },
  {
    path: '/gpus',
    name: 'gpus',
    component: () => import('../views/GPUView.vue'),
  },
  {
    path: '/tasks',
    name: 'tasks',
    component: () => import('../views/TasksView.vue'),
  },
  {
    path: '/docker',
    name: 'docker',
    component: () => import('../views/DockerView.vue'),
  },
  {
    path: '/vps', // NEW path for VPS view
    name: 'vps',
    component: () => import('../views/VPSView.vue'), // Lazy-loaded VPS view
  },
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});

export default router;
