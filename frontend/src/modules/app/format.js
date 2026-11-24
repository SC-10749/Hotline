import { apiUrl } from '../../api'

// 字节数展示：聊天附件与工作区上传清单共用同一套文案。
export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// 下载链接：相对路径按后端地址补全，远程链接原样使用。
export function downloadHref(backendUrl, file) {
  return /^https?:\/\//i.test(file) ? file : apiUrl(backendUrl, file)
}
