import { reactive } from 'vue'

export type FeedbackTone = 'default' | 'success' | 'warning' | 'danger'
export type DialogFieldType =
  | 'text'
  | 'password'
  | 'number'
  | 'textarea'
  | 'select'
  | 'checkbox'
  | 'size-gb'

export interface DialogOption {
  label: string
  value: string
  hint?: string
}

export interface DialogField {
  name: string
  label: string
  type?: DialogFieldType
  value?: string | number | boolean | null
  placeholder?: string
  hint?: string
  required?: boolean
  min?: number
  max?: number
  step?: number
  options?: DialogOption[]
  presetsGb?: number[]
  minMb?: number
  optional?: boolean
}

export interface DialogRequest {
  title: string
  message?: string
  tone?: FeedbackTone
  confirmLabel?: string
  cancelLabel?: string
  fields?: DialogField[]
  destructive?: boolean
}

export type DialogResult = Record<string, string | number | boolean | null>

export interface PromptOptions {
  title: string
  label?: string
  message?: string
  defaultValue?: string
  placeholder?: string
  inputType?: 'text' | 'password' | 'number' | 'textarea'
  confirmLabel?: string
  required?: boolean
}

export interface ToastItem {
  id: number
  title: string
  message?: string
  tone: FeedbackTone
}

interface DialogState {
  open: boolean
  requestId: number
  request: DialogRequest | null
}

export const dialogState = reactive<DialogState>({
  open: false,
  requestId: 0,
  request: null,
})

export const toastState = reactive<{ items: ToastItem[] }>({ items: [] })

let dialogResolver: ((result: DialogResult | null) => void) | null = null
let nextToastId = 1

export function openDialog(request: DialogRequest): Promise<DialogResult | null> {
  if (dialogResolver) {
    dialogResolver(null)
    dialogResolver = null
  }

  dialogState.requestId += 1
  dialogState.request = request
  dialogState.open = true

  return new Promise((resolve) => {
    dialogResolver = resolve
  })
}

export function resolveDialog(result: DialogResult | null) {
  const resolver = dialogResolver
  dialogResolver = null
  dialogState.open = false
  dialogState.request = null
  resolver?.(result)
}

export async function confirmDialog(options: {
  title: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: FeedbackTone
  destructive?: boolean
}) {
  const result = await openDialog({
    ...options,
    fields: [],
  })
  return result !== null
}

export async function promptDialog(options: PromptOptions) {
  const result = await openDialog({
    title: options.title,
    message: options.message,
    confirmLabel: options.confirmLabel ?? 'Continue',
    fields: [
      {
        name: 'value',
        label: options.label ?? options.title,
        type: options.inputType ?? 'text',
        value: options.defaultValue ?? '',
        placeholder: options.placeholder,
        required: options.required ?? false,
      },
    ],
  })

  if (!result) return null
  return String(result.value ?? '')
}

export async function formDialog(request: DialogRequest) {
  return openDialog(request)
}

export function showToast(options: {
  title: string
  message?: string
  tone?: FeedbackTone
  durationMs?: number
}) {
  const item: ToastItem = {
    id: nextToastId++,
    title: options.title,
    message: options.message,
    tone: options.tone ?? 'default',
  }

  toastState.items.push(item)
  window.setTimeout(() => dismissToast(item.id), options.durationMs ?? 4200)
  return item.id
}

export function dismissToast(id: number) {
  const index = toastState.items.findIndex((item) => item.id === id)
  if (index >= 0) toastState.items.splice(index, 1)
}
