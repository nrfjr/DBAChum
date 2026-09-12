<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'

import {
  dialogState,
  resolveDialog,
  type DialogField,
  type DialogResult,
} from '@/ui/feedback'

const values = reactive<DialogResult>({})
const sizeModes = reactive<Record<string, string>>({})
const customSizeGb = reactive<Record<string, number | null>>({})
const validationError = ref<string | null>(null)
const dialogPanel = ref<HTMLElement | null>(null)

const request = computed(() => dialogState.request)
const fields = computed(() => request.value?.fields ?? [])
const dialogStyle = computed<Record<string, string>>(() => ({
  '--app-dialog-width': request.value?.width ?? '34rem',
}))

function sizePresets(field: DialogField) {
  return field.presetsGb?.length ? field.presetsGb : [10, 20, 30]
}

function initializeField(field: DialogField) {
  const value = field.value ?? (field.type === 'checkbox' ? false : '')
  values[field.name] = value

  if (field.type !== 'size-gb') return

  const currentMb = typeof value === 'number' ? value : Number(value || 0)
  const matched = sizePresets(field).find((gb) => gb * 1024 === currentMb)
  if (matched) {
    sizeModes[field.name] = String(matched)
    customSizeGb[field.name] = matched
    return
  }

  const currentGb = currentMb > 0 ? Math.round((currentMb / 1024) * 10) / 10 : null
  const safePreset = sizePresets(field).find((gb) => gb * 1024 >= (field.minMb ?? 0))
  if (currentGb && currentMb >= (field.minMb ?? 0)) {
    sizeModes[field.name] = 'custom'
    customSizeGb[field.name] = currentGb
  } else if (safePreset != null) {
    sizeModes[field.name] = String(safePreset)
    customSizeGb[field.name] = safePreset
  } else {
    sizeModes[field.name] = 'custom'
    customSizeGb[field.name] = currentGb ?? 10
  }
}

watch(
  () => dialogState.requestId,
  async () => {
    validationError.value = null
    for (const key of Object.keys(values)) delete values[key]
    for (const key of Object.keys(sizeModes)) delete sizeModes[key]
    for (const key of Object.keys(customSizeGb)) delete customSizeGb[key]
    for (const field of fields.value) initializeField(field)
    await nextTick()
    dialogPanel.value?.focus()
  },
)

function controlValue(value: DialogResult[string] | undefined) {
  if (value == null || typeof value === 'boolean') return ''
  return value
}

function setControlValue(name: string, event: Event) {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
  values[name] = target.value
}

function setCheckboxValue(name: string, event: Event) {
  values[name] = (event.target as HTMLInputElement).checked
}

function cancel() {
  resolveDialog(null)
}

