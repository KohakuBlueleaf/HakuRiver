/**
 * File icon mapping utility.
 *
 * Maps file extensions and types to icon classes.
 * Uses Carbon Design icons (i-carbon-*) via UnoCSS.
 */

// Icon map by file extension
const extensionIconMap = {
  // JavaScript/TypeScript
  js: 'i-carbon-logo-javascript',
  jsx: 'i-carbon-logo-javascript',
  mjs: 'i-carbon-logo-javascript',
  cjs: 'i-carbon-logo-javascript',
  ts: 'i-carbon-typescript',
  tsx: 'i-carbon-typescript',
  mts: 'i-carbon-typescript',

  // Python
  py: 'i-carbon-logo-python',
  pyi: 'i-carbon-logo-python',
  pyw: 'i-carbon-logo-python',
  pyc: 'i-carbon-logo-python',

  // Vue
  vue: 'i-carbon-logo-vue',

  // React
  // jsx/tsx covered above

  // Data formats
  json: 'i-carbon-json',
  yaml: 'i-carbon-document',
  yml: 'i-carbon-document',
  toml: 'i-carbon-document',
  xml: 'i-carbon-code',
  csv: 'i-carbon-table-split',

  // Markup
  html: 'i-carbon-html',
  htm: 'i-carbon-html',
  css: 'i-carbon-css',
  scss: 'i-carbon-css',
  sass: 'i-carbon-css',
  less: 'i-carbon-css',
  md: 'i-carbon-document',
  markdown: 'i-carbon-document',
  rst: 'i-carbon-document',
  txt: 'i-carbon-document-blank',

  // Shell
  sh: 'i-carbon-terminal',
  bash: 'i-carbon-terminal',
  zsh: 'i-carbon-terminal',
  fish: 'i-carbon-terminal',
  ps1: 'i-carbon-terminal',
  bat: 'i-carbon-terminal',
  cmd: 'i-carbon-terminal',

  // Config
  env: 'i-carbon-settings',
  ini: 'i-carbon-settings',
  cfg: 'i-carbon-settings',
  conf: 'i-carbon-settings',
  config: 'i-carbon-settings',

  // Git
  gitignore: 'i-carbon-logo-github',
  gitattributes: 'i-carbon-logo-github',
  gitmodules: 'i-carbon-logo-github',

  // Docker
  dockerfile: 'i-carbon-container-software',

  // Images
  png: 'i-carbon-image',
  jpg: 'i-carbon-image',
  jpeg: 'i-carbon-image',
  gif: 'i-carbon-image',
  svg: 'i-carbon-image',
  ico: 'i-carbon-image',
  webp: 'i-carbon-image',
  bmp: 'i-carbon-image',

  // Archives
  zip: 'i-carbon-zip',
  tar: 'i-carbon-zip',
  gz: 'i-carbon-zip',
  bz2: 'i-carbon-zip',
  xz: 'i-carbon-zip',
  '7z': 'i-carbon-zip',
  rar: 'i-carbon-zip',

  // Binary/Executable
  exe: 'i-carbon-application',
  dll: 'i-carbon-application',
  so: 'i-carbon-application',
  dylib: 'i-carbon-application',
  bin: 'i-carbon-application',

  // Database
  sql: 'i-carbon-data-base',
  db: 'i-carbon-data-base',
  sqlite: 'i-carbon-data-base',
  sqlite3: 'i-carbon-data-base',

  // Other languages
  go: 'i-carbon-code',
  rs: 'i-carbon-code',
  java: 'i-carbon-code',
  kt: 'i-carbon-code',
  c: 'i-carbon-code',
  cpp: 'i-carbon-code',
  h: 'i-carbon-code',
  hpp: 'i-carbon-code',
  cs: 'i-carbon-code',
  rb: 'i-carbon-code',
  php: 'i-carbon-code',
  swift: 'i-carbon-code',
  r: 'i-carbon-code',
  lua: 'i-carbon-code',
  pl: 'i-carbon-code',
  ex: 'i-carbon-code',
  exs: 'i-carbon-code',
  erl: 'i-carbon-code',
  hs: 'i-carbon-code',
  clj: 'i-carbon-code',
  scala: 'i-carbon-code',

  // Build/Package
  makefile: 'i-carbon-build-tool',
  cmake: 'i-carbon-build-tool',
  gradle: 'i-carbon-build-tool',
  'package.json': 'i-carbon-package',
  'package-lock.json': 'i-carbon-package',
  'yarn.lock': 'i-carbon-package',
  'pnpm-lock.yaml': 'i-carbon-package',
  'requirements.txt': 'i-carbon-package',
  'pyproject.toml': 'i-carbon-package',
  'setup.py': 'i-carbon-package',
  'Cargo.toml': 'i-carbon-package',
  'go.mod': 'i-carbon-package',

  // Lock files
  lock: 'i-carbon-locked',

  // Log files
  log: 'i-carbon-report',

  // PDF and documents
  pdf: 'i-carbon-document-pdf',
  doc: 'i-carbon-document',
  docx: 'i-carbon-document',
  xls: 'i-carbon-spreadsheet',
  xlsx: 'i-carbon-spreadsheet',
  ppt: 'i-carbon-presentation-file',
  pptx: 'i-carbon-presentation-file',

  // Video
  mp4: 'i-carbon-video',
  mkv: 'i-carbon-video',
  avi: 'i-carbon-video',
  mov: 'i-carbon-video',
  webm: 'i-carbon-video',

  // Audio
  mp3: 'i-carbon-music',
  wav: 'i-carbon-music',
  ogg: 'i-carbon-music',
  flac: 'i-carbon-music',
  m4a: 'i-carbon-music',
}

