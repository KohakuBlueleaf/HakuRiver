<script setup>
/**
 * IdeOverlay - Lightweight modal overlay for IDE content.
 *
 * A simple overlay wrapper that provides consistent modal styling
 * for the IDE interface. Used by VPS and Docker pages to display
 * the IDE in a modal without duplicating CSS.
 *
 * Features:
 * - Responsive 95vh/95vw modal sizing
 * - Click-outside-to-close behavior
 * - Smooth transition animations
 * - Teleport to body for proper z-index stacking
 */

defineProps({
  /**
   * Controls modal visibility
   */
  visible: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits(['close'])

/**
 * Handle click on backdrop to close.
 */
function handleBackdropClick() {
  emit('close')
}
</script>

<template>
  <teleport to="body">
    <transition
      name="ide-overlay"
      appear>
      <div
        v-if="visible"
        class="ide-overlay"
        @click.self="handleBackdropClick">
        <div class="ide-overlay-content">
          <slot />
        </div>
      </div>
    </transition>
  </teleport>
</template>

<style scoped>
/* =============================================================================
 * IDE Overlay - Modal backdrop and container
 * ============================================================================= */

.ide-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 2.5vh 2.5vw;
}

.ide-overlay-content {
  width: 95vw;
  height: 95vh;
  max-width: 100%;
  max-height: 100%;
  background: var(--el-bg-color);
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* =============================================================================
 * Responsive Adjustments
 * ============================================================================= */

@media (max-width: 768px) {
  .ide-overlay {
    padding: 1vh 1vw;
  }

  .ide-overlay-content {
    width: 98vw;
    height: 98vh;
    border-radius: 4px;
  }
}

/* =============================================================================
 * Transition Animations
 * ============================================================================= */

.ide-overlay-enter-active,
.ide-overlay-leave-active {
  transition: opacity 0.2s ease;
}

.ide-overlay-enter-active .ide-overlay-content,
.ide-overlay-leave-active .ide-overlay-content {
  transition: transform 0.2s ease;
}

.ide-overlay-enter-from,
.ide-overlay-leave-to {
  opacity: 0;
}

.ide-overlay-enter-from .ide-overlay-content,
.ide-overlay-leave-to .ide-overlay-content {
  transform: scale(0.95);
}
</style>
