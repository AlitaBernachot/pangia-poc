import { createApp } from 'vue'
import PrimeVue from 'primevue/config'
import { definePreset } from '@primevue/themes'
import Aura from '@primevue/themes/aura'
import App from './App.vue'
import './assets/main.css'

const YellowAura = definePreset(Aura, {
  semantic: {
    primary: {
      50:  '{yellow.50}',
      100: '{yellow.100}',
      200: '{yellow.200}',
      300: '{yellow.300}',
      400: '{yellow.400}',
      500: '{yellow.500}',
      600: '{yellow.600}',
      700: '{yellow.700}',
      800: '{yellow.800}',
      900: '{yellow.900}',
      950: '{yellow.950}',
    },
  },
})

createApp(App)
  .use(PrimeVue, {
    theme: {
      preset: YellowAura,
      options: {
        darkModeSelector: '.dark',
        cssLayer: { name: 'primevue', order: 'tailwind-base, primevue, tailwind-utilities' },
      },
    },
  })
  .mount('#app')