// Icon map by filename (for special files)
const filenameIconMap = {
  dockerfile: 'i-carbon-container-software',
  'docker-compose.yml': 'i-carbon-container-software',
  'docker-compose.yaml': 'i-carbon-container-software',
  '.dockerignore': 'i-carbon-container-software',
  '.gitignore': 'i-carbon-logo-github',
  '.gitattributes': 'i-carbon-logo-github',
  '.gitmodules': 'i-carbon-logo-github',
  '.env': 'i-carbon-settings',
  '.env.local': 'i-carbon-settings',
  '.env.development': 'i-carbon-settings',
  '.env.production': 'i-carbon-settings',
  '.editorconfig': 'i-carbon-settings',
  '.prettierrc': 'i-carbon-settings',
  '.eslintrc': 'i-carbon-settings',
  '.eslintrc.js': 'i-carbon-settings',
  '.eslintrc.json': 'i-carbon-settings',
  'tsconfig.json': 'i-carbon-typescript',
  'jsconfig.json': 'i-carbon-logo-javascript',
  'vite.config.js': 'i-carbon-build-tool',
  'vite.config.ts': 'i-carbon-build-tool',
  'webpack.config.js': 'i-carbon-build-tool',
  'rollup.config.js': 'i-carbon-build-tool',
  makefile: 'i-carbon-build-tool',
  readme: 'i-carbon-book',
  'readme.md': 'i-carbon-book',
  'README.md': 'i-carbon-book',
  license: 'i-carbon-license',
  'license.md': 'i-carbon-license',
  'LICENSE': 'i-carbon-license',
  changelog: 'i-carbon-list-numbered',
  'CHANGELOG.md': 'i-carbon-list-numbered',
}

// Default icons
const defaultIcons = {
  file: 'i-carbon-document-blank',
  directory: 'i-carbon-folder',
  directoryOpen: 'i-carbon-folder-open',
  symlink: 'i-carbon-link',
  other: 'i-carbon-help',
}

/**
 * Get the icon class for a file or directory.
 *
 * @param {string} name - File or directory name
 * @param {string} type - Type: 'file', 'directory', 'symlink', 'other'
 * @param {boolean} isExpanded - Whether directory is expanded (for open folder icon)
 * @returns {string} Icon class
 */
export function getFileIcon(name, type = 'file', isExpanded = false) {
  // Handle directories
  if (type === 'directory') {
    return isExpanded ? defaultIcons.directoryOpen : defaultIcons.directory
  }

  // Handle symlinks
  if (type === 'symlink') {
    return defaultIcons.symlink
  }

  // Handle other types
  if (type === 'other') {
    return defaultIcons.other
  }

  // File - check filename first
  const lowerName = name.toLowerCase()
  if (filenameIconMap[lowerName]) {
    return filenameIconMap[lowerName]
  }

  // Check extension
  const ext = name.split('.').pop()?.toLowerCase()
  if (ext && extensionIconMap[ext]) {
    return extensionIconMap[ext]
  }

  // Default file icon
  return defaultIcons.file
}

/**
 * Get icon color class for a file type.
 *
 * @param {string} name - File or directory name
 * @param {string} type - Type: 'file', 'directory', 'symlink', 'other'
 * @returns {string} Color class
 */
export function getFileIconColor(name, type = 'file') {
  if (type === 'directory') {
    return 'text-amber-500'
  }

  if (type === 'symlink') {
    return 'text-cyan-500'
  }

  const ext = name.split('.').pop()?.toLowerCase()

  // Color by extension type
  const colorMap = {
    // JavaScript/TypeScript - Yellow
    js: 'text-yellow-500',
    jsx: 'text-yellow-500',
    ts: 'text-blue-500',
    tsx: 'text-blue-500',

    // Python - Blue/Green
    py: 'text-blue-400',

    // Vue - Green
    vue: 'text-green-500',

    // HTML/CSS - Orange/Blue
    html: 'text-orange-500',
    css: 'text-blue-400',
    scss: 'text-pink-500',

    // Data - Gray
    json: 'text-gray-400',
    yaml: 'text-gray-400',
    yml: 'text-gray-400',

    // Markdown - White/Gray
    md: 'text-gray-300',

    // Images - Purple
    png: 'text-purple-400',
    jpg: 'text-purple-400',
    svg: 'text-purple-400',
  }

  return colorMap[ext] || 'text-gray-400'
}

export default {
  getFileIcon,
  getFileIconColor,
}