function submit() {
  validationError.value = null
  const result: DialogResult = {}

  for (const field of fields.value) {
    let value = values[field.name]

    if (field.type === 'size-gb') {
      const mode = sizeModes[field.name]
      const gb = mode === 'custom' ? customSizeGb[field.name] : Number(mode)
      if (gb == null || !Number.isFinite(gb) || gb <= 0) {
        validationError.value = `${field.label} must be greater than 0 GB.`
        return
      }
      value = Math.round(gb * 1024)
      if (field.minMb != null && Number(value) < field.minMb) {
        validationError.value = `${field.label} cannot be smaller than the current size.`
        return
      }
    }

    if (field.type === 'number' && value !== '' && value != null) {
      const numeric = Number(value)
      if (!Number.isFinite(numeric)) {
        validationError.value = `${field.label} must be a valid number.`
        return
      }
      if (field.min != null && numeric < field.min) {
        validationError.value = `${field.label} must be at least ${field.min}.`
        return
      }
      if (field.max != null && numeric > field.max) {
        validationError.value = `${field.label} must be at most ${field.max}.`
        return
      }
      value = numeric
    }

    if (field.required && (value == null || String(value).trim() === '')) {
      validationError.value = `${field.label} is required.`
      return
    }

    result[field.name] = value ?? null
  }

  resolveDialog(result)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    cancel()
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="dialogState.open && request" class="app-dialog-backdrop" @mousedown.self="cancel">
      <section
        ref="dialogPanel"
        class="app-dialog"
        :class="[`app-dialog--${request.tone ?? 'default'}`, { 'app-dialog--destructive': request.destructive }]"
        :style="dialogStyle"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="`dialog-title-${dialogState.requestId}`"
        tabindex="-1"
        @keydown="onKeydown"
      >
        <header class="app-dialog__header">
          <div>
            <h2 :id="`dialog-title-${dialogState.requestId}`">{{ request.title }}</h2>
            <p v-if="request.message">{{ request.message }}</p>
          </div>
          <button type="button" class="icon-button app-dialog__close" aria-label="Close dialog" @click="cancel">×</button>
        </header>

        <form class="app-dialog__body" @submit.prevent="submit">
          <div v-for="field in fields" :key="field.name" class="app-dialog-field">
            <label :for="`dialog-${dialogState.requestId}-${field.name}`">
              <span>{{ field.label }}</span><span v-if="field.required" class="required-mark" aria-hidden="true">*</span>
            </label>

            <template v-if="field.type === 'checkbox'">
              <label class="app-dialog-checkbox">
                <input :checked="Boolean(values[field.name])" type="checkbox" class="toggle-switch" @change="setCheckboxValue(field.name, $event)" />
                <span>{{ field.hint ?? field.label }}</span>
              </label>
            </template>

            <template v-else-if="field.type === 'select'">
              <select :id="`dialog-${dialogState.requestId}-${field.name}`" :value="controlValue(values[field.name])" :required="field.required" @change="setControlValue(field.name, $event)">
                <option v-for="option in field.options ?? []" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </template>

            <template v-else-if="field.type === 'textarea'">
              <textarea
                :id="`dialog-${dialogState.requestId}-${field.name}`"
                :value="controlValue(values[field.name])"
                @input="values[field.name] = ($event.target as HTMLTextAreaElement).value"
                rows="5"
                :placeholder="field.placeholder"
                :required="field.required"
              />
            </template>

            <template v-else-if="field.type === 'size-gb'">
              <div class="app-dialog-size-row">
                <select v-model="sizeModes[field.name]" :id="`dialog-${dialogState.requestId}-${field.name}`">
                  <option v-for="gb in sizePresets(field)" :key="gb" :value="String(gb)">{{ gb }} GB</option>
                  <option value="custom">Custom…</option>
                </select>
                <div v-if="sizeModes[field.name] === 'custom'" class="app-dialog-size-custom">
                  <input v-model.number="customSizeGb[field.name]" type="number" min="0.1" step="0.1" />
                  <span>GB</span>
                </div>
              </div>
            </template>

            <template v-else>
              <input
                :id="`dialog-${dialogState.requestId}-${field.name}`"
                :value="typeof values[field.name] === 'boolean' ? '' : values[field.name]"
                :type="field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text'"
                :min="field.min"
                :max="field.max"
                :step="field.step"
                :placeholder="field.placeholder"
                :required="field.required"
                autocomplete="off"
                @input="values[field.name] = ($event.target as HTMLTextAreaElement).value"
              />
            </template>

            <small v-if="field.hint && field.type !== 'checkbox'" class="app-dialog-field__hint">{{ field.hint }}</small>
          </div>

          <p v-if="validationError" class="app-dialog__error">{{ validationError }}</p>

          <footer class="app-dialog__actions">
            <button type="button" class="secondary-button" @click="cancel">{{ request.cancelLabel ?? 'Cancel' }}</button>
            <button
              type="submit"
              :class="request.destructive ? 'danger-button' : 'primary-button'"
            >
              {{ request.confirmLabel ?? 'Continue' }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>
