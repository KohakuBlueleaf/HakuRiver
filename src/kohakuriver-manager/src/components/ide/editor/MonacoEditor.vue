<script setup>
/**
 * MonacoEditor - Monaco Editor wrapper component.
 *
 * Features:
 * - Syntax highlighting
 * - Theme support (dark/light)
 * - Auto-resize
 * - Language detection
 */

import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker'
import cssWorker from 'monaco-editor/esm/vs/language/css/css.worker?worker'
import htmlWorker from 'monaco-editor/esm/vs/language/html/html.worker?worker'
import tsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker?worker'

// Setup Monaco environment for workers
self.MonacoEnvironment = {
  getWorker(_, label) {
    if (label === 'json') {
      return new jsonWorker()
    }
    if (label === 'css' || label === 'scss' || label === 'less') {
      return new cssWorker()
    }
    if (label === 'html' || label === 'handlebars' || label === 'razor') {
      return new htmlWorker()
    }
    if (label === 'typescript' || label === 'javascript') {
      return new tsWorker()
    }
    return new editorWorker()
  },
}

const props = defineProps({
  /**
   * File content
   */
  modelValue: {
    type: String,
    default: '',
  },
  /**
   * Language for syntax highlighting
   */
  language: {
    type: String,
    default: 'plaintext',
  },
  /**
   * Read-only mode
   */
  readOnly: {
    type: Boolean,
    default: false,
  },
  /**
   * File path (for display purposes)
   */
  path: {
    type: String,
    default: '',
  },
  /**
   * Theme: 'vs-dark' or 'vs'
   */
  theme: {
    type: String,
    default: 'vs-dark',
  },
})

const emit = defineEmits(['update:modelValue', 'save', 'cursor-change'])

// Editor refs
const editorContainer = ref(null)
let editor = null

// Track cursor position
const cursorPosition = ref({ line: 1, column: 1 })

/**
 * Initialize Monaco editor.
 */
function initEditor() {
  if (!editorContainer.value) return

  editor = monaco.editor.create(editorContainer.value, {
    value: props.modelValue,
    language: props.language,
    theme: props.theme,
    readOnly: props.readOnly,
    automaticLayout: true,
    minimap: {
      enabled: true,
      maxColumn: 80,
    },
    fontSize: 14,
    fontFamily: 'Consolas, "Courier New", monospace',
    lineNumbers: 'on',
    renderWhitespace: 'selection',
    scrollBeyondLastLine: false,
    wordWrap: 'off',
    tabSize: 2,
    insertSpaces: true,
    formatOnPaste: true,
    scrollbar: {
      vertical: 'auto',
      horizontal: 'auto',
      verticalScrollbarSize: 10,
      horizontalScrollbarSize: 10,
    },
    padding: {
      top: 8,
      bottom: 8,
    },
  })

  // Listen for content changes
  editor.onDidChangeModelContent(() => {
    const value = editor.getValue()
    emit('update:modelValue', value)
  })

  // Listen for cursor position changes
  editor.onDidChangeCursorPosition((e) => {
    cursorPosition.value = {
      line: e.position.lineNumber,
      column: e.position.column,
    }
    emit('cursor-change', cursorPosition.value)
  })

  // Add Ctrl+S save command
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
    emit('save')
  })

  // Focus the editor
  editor.focus()
}

/**
 * Dispose Monaco editor.
 */
function disposeEditor() {
  if (editor) {
    editor.dispose()
    editor = null
  }
}

/**
 * Get the current cursor position.
 */
function getCursorPosition() {
  if (!editor) return { line: 1, column: 1 }
  const pos = editor.getPosition()
  return { line: pos.lineNumber, column: pos.column }
}

/**
 * Set cursor position.
 */
function setCursorPosition(line, column) {
  if (!editor) return
  editor.setPosition({ lineNumber: line, column })
  editor.revealLineInCenter(line)
}

/**
 * Focus the editor.
 */
function focus() {
  editor?.focus()
}

/**
 * Format document.
 */
function formatDocument() {
  editor?.getAction('editor.action.formatDocument')?.run()
}

// Watch for external content changes
watch(
  () => props.modelValue,
  (newValue) => {
    if (editor && newValue !== editor.getValue()) {
      const position = editor.getPosition()
      editor.setValue(newValue)
      if (position) {
        editor.setPosition(position)
      }
    }
  }
)

// Watch for language changes
watch(
  () => props.language,
  (newLanguage) => {
    if (editor) {
      const model = editor.getModel()
      if (model) {
        monaco.editor.setModelLanguage(model, newLanguage)
      }
    }
  }
)

// Watch for theme changes
watch(
  () => props.theme,
  (newTheme) => {
    monaco.editor.setTheme(newTheme)
  }
)

// Watch for readOnly changes
watch(
  () => props.readOnly,
  (newReadOnly) => {
    if (editor) {
      editor.updateOptions({ readOnly: newReadOnly })
    }
  }
)

// Lifecycle
onMounted(() => {
  initEditor()
})

onBeforeUnmount(() => {
  disposeEditor()
})

// Expose methods
defineExpose({
  getCursorPosition,
  setCursorPosition,
  focus,
  formatDocument,
  cursorPosition,
})
</script>

<template>
  <div ref="editorContainer" class="monaco-editor-container" />
</template>

<style scoped>
.monaco-editor-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
</style>
