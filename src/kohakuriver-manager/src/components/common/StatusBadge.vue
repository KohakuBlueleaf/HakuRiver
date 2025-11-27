<script setup>
import { STATUS_BADGE_CLASS } from '@/utils/constants'

const props = defineProps({
  status: {
    type: String,
    required: true,
  },
  size: {
    type: String,
    default: 'md', // sm, md, lg
  },
})

const badgeClass = computed(() => {
  return STATUS_BADGE_CLASS[props.status] || 'badge-gray'
})

const sizeClass = computed(() => {
  const sizes = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-xs px-2.5 py-1',
    lg: 'text-sm px-3 py-1.5',
  }
  return sizes[props.size] || sizes.md
})

const displayStatus = computed(() => {
  // Convert status to display format
  return props.status.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
})
</script>

<template>
  <span :class="[badgeClass, sizeClass]" class="rounded-full font-medium inline-flex items-center gap-1">
    <span class="w-1.5 h-1.5 rounded-full bg-current opacity-75"></span>
    {{ displayStatus }}
  </span>
</template>
