import { Store } from '@tauri-apps/plugin-store'

let store = null

async function getStore() {
  if (!store) {
    store = await Store.load('connections.json')
  }
  return store
}

export async function getConnections() {
  const s = await getStore()
  return (await s.get('connections')) || []
}

export async function saveConnection(conn) {
  const s = await getStore()
  const connections = (await s.get('connections')) || []
  const idx = connections.findIndex((c) => c.id === conn.id)
  if (idx >= 0) {
    connections[idx] = conn
  } else {
    connections.push(conn)
  }
  await s.set('connections', connections)
  await s.save()
}

export async function deleteConnection(id) {
  const s = await getStore()
  const connections = (await s.get('connections')) || []
  await s.set(
    'connections',
    connections.filter((c) => c.id !== id),
  )
  await s.save()
}

export async function getLastUsedConnection() {
  const connections = await getConnections()
  if (connections.length === 0) return null
  return connections.reduce((a, b) => (a.lastUsed > b.lastUsed ? a : b))
}
