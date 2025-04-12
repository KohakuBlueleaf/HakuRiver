// src/main.js
import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import 'element-plus/dist/index.css';
import 'element-plus/theme-chalk/dark/css-vars.css'; // Import dark theme CSS variables

const app = createApp(App);

app.use(router);
app.mount('#app');
