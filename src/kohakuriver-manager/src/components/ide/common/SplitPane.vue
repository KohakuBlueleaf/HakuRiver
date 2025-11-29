<script setup>
/**
 * SplitPane - A resizable split pane component.
 *
 * Can be horizontal (left/right) or vertical (top/bottom).
 * Supports min/max size constraints and localStorage persistence.
 */

const props = defineProps({
  /**
   * Split direction: 'horizontal' for left/right, 'vertical' for top/bottom
   */
  direction: {
    type: String,
    default: 'horizontal',
    validator: (v) => ['horizontal', 'vertical'].includes(v),
  },
  /**
   * Initial size of the sized pane in pixels
   */
  initialSize: {
    type: Number,
    default: 250,
  },
  /**
   * Minimum size of the sized pane in pixels
   */
  minSize: {
    type: Number,
    default: 100,
  },
  /**
   * Maximum size of the sized pane in pixels
   */
  maxSize: {
    type: Number,
    default: 600,
  },
  /**
   * localStorage key for persisting size (optional)
   */
  storageKey: {
    type: String,
    default: null,
  },
  /**
   * If true, the second pane is the sized one (dragging right increases it)
   */
  reverse: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:size', 'resize-start', 'resize-end'])

// Current size of the first pane
const size = ref(props.initialSize)

// Whether the user is currently resizing
const isResizing = ref(false)

// Computed properties
const isHorizontal = computed(() => props.direction === 'horizontal')
const sizeProperty = computed(() => (isHorizontal.value ? 'width' : 'height'))

// Load from localStorage on mount
onMounted(() => {
  if (props.storageKey) {
    try {
      const saved = localStorage.getItem(`split-pane-${props.storageKey}`)
      if (saved) {
        const savedSize = parseInt(saved, 10)
        if (!isNaN(savedSize) && savedSize >= props.minSize && savedSize <= props.maxSize) {
          size.value = savedSize
        }
      }
    } catch (e) {
      console.warn('Failed to load split pane size:', e)
    }
  }
})

// Save to localStorage when size changes
watch(size, (newSize) => {
  emit('update:size', newSize)

  if (props.storageKey) {
    try {
      localStorage.setItem(`split-pane-${props.storageKey}`, newSize.toString())
    } catch (e) {
      console.warn('Failed to save split pane size:', e)
    }
  }
})

/**
 * Handle resize start (mouse/touch down on resizer)
 */
function startResize(e) {
  e.preventDefault()

  isResizing.value = true
  emit('resize-start')

  const startPos = isHorizontal.value ? e.clientX || e.touches?.[0]?.clientX : e.clientY || e.touches?.[0]?.clientY
  const startSize = size.value

  function onMove(moveEvent) {
    const currentPos = isHorizontal.value
      ? moveEvent.clientX || moveEvent.touches?.[0]?.clientX
      : moveEvent.clientY || moveEvent.touches?.[0]?.clientY

    if (currentPos === undefined) return

    const delta = currentPos - startPos
    // In reverse mode, dragging right/down should decrease the size
    const newSize = props.reverse ? startSize - delta : startSize + delta

    // Clamp to min/max
    size.value = Math.max(props.minSize, Math.min(props.maxSize, newSize))
  }

  function onEnd() {
    isResizing.value = false
    emit('resize-end')

    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onEnd)
    document.removeEventListener('touchmove', onMove)
    document.removeEventListener('touchend', onEnd)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onEnd)
  document.addEventListener('touchmove', onMove)
  document.addEventListener('touchend', onEnd)

  // Set cursor style during resize
  document.body.style.cursor = isHorizontal.value ? 'col-resize' : 'row-resize'
  document.body.style.userSelect = 'none'
}

/**
 * Handle double-click to reset to initial size
 */
function resetSize() {
  size.value = props.initialSize
}

// Expose size for parent components
defineExpose({ size })
</script>

<template>
  <div
    class="split-pane"
    :class="[direction, { resizing: isResizing, reverse: reverse }]">
    <!-- First pane -->
    <div
      class="pane first"
      :style="reverse ? {} : { [sizeProperty]: size + 'px' }">
      <slot name="first" />
    </div>

    <!-- Resizer bar -->
    <div
      class="resizer"
      :class="direction"
      @mousedown="startResize"
      @touchstart="startResize"
      @dblclick="resetSize">
      <div class="resizer-handle" />
    </div>

    <!-- Second pane -->
    <div
      class="pane second"
      :style="reverse ? { [sizeProperty]: size + 'px' } : {}">
      <slot name="second" />
    </div>
  </div>
</template>

<style scoped>
.split-pane {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.split-pane.horizontal {
  flex-direction: row;
}

.split-pane.vertical {
  flex-direction: column;
}

.pane {
  overflow: hidden;
  position: relative;
  min-height: 0;
}

.pane.first {
  flex-shrink: 0;
}

.pane.second {
  flex: 1;
  min-width: 0;
  min-height: 0;
}

/* Reverse mode: first pane is flexible, second is sized */
.split-pane.reverse .pane.first {
  flex: 1;
  min-width: 0;
  min-height: 0;
}

.split-pane.reverse .pane.second {
  flex-shrink: 0;
}

.resizer {
  flex-shrink: 0;
  background: var(--el-border-color);
  position: relative;
  z-index: 100;
  transition: background-color 0.15s ease;
}

.resizer.horizontal {
  width: 4px;
  cursor: col-resize;
}

.resizer.vertical {
  height: 4px;
  cursor: row-resize;
}

.resizer:hover,
.split-pane.resizing .resizer {
  background: var(--el-color-primary);
}

/* Invisible larger hit area for easier grabbing */
.resizer-handle {
  position: absolute;
  background: transparent;
}

.resizer.horizontal .resizer-handle {
  left: -4px;
  right: -4px;
  top: 0;
  bottom: 0;
}

.resizer.vertical .resizer-handle {
  top: -4px;
  bottom: -4px;
  left: 0;
  right: 0;
}

/* Prevent text selection during resize */
.split-pane.resizing {
  user-select: none;
}

.split-pane.resizing .pane {
  pointer-events: none;
}
</style>
