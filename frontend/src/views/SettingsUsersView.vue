<script setup lang="ts">
import {
    onMounted,
    reactive,
    ref,
} from 'vue'

import {
    useUsersStore,
    type UserRole,
} from '@/stores/users'


const usersStore = useUsersStore()

const createOpen = ref(false)
const error = ref<string | null>(null)


const form = reactive({
  username: '',
  display_name: '',
  email: '',
  password: '',
  role: 'viewer' as UserRole,
  is_active: true,
})

const passwordUserId =
    ref<string | null>(null)

const passwordUsername =
    ref('')

const newPassword =
    ref('')

const passwordError =
    ref<string | null>(null)


function resetForm() {
    form.username = ''
    form.display_name = ''
    form.email = ''
    form.password = ''
    form.role = 'viewer'
    form.is_active = true

    error.value = null
}

function openPasswordReset(
    id: string,
    username: string,
) {
    passwordUserId.value = id
    passwordUsername.value = username
    newPassword.value = ''
    passwordError.value = null
}


function closePasswordReset() {
    passwordUserId.value = null
    passwordUsername.value = ''
    newPassword.value = ''
    passwordError.value = null
}


async function resetPassword() {
    if (!passwordUserId.value) {
        return
    }

    passwordError.value = null

    try {
        await usersStore.resetPassword(
            passwordUserId.value,
            newPassword.value,
        )

        closePasswordReset()

    } catch (cause) {
        passwordError.value =
            cause instanceof Error
                ? cause.message
                : 'Unable to reset password.'
    }
}


async function createUser() {
    error.value = null

    try {
        await usersStore.create({
            username:
                form.username.trim(),

            display_name:
                form.display_name.trim() || null,

            email:
                form.email.trim() || null,

            password:
                form.password,

            role:
                form.role,

            is_active: form.is_active,
        })

        createOpen.value = false
        resetForm()

    } catch (cause) {
        error.value =
            cause instanceof Error
                ? cause.message
                : 'Unable to create user.'
    }
}

async function changeEnabled(
  id: string,
  role: UserRole,
  isActive: boolean,
) {
  try {
    await usersStore.update(
      id,
      {
        role,
        is_active: isActive,
      },
    )
  } catch (cause) {
    window.alert(
      cause instanceof Error
        ? cause.message
        : 'Unable to update user.',
    )

    await usersStore.load()
  }
}


async function changeRole(
  id: string,
  role: UserRole,
  isActive: boolean,
) {
  try {
    await usersStore.update(
      id,
      {
        role,
        is_active: isActive,
      },
    )
  } catch (cause) {
    window.alert(
      cause instanceof Error
        ? cause.message
        : 'Unable to update user.',
    )

    await usersStore.load()
  }
}


async function removeUser(
    id: string,
    username: string,
) {
    if (
        !window.confirm(
            `Delete "${username}"?`,
        )
    ) {
        return
    }

    try {
        await usersStore.remove(id)

    } catch (cause) {
        window.alert(
            cause instanceof Error
                ? cause.message
                : 'Unable to delete user.',
        )
    }
}


onMounted(() => {
    usersStore.load()
})
</script>

