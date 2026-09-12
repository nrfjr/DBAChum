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
import { confirmDialog, showToast } from '@/ui/feedback'
import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import FloatingActionMenu from '@/components/common/FloatingActionMenu.vue'


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

        const username = passwordUsername.value
        closePasswordReset()
        showToast({ title: 'Password reset', message: username, tone: 'success' })

    } catch (cause) {
        const message = cause instanceof Error ? cause.message : 'Unable to reset password.'
        passwordError.value = message
        showToast({ title: 'Unable to reset password', message, tone: 'danger' })
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

        const username = form.username.trim()
        createOpen.value = false
        resetForm()
        showToast({ title: 'User created', message: username, tone: 'success' })

    } catch (cause) {
        const message = cause instanceof Error ? cause.message : 'Unable to create user.'
        error.value = message
        showToast({ title: 'Unable to create user', message, tone: 'danger' })
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
        showToast({ title: isActive ? 'User enabled' : 'User disabled', tone: 'success' })
    } catch (cause) {
        showToast({ title: 'Unable to update user', message: cause instanceof Error ? cause.message : undefined, tone: 'danger' })

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
        showToast({ title: 'User role updated', message: role, tone: 'success' })
    } catch (cause) {
        showToast({ title: 'Unable to update user', message: cause instanceof Error ? cause.message : undefined, tone: 'danger' })

        await usersStore.load()
    }
}


async function removeUser(
    id: string,
    username: string,
) {
    if (
        !(await confirmDialog({ title: 'Delete DBAChum user', message: username, confirmLabel: 'Delete user', destructive: true, tone: 'danger' }))
    ) {
        return
    }

    try {
        await usersStore.remove(id)
        showToast({ title: 'User deleted', message: username, tone: 'success' })

    } catch (cause) {
        showToast({ title: 'Unable to delete user', message: cause instanceof Error ? cause.message : undefined, tone: 'danger' })
    }
}


onMounted(() => {
    usersStore.load()
})
</script>

<template>
    <section class="page-header alert-header-list">
        <div>
        </div>
        <button type="button" class="primary-button" @click="createOpen = true">
            Add user
        </button>
    </section>

    <div v-if="usersStore.loading">
        Loading users
        <p class="loading"></p>
    </div>

    <p v-else-if="usersStore.error" class="login-error">
        {{ usersStore.error }}
    </p>

    <ScrollableDataTable v-else max-height="34rem">
        <template #header>
            <tr>
                <th>Display name</th>
                <th>Username</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th class="user-actions-column">Actions</th>
            </tr>
        </template>
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
                <select class="secondary-button" :value="user.role" @change="
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
                    <input type="checkbox" class="toggle-switch" :checked="user.is_active" @change="
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

            <td class="user-actions-cell">
                <FloatingActionMenu :label="`Actions for ${user.username}`">
                    <button type="button" role="menuitem" @click="openPasswordReset(user.id, user.username)">
                        <FontAwesomeIcon icon="key" />
                        Reset password
                    </button>
                    <button type="button" role="menuitem" class="danger-menu-item"
                        @click="removeUser(user.id, user.username)">
                        <FontAwesomeIcon icon="trash-can" />
                        Delete
                    </button>
                </FloatingActionMenu>
            </td>
        </tr>
    </ScrollableDataTable>

    <div v-if="createOpen" class="modal-backdrop" @click.self="
        createOpen = false
        ">
        <section class="modal-panel" style="--modal-width: 400px;">
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
                    <span class="field-label">Username <span class="required-mark" aria-hidden="true">*</span></span>
                    <input v-model="form.username" required minlength="3" autocomplete="off" />
                </label>

                <label>
                    Display name (Optional)

                    <input v-model="form.display_name" maxlength="120" autocomplete="name"
                        placeholder="defaults to username" />
                </label>

                <label>
                    Email (Optional)

                    <input v-model="form.email" type="email" maxlength="254" autocomplete="email"
                        placeholder="Used for future alert subscriptions" />
                </label>

                <label>
                    <span class="field-label">Password <span class="required-mark" aria-hidden="true">*</span></span>
                    <input v-model="form.password" required minlength="12" maxlength="128" type="password"
                        autocomplete="new-password" />
                </label>

                <label>
                    <span class="field-label">Role <span class="required-mark" aria-hidden="true">*</span></span>
                    <select v-model="form.role" required>
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
                    <input v-model="form.is_active" type="checkbox" class="toggle-switch" />

                    Enabled
                </label>

                <p v-if="error" class="login-error">
                    {{ error }}
                </p>

                <div class="connection-form-actions">
                    <button type="submit" class="primary-button" :disabled="usersStore.saving">
                        {{
                            usersStore.saving
                                ? 'Creating'
                                : 'Add user'
                        }}
                        <p v-if="usersStore.saving" class="loading"></p>
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
    <div v-if="passwordUserId" class="modal-backdrop" @click.self="closePasswordReset">
        <section class="modal-panel" role="dialog" aria-modal="true">
            <div class="modal-header">
                <div>
                    <h2>Reset password</h2>

                    <p>
                        {{ passwordUsername }}
                    </p>
                </div>

                <button type="button" class="modal-close" @click="closePasswordReset">
                    ×
                </button>
            </div>

            <form class="connection-form" @submit.prevent="resetPassword">
                <label>
                    <span class="field-label">New password <span class="required-mark"
                            aria-hidden="true">*</span></span>
                    <input v-model="newPassword" type="password" required minlength="12" maxlength="128"
                        autocomplete="new-password" />
                </label>

                <p v-if="passwordError" class="login-error">
                    {{ passwordError }}
                </p>

                <div class="connection-form-actions">
                    <button type="submit" class="primary-button">
                        Reset password
                    </button>

                    <button type="button" class="secondary-button" @click="closePasswordReset">
                        Cancel
                    </button>
                </div>
            </form>
        </section>
    </div>

</template>