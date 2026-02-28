export function formatTimestamp(timestampSeconds) {
  const value = Number(timestampSeconds)
  if (!Number.isFinite(value) || value <= 0) {
    return '-'
  }

  const date = new Date(value * 1000)
  const now = new Date()
  const diffSeconds = (now - date) / 1000

  if (diffSeconds < 60) {
    return 'just now'
  }

  if (diffSeconds < 3600) {
    return `${Math.floor(diffSeconds / 60)}m ago`
  }

  if (diffSeconds < 86400) {
    return `${Math.floor(diffSeconds / 3600)}h ago`
  }

  return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })}`
}

export function formatDuration(seconds) {
  const value = Number(seconds)
  if (!Number.isFinite(value) || value <= 0) {
    return '-'
  }

  if (value < 60) {
    return `${Math.round(value)}s`
  }

  if (value < 3600) {
    return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`
  }

  return `${Math.floor(value / 3600)}h ${Math.floor((value % 3600) / 60)}m`
}

export function formatCost(value, digits = 4) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue) || numericValue <= 0) {
    return '-'
  }
  return `$${numericValue.toFixed(digits)}`
}