<template>
    <section class="page-header">
        <div>
            <h2>Users</h2>

            <p>
                Local DBAChum accounts and roles.
            </p>
        </div>

        <button type="button" class="primary-button" @click="createOpen = true">
            Add user
        </button>
    </section>

    <p v-if="usersStore.loading">
        Loading users...
    </p>

    <p v-else-if="usersStore.error" class="login-error">
        {{ usersStore.error }}
    </p>

    <div v-else class="utility-table-wrap">
        <table class="utility-table">
            <thead>
                <tr>
                    <th>Display name</th>
                    <th>Username</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>

            <tbody>
                <tr v-for="user in usersStore.users" :key="user.id">
                    <td>
                        <strong>{{ user.display_name }}</strong>
                    </td>

                    <td>
                        {{ user.username }}
                    </td>

                    <td>
                        {{ user.email || '—' }}
                    </td>

                    <td>
                        <select :value="user.role" @change="
                            changeRole(
                                user.id,
                                ($event.target as HTMLSelectElement)
                                    .value as UserRole,
                                user.is_active,
                            )
                            ">
                            <option value="viewer">
                                Viewer
                            </option>

                            <option value="operator">
                                Operator
                            </option>

                            <option value="admin">
                                Admin
                            </option>
                        </select>
                    </td>

                    <td>
                        <label class="connection-checkbox">
                            <input type="checkbox" :checked="user.is_active" @change="
                                changeEnabled(
                                    user.id,
                                    user.role,
                                    ($event.target as HTMLInputElement)
                                        .checked,
                                )
                                " />

                            {{
                                user.is_active
                                    ? 'Enabled'
                                    : 'Disabled'
                            }}
                        </label>
                    </td>

                    <td>
                        <button type="button" class="secondary-button" @click="
                            removeUser(
                                user.id,
                                user.username,
                            )
                            ">
                            Delete
                        </button>
                        <button type="button" class="secondary-button" @click="
                            openPasswordReset(
                                user.id,
                                user.username,
                            )
                            ">
                            Reset password
                        </button>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>

    <div v-if="createOpen" class="modal-backdrop" @click.self="
        createOpen = false
        ">
        <section class="modal-panel">
            <div class="modal-header">
                <div>
                    <h2>Add user</h2>

                    <p>
                        Create a local DBAChum account.
                    </p>
                </div>

                <button type="button" class="modal-close" @click="
                    createOpen = false
                    ">
                    ×
                </button>
            </div>

            <form class="connection-form" @submit.prevent="createUser">
                <label>
                    Username

                    <input v-model="form.username" required minlength="3" autocomplete="off" />
                </label>

                <label>
                    Display name

                    <input v-model="form.display_name" maxlength="120" autocomplete="name" placeholder="Optional; defaults to username" />
                </label>

                <label>
                    Email

                    <input v-model="form.email" type="email" maxlength="254" autocomplete="email" placeholder="Optional; used for future alert subscriptions" />
                </label>

                <label>
                    Password

                    <input v-model="form.password" required minlength="12" type="password" autocomplete="new-password" />
                </label>

                <label>
                    Role

                    <select v-model="form.role">
                        <option value="viewer">
                            Viewer
                        </option>

                        <option value="operator">
                            Operator
                        </option>

                        <option value="admin">
                            Admin
                        </option>
                    </select>
                </label>

                <label class="connection-checkbox">
                    <input v-model="form.is_active" type="checkbox" />

                    Enabled
                </label>

                <p v-if="error" class="login-error">
                    {{ error }}
                </p>

                <div class="connection-form-actions">
                    <button type="submit" class="primary-button" :disabled="usersStore.saving">
                        {{
                            usersStore.saving
                                ? 'Creating...'
                                : 'Add user'
                        }}
                    </button>

                    <button type="button" class="secondary-button" @click="
                        createOpen = false
                        ">
                        Cancel
                    </button>
                </div>
            </form>
        </section>
    </div>
    <div
  v-if="passwordUserId"
  class="modal-backdrop"
  @click.self="closePasswordReset"
>
  <section
    class="modal-panel"
    role="dialog"
    aria-modal="true"
  >
    <div class="modal-header">
      <div>
        <h2>Reset password</h2>

        <p>
          {{ passwordUsername }}
        </p>
      </div>

      <button
        type="button"
        class="modal-close"
        @click="closePasswordReset"
      >
        ×
      </button>
    </div>

    <form
      class="connection-form"
      @submit.prevent="resetPassword"
    >
      <label>
        New password

        <input
          v-model="newPassword"
          type="password"
          required
          minlength="12"
          autocomplete="new-password"
        />
      </label>

      <p
        v-if="passwordError"
        class="login-error"
      >
        {{ passwordError }}
      </p>

      <div class="connection-form-actions">
        <button
          type="submit"
          class="primary-button"
        >
          Reset password
        </button>

        <button
          type="button"
          class="secondary-button"
          @click="closePasswordReset"
        >
          Cancel
        </button>
      </div>
    </form>
  </section>
</div>
</template>