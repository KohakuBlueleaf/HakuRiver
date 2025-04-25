// src/router/index.js
import { createRouter, createWebHistory } from 'vue-router';
import HomeView from '../views/HomeView.vue'; // Example view

const routes = [
  {
    path: '/',
    name: 'home',
    component: HomeView,
  },
  {
    path: '/nodes',
    name: 'nodes',
    // Lazy-loaded component
    component: () => import('../views/NodesView.vue'),
  },
  {
    path: '/gpus', // New path for GPU view
    name: 'gpus',
    component: () => import('../views/GPUView.vue'), // Lazy-loaded GPU view
  },
  {
    path: '/tasks',
    name: 'tasks',
    // Lazy-loaded component
    component: () => import('../views/TasksView.vue'),
  },
  {
    path: '/docker',
    name: 'docker',
    component: () => import('../views/DockerView.vue'), // Assuming DockerView.vue will be the main view
  },
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL), // Use history mode
  routes,
});

export default router;
