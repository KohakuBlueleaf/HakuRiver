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
    path: '/tasks',
    name: 'tasks',
    // Lazy-loaded component
    component: () => import('../views/TasksView.vue'),
  },
  // Add other routes as needed
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL), // Use history mode
  routes,
});

export default router;
