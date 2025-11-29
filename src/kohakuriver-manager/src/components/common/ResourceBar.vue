<script setup>
const props = defineProps({
  value: {
    type: Number,
    default: 0,
  },
  max: {
    type: Number,
    default: 100,
  },
  label: {
    type: String,
    default: '',
  },
  showPercent: {
    type: Boolean,
    default: true,
  },
  size: {
    type: String,
    default: 'md', // sm, md, lg
  },
  color: {
    type: String,
    default: 'blue', // blue, green, yellow, red
  },
})

const percent = computed(() => {
  if (props.max === 0) return 0
  return Math.min(100, (props.value / props.max) * 100)
})

const barHeight = computed(() => {
  const heights = { sm: 'h-1.5', md: 'h-2', lg: 'h-3' }
  return heights[props.size] || heights.md
})

const barColor = computed(() => {
  // Auto color based on percent
  if (props.color === 'auto') {
    if (percent.value >= 90) return 'bg-red-500'
    if (percent.value >= 70) return 'bg-yellow-500'
    return 'bg-green-500'
  }
  const colors = {
    blue: 'bg-blue-500',
    green: 'bg-green-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500',
  }
  return colors[props.color] || colors.blue
})
</script>

<template>
  <div class="w-full">
    <div
      v-if="label || showPercent"
      class="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
      <span>{{ label }}</span>
      <span v-if="showPercent">{{ percent.toFixed(1) }}%</span>
    </div>
    <div
      :class="barHeight"
      class="bg-app-inset rounded-full overflow-hidden">
      <div
        :class="[barColor, barHeight]"
        class="rounded-full transition-all duration-300"
        :style="{ width: `${percent}%` }"></div>
    </div>
  </div>
</template>
