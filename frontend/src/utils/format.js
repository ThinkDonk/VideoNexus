// 通用格式化工具

// 日期对象 → "YYYY-MM-DD HH:mm:ss"
export function fmtDateTime(input) {
  if (!input) return ''
  if (typeof input === 'string' && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(input)) {
    return input.slice(0, 19)
  }
  const d = input instanceof Date ? input : new Date(input)
  if (isNaN(d.getTime())) return String(input)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

// 字节数 → 人类可读大小
export function fmtSize(bytes) {
  if (bytes === null || bytes === undefined || bytes === '') return '-'
  const n = Number(bytes)
  if (isNaN(n)) return '-'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

// 秒 → "HH:mm:ss"（时长展示）
export function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined || seconds === '') return '-'
  const s = Math.max(0, Math.round(Number(seconds)))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const p = (n) => String(n).padStart(2, '0')
  return `${p(h)}:${p(m)}:${p(sec)}`
}
