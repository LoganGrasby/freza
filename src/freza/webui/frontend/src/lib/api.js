let _baseUrl = ''
let _authToken = null

export function setBaseUrl(url) {
  _baseUrl = url.replace(/\/+$/, '')
}

export function setAuthToken(token) {
  _authToken = token
}

export function getBaseUrl() {
  return _baseUrl
}

export function getAuthToken() {
  return _authToken
}

function buildUrl(path) {
  return `${_baseUrl}${path}`
}

function authHeaders() {
  const headers = {}
  if (_authToken) {
    headers['Authorization'] = `Bearer ${_authToken}`
  }
  return headers
}

async function parseJsonResponse(response) {
  let payload = null

  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    const message = payload?.error || `Request failed with status ${response.status}`
    throw new Error(message)
  }

  return payload
}

export async function getJson(path) {
  const response = await fetch(buildUrl(path), {
    headers: authHeaders(),
  })
  return parseJsonResponse(response)
}

export async function postJson(path, body) {
  const response = await fetch(buildUrl(path), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify(body),
  })

  return parseJsonResponse(response)
}

export function sseUrl(path) {
  const base = buildUrl(path)
  if (_authToken) {
    const separator = base.includes('?') ? '&' : '?'
    return `${base}${separator}token=${encodeURIComponent(_authToken)}`
  }
  return base
}
