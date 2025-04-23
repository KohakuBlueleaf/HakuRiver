<!-- src/components/TerminalModal.vue -->
<template>
  <el-dialog
    v-model="dialogVisible"
    :title="`Shell: ${containerName}`"
    width="90vw"
    top="5vh"
    :close-on-click-modal="false"
    @open="handleOpen"
    @closed="handleClosed"
    class="terminal-modal"
    style="height: 90vh; max-height: 100vh"
  >
    <div ref="terminalContainer" class="terminal-container"></div>

    <div v-if="isLoading" class="terminal-overlay">
      <el-icon class="is-loading"><Loading /></el-icon> Connecting...
    </div>
    <div v-if="error" class="terminal-overlay terminal-error">
      <el-icon><CircleClose /></el-icon> {{ error }}
    </div>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="dialogVisible = false">Close</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, nextTick } from 'vue';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css'; // Import Xterm.js CSS
import { Loading, CircleClose } from '@element-plus/icons-vue'; // Import icons

const props = defineProps({
  modelValue: Boolean, // v-model binding for dialog visibility
  containerName: String, // Name of the container to connect to
});

const emit = defineEmits(['update:modelValue', 'closed']);

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});

const terminalContainer = ref(null);
let term = null;
let fitAddon = null;
let websocket = null;

const isLoading = ref(false);
const error = ref(null);

const hostUrl = import.meta.env.DEV ? '' : '/api'; // Use proxy in dev, direct /api in prod

const handleOpen = () => {
  isLoading.value = true;
  error.value = null;

  nextTick(() => {
    // Ensure DOM element is available
    if (terminalContainer.value && props.containerName) {
      initializeTerminal();
      connectWebSocket();
    } else {
      error.value = 'Terminal container not ready or container name missing.';
      isLoading.value = false;
    }
  });
};

const handleClosed = () => {
  disposeTerminal();
  emit('closed'); // Notify parent component
};

const initializeTerminal = () => {
  if (term) disposeTerminal(); // Clean up existing instance

  term = new Terminal({
    cursorBlink: true,
    cursorStyle: 'block', // or 'underline'
    bellStyle: 'sound',
    fontSize: 14, // Adjust font size as needed
    fontFamily: 'Consolas, Monaco, "Andale Mono", "Ubuntu Mono", monospace', // Monospace font
    theme: {
      background: '#1f2d3d', // Dark background similar to Element Plus sidebar
      foreground: '#bfcbd9', // Light text color
      // Add other colors for a complete theme if desired
      cursor: '#bfcbd9',
      selectionBackground: 'rgba(64, 158, 255, 0.3)',
      black: '#2e3436',
      red: '#cc0000',
      green: '#4e9a06',
      yellow: '#c4a000',
      blue: '#3465a4',
      magenta: '#75507b',
      cyan: '#06989a',
      white: '#d3d7cf',
      brightBlack: '#555753',
      brightRed: '#ef2929',
      brightGreen: '#8ae234',
      brightYellow: '#fce94f',
      brightBlue: '#729fcf',
      brightMagenta: '#ad7fa8',
      brightCyan: '#34e2e2',
      brightWhite: '#eeeeec',
    },
  });

  fitAddon = new FitAddon();
  term.loadAddon(fitAddon);

  term.open(terminalContainer.value);
  fitAddon.fit(); // Initial fit

  // Add resize listener (uses browser's ResizeObserver under the hood for the modal content)
  window.addEventListener('resize', handleResize); // Global resize
  // Need observer for modal resizing
  const observer = new ResizeObserver(() => {
    handleResize();
  });
  if (terminalContainer.value.parentElement) {
    observer.observe(terminalContainer.value.parentElement);
  }

  // Handle user input from the terminal
  term.onData((data) => {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.send(JSON.stringify({ type: 'input', data: data }));
    }
  });
};

const disposeTerminal = () => {
  if (websocket) {
    websocket.close();
    websocket = null;
  }
  if (term) {
    term.dispose();
    term = null;
  }
  if (fitAddon) {
    fitAddon = null;
  }
  window.removeEventListener('resize', handleResize); // Remove global listener
  // Need to disconnect ResizeObserver if used
  const observer = new ResizeObserver(() => {
    handleResize();
  }); // Dummy observer to get its instance
  if (terminalContainer.value && terminalContainer.value.parentElement) {
    observer.unobserve(terminalContainer.value.parentElement);
  }
};

const connectWebSocket = () => {
  const wsUrl = `ws://${window.location.host}${hostUrl}/api/docker/host/containers/${props.containerName}/terminal`; // Construct WebSocket URL

  websocket = new WebSocket(wsUrl);

  websocket.onopen = () => {
    console.log('WebSocket connection opened');
    isLoading.value = false;
    error.value = null;
    // Initial resize message after connection
    sendResizeMessage();
  };

  websocket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      if (message.type === 'output') {
        term.write(message.data);
      } else if (message.type === 'error') {
        error.value = message.data;
        console.error('Received error from WebSocket:', message.data);
        // Optionally close WebSocket on error
        // websocket.close(1008, message.data);
      } else {
        console.warn('Received unknown message type:', message.type, message);
      }
    } catch (e) {
      console.error('Failed to parse WebSocket message:', event.data, e);
      term.write(`\r\nError processing message: ${event.data}\r\n`);
    }
  };

  websocket.onerror = (event) => {
    console.error('WebSocket error observed:', event);
    error.value = 'WebSocket error. See browser console for details.';
    isLoading.value = false;
  };

  websocket.onclose = (event) => {
    console.log('WebSocket connection closed:', event.code, event.reason);
    isLoading.value = false;
    if (event.code !== 1000) {
      // 1000 is normal closure
      error.value = `WebSocket closed unexpectedly: ${event.code} ${event.reason}`;
    } else {
      term.write('\r\nConnection closed.\r\n'); // Notify user in terminal
    }
  };
};

const handleResize = () => {
  if (term && fitAddon && websocket && websocket.readyState === WebSocket.OPEN) {
    fitAddon.fit();
    sendResizeMessage();
  }
};

const sendResizeMessage = () => {
  if (term && websocket && websocket.readyState === WebSocket.OPEN) {
    const { rows, cols } = term.size;
    websocket.send(JSON.stringify({ type: 'resize', rows, cols }));
    console.log(`Sent resize: ${cols}x${rows}`);
  }
};

// Clean up on component unmount
onBeforeUnmount(() => {
  disposeTerminal();
});
</script>

<style>
.terminal-modal .el-dialog__body {
  height: calc(100% - 4.5rem);
}
</style>

<style scoped>
.terminal-container {
  flex-grow: 1;
  /* Override default background if needed, or let xterm theme handle it */
  background-color: var(--el-color-black); /* Dark background for terminal area */
  position: relative; /* Needed for absolute positioning of overlay */
  height: 100%;
}

/* Overlay for loading/error */
.terminal-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.8);
  color: white;
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 10; /* Above terminal content */
  font-size: 1.2em;
}
.terminal-error {
  background-color: rgba(245, 108, 108, 0.9); /* Reddish background for errors */
  color: white;
}
.terminal-overlay .el-icon {
  margin-right: 10px;
}

/* Make the Xterm.js content fill the container */
.terminal-container :deep(.xterm) {
  height: 100%;
  width: 100%;
}
</style>
