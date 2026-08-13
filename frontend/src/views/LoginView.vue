<script setup lang="ts">
import { ref } from 'vue'
import {
  useRoute,
  useRouter,
} from 'vue-router'

import { useAuthStore } from '@/stores/auth'


const router = useRouter()
const route = useRoute()

const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')


async function submit() {
  error.value = ''

  try {
    await authStore.login({
      username: username.value,
      password: password.value,
    })

    const redirect =
      typeof route.query.redirect === 'string'
        ? route.query.redirect
        : '/'

    await router.push(redirect)
  } catch {
    error.value =
      'Invalid username or password.'
  }
}
</script>


<template>
  <main class="login-page">
    <section class="login-card">
      <div class="login-brand">
        <div class="brand__logo">
          D
        </div>

        <div>
          <strong>DBAChum</strong>
          <span>
            Database workspace
          </span>
        </div>
      </div>

      <div class="login-heading">
        <h1>Welcome back</h1>

        <p>
          Sign in to continue to DBAChum.
        </p>
      </div>

      <form
        class="login-form"
        @submit.prevent="submit"
      >
        <label>
          <span>Username</span>

          <input
            v-model="username"
            type="text"
            autocomplete="username"
            required
          />
        </label>

        <label>
          <span>Password</span>

          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
          />
        </label>

        <p
          v-if="error"
          class="login-error"
        >
          {{ error }}
        </p>

        <button
          class="primary-button login-submit"
          type="submit"
          :disabled="authStore.loading"
        >
          {{
            authStore.loading
              ? 'Signing in...'
              : 'Sign in'
          }}
        </button>
      </form>
    </section>
  </main>
</template>