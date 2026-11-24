const excludedDirectories = new Set([
  '.git', 'data', 'private', 'secrets', '.secrets', '.ssh', '.aws', '.azure',
  'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build',
])

export function workspacePathAllowed(value) {
  const path = String(value).replaceAll('\\', '/')
  if (path.startsWith('/') || path.includes(':') || /[\u0000-\u001f]/.test(path)) return false
  return path.split('/').every((part) => {
    const name = part.toLowerCase()
    return name !== '..' && !excludedDirectories.has(name)
      && !/(^|\.)env($|[._-])/.test(name)
      && !/\.(local|private)(\.|$)/.test(name)
      && !/\.(pem|key|p12|pfx)$/.test(name)
      && !/^(id_rsa|id_ed25519)/.test(name)
  })
}
