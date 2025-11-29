<script setup>
defineProps({
  icon: {
    type: String,
    default: 'i-carbon-document-unknown',
  },
  title: {
    type: String,
    default: 'No data',
  },
  description: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <div class="flex flex-col items-center justify-center py-12 text-center">
    <span
      :class="icon"
      class="text-6xl text-gray-300 dark:text-gray-600 mb-4"></span>
    <h3 class="text-lg font-medium text-gray-600 dark:text-gray-400">{{ title }}</h3>
    <p
      v-if="description"
      class="text-sm text-gray-500 dark:text-gray-500 mt-1 max-w-md">
      {{ description }}
    </p>
    <div class="mt-4">
      <slot name="action"></slot>
    </div>
  </div>
</template>
