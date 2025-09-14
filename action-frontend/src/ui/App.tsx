import React, { useEffect, useState } from 'react'

type Session = { id: string }

export const App: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [messages, setMessages] = useState<any[]>([])
  const [since, setSince] = useState<string | null>(null)
  const API_BASE = (process.env.VITE_WEBAPP_URL as string) || 'http://localhost:8000'

  useEffect(() => {
    fetch(`${API_BASE}/api/sessions`)
      .then(r => r.json()).then(setSessions).catch(() => {})
  }, [])

  useEffect(() => {
    if (!selected) return
    const poll = async () => {
      const qs = new URLSearchParams({ session_id: selected })
      if (since) qs.set('since', since)
      const resp = await fetch(`${API_BASE}/api/updates?` + qs.toString())
      const data = await resp.json()
      if (data.messages?.length) {
        setMessages(prev => [...prev, ...data.messages])
        const last = data.messages[data.messages.length - 1]?.created_at
        if (last) setSince(last)
      }
    }
    const id = setInterval(poll, 500)
    return () => clearInterval(id)
  }, [selected, since])

  return (
    <div style={{ display: 'flex', gap: 16, padding: 16 }}>
      <div style={{ width: 300 }}>
        <h3>Sessions</h3>
        <button onClick={async () => {
          const resp = await fetch(`${API_BASE}/api/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
          const s = await resp.json(); setSessions(prev => [s, ...prev])
        }}>New Session</button>
        <ul>
          {sessions.map(s => (
            <li key={s.id}>
              <button onClick={() => { setSelected(s.id); setMessages([]); setSince(null) }}>
                {s.id}
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div style={{ flex: 1 }}>
        <h3>Session Detail {selected ? `(${selected})` : ''}</h3>
        <ul>
          {messages.map(m => (
            <li key={m.id}><code>{m.created_at}</code> [{m.topic_id}] {m.payload_json}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}


