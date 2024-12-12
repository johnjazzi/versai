import './style.css'
import { createApp } from 'vue';
import App from './App.vue';
import { createVuetify } from 'vuetify'; // Import Vuetify
import 'vuetify/styles'; // Import Vuetify styles

const vuetify = createVuetify(); // Create Vuetify instance

createApp(App).use(vuetify).mount('#app'); // Use Vuetify in the app
