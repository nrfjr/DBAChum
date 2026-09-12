<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    disabled?: boolean
    width?: number
  }>(),
  {
    disabled: false,
    width: 190,
  },
)

const menuId = Symbol('floating-action-menu')
const open = ref(false)
const trigger = ref<HTMLElement | null>(null)
const menu = ref<HTMLElement | null>(null)
const menuStyle = ref<Record<string, string>>({ visibility: 'hidden' })

const triggerTitle = computed(() => props.label)

async function positionMenu() {
  if (!open.value || !trigger.value) return

  await nextTick()

  const triggerRect = trigger.value.getBoundingClientRect()
  const menuHeight = menu.value?.offsetHeight ?? 0
  const menuWidth = menu.value?.offsetWidth ?? props.width
  const gap = 6
  const viewportPadding = 8

  const preferredLeft = triggerRect.right - menuWidth
  const left = Math.min(
    Math.max(preferredLeft, viewportPadding),
    Math.max(viewportPadding, window.innerWidth - menuWidth - viewportPadding),
  )

  const downwardTop = triggerRect.bottom + gap
  const canOpenDown = downwardTop + menuHeight <= window.innerHeight - viewportPadding
  const top = canOpenDown
    ? downwardTop
    : Math.max(viewportPadding, triggerRect.top - gap - menuHeight)

  menuStyle.value = {
    position: 'fixed',
    top: `${Math.round(top)}px`,
    left: `${Math.round(left)}px`,
    right: 'auto',
    bottom: 'auto',
    width: `${props.width}px`,
    zIndex: '1200',
    visibility: 'visible',
  }
}

async function toggle(event: MouseEvent) {
  event.stopPropagation()
  if (props.disabled) return

  const nextOpen = !open.value
  if (nextOpen) {
    window.dispatchEvent(new CustomEvent('dbachum-floating-menu-open', { detail: menuId }))
  }

  open.value = nextOpen
  if (open.value) {
    menuStyle.value = { visibility: 'hidden' }
    await positionMenu()
  }
}

function close() {
  open.value = false
}

function closeFromOutside() {
  close()
}

function closeFromViewportChange() {
  close()
}

function closeOtherMenu(event: Event) {
  const customEvent = event as CustomEvent<symbol>
  if (customEvent.detail !== menuId) close()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
}

watch(open, (isOpen) => {
  if (isOpen) {
    document.addEventListener('click', closeFromOutside)
    document.addEventListener('scroll', closeFromViewportChange, true)
    window.addEventListener('resize', closeFromViewportChange)
    document.addEventListener('keydown', handleKeydown)
    window.addEventListener('dbachum-floating-menu-open', closeOtherMenu)
  } else {
    document.removeEventListener('click', closeFromOutside)
    document.removeEventListener('scroll', closeFromViewportChange, true)
    window.removeEventListener('resize', closeFromViewportChange)
    document.removeEventListener('keydown', handleKeydown)
    window.removeEventListener('dbachum-floating-menu-open', closeOtherMenu)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('click', closeFromOutside)
  document.removeEventListener('scroll', closeFromViewportChange, true)
  window.removeEventListener('resize', closeFromViewportChange)
  document.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('dbachum-floating-menu-open', closeOtherMenu)
})
</script>

<template>
  <div class="user-action-menu-wrap" @click.stop>
    <button
      ref="trigger"
      type="button"
      class="user-action-button user-menu-button"
      :aria-expanded="open"
      :aria-label="label"
      :title="triggerTitle"
      :disabled="disabled"
      @click="toggle"
    >
      <FontAwesomeIcon icon="ellipsis-vertical" />
    </button>
  </div>

  <Teleport to="body">
    <div
      v-if="open"
      ref="menu"
      class="user-action-dropdown floating-action-menu"
      role="menu"
      :style="menuStyle"
      @click.stop="close"
    >
      <slot />
    </div>
  </Teleport>
</template>
