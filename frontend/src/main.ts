import '@fontsource-variable/quicksand/wght.css'
import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'

import { library } from '@fortawesome/fontawesome-svg-core'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import { fas } from '@fortawesome/free-solid-svg-icons'

import { useUiStore } from './stores/ui'
import { installSessionFetchInterceptor } from './core/session'

library.add(fas)

installSessionFetchInterceptor()

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

app.component('FontAwesomeIcon', FontAwesomeIcon)

const uiStore = useUiStore(pinia)
uiStore.initialize()

app.mount('#app')
