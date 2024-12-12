import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import vuetify from 'vite-plugin-vuetify'

export default defineConfig({
  plugins: [
    vue(),
    vuetify({ autoImport: true })
],
  server: {
    // Optional: Configure server settings
    port: 3000, // Change to your desired port
    open: true, // Automatically open the app in the browser
  },
});