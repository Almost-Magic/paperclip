import React, { useState, useEffect, useCallback, useRef } from 'react'
import { CostDashboard } from './screens/CostDashboard'
import { AuditLog } from './screens/AuditLog'

// Colors constant
const colors = {
  bg: '#0A0E14',
  card: '#131820',
  border: '#21262D',
  text: '#E6EDF3',
  muted: '#8B949E',
  accent: '#C9944A',
  success: '#4CAF7D',
  warning: '#D4863A',
  error: '#E05858',
}

// Hook: useWebSocket — Real-time updates via WebSocket
function useWebSocket(endpoint) {
  const [data, setData] = useState(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState(null)
  const wsRef = useRef(null)
  const messageHandlersRef = useRef([])

  useEffect(() => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}${endpoint}`

    const connect = () => {
      try {
        const ws = new WebSocket(wsUrl)

        ws.onopen = () => {
          console.log(`[WebSocket] Connected to ${endpoint}`)
          setConnected(true)
          setError(null)
        }

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data)
            console.log(`[WebSocket] Received:`, message)

            // Call all registered message handlers
            messageHandlersRef.current.forEach(handler => handler(message))

            // Store the message for reference
            setData(prev => ({
              ...prev,
              lastMessage: message,
              timestamp: new Date().toISOString(),
            }))
          } catch (e) {
            console.error('[WebSocket] Failed to parse message:', e)
          }
        }

        ws.onerror = (event) => {
          console.error('[WebSocket] Error:', event)
          setError('WebSocket error')
          setConnected(false)
        }

        ws.onclose = () => {
          console.log(`[WebSocket] Disconnected from ${endpoint}`)
          setConnected(false)
          // Attempt to reconnect after 3 seconds
          setTimeout(connect, 3000)
        }

        wsRef.current = ws
      } catch (e) {
        console.error('[WebSocket] Failed to connect:', e)
        setError(e.message)
        setTimeout(connect, 3000)
      }
    }

    connect()

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [endpoint])

  const subscribe = useCallback((handler) => {
    messageHandlersRef.current.push(handler)
    return () => {
      messageHandlersRef.current = messageHandlersRef.current.filter(h => h !== handler)
    }
  }, [])

  const send = useCallback((message) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
    } else {
      console.warn('[WebSocket] Connection not ready')
    }
  }, [])

  return { connected, error, subscribe, send, data }
}

// Hook: usePolling — Fallback for non-WebSocket data
function usePolling(url, interval) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const r = await fetch(url)
        if (!r.ok) throw new Error(`${r.status}`)
        setData(await r.json())
        setError(null)
      } catch (e) {
        setError(e.message)
      }
      setLoading(false)
    }

    load()
    const id = setInterval(load, interval)
    return () => clearInterval(id)
  }, [url, interval])

  return { data, loading, error }
}

// Component: StatusBadge
function StatusBadge({ status }) {
  const bgColor = status === 'busy' ? colors.success : status === 'offline' ? colors.error : colors.warning
  return (
    <span style={{
      display: 'inline-block',
      backgroundColor: bgColor,
      color: colors.bg,
      padding: '4px 8px',
      borderRadius: '8px',
      fontSize: '12px',
      fontWeight: 600,
      textTransform: 'uppercase',
      marginRight: '8px',
    }}>
      {status === 'busy' ? '🟢' : status === 'offline' ? '🔴' : '🟡'} {status}
    </span>
  )
}

// Component: TaskCard
function TaskCard({ task }) {
  return (
    <div style={{
      backgroundColor: colors.card,
      border: `1px solid ${colors.border}`,
      borderRadius: '8px',
      padding: '16px',
      marginBottom: '12px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
        <span style={{ fontWeight: 600, color: colors.accent }}>{task.instruction}</span>
        <StatusBadge status={task.status} />
      </div>
      <div style={{ fontSize: '12px', color: colors.muted, marginBottom: '8px' }}>
        → {task.assigned_to} ({task.assigned_to_type})
      </div>
      {task.output && (
        <pre style={{
          backgroundColor: colors.bg,
          border: `1px solid ${colors.border}`,
          borderRadius: '6px',
          padding: '8px 12px',
          fontSize: '11px',
          color: colors.accent,
          fontFamily: 'JetBrains Mono',
          maxHeight: '150px',
          overflow: 'auto',
          margin: 0,
        }}>
          {task.output.substring(0, 300)}
        </pre>
      )}
    </div>
  )
}

// Screen 1: Command Centre
function CommandCentre({ onTaskCreated, wsConnected }) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [tasks, setTasks] = useState([])
  const { subscribe } = useWebSocket('/paperclip/ws')

  // Fetch initial tasks
  useEffect(() => {
    const fetchTasks = async () => {
      try {
        const r = await fetch('/paperclip/api/tasks?limit=50')
        if (r.ok) {
          const result = await r.json()
          setTasks(result.items || [])
        }
      } catch (e) {
        console.error('Failed to fetch tasks:', e)
      }
    }
    fetchTasks()
  }, [])

  // Subscribe to task creation events
  useEffect(() => {
    return subscribe((msg) => {
      if (msg.type === 'task_created' || msg.type === 'task_update') {
        // Refetch tasks when new one arrives
        fetch('/paperclip/api/tasks?limit=50')
          .then(r => r.json())
          .then(result => setTasks(result.items || []))
          .catch(e => console.error('Failed to refresh tasks:', e))
      }
    })
  }, [subscribe])

  const handleCommand = async (e) => {
    e.preventDefault()
    if (!input.trim()) return

    setLoading(true)
    setMessage('')
    try {
      const r = await fetch('/paperclip/api/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: input }),
      })
      const data = await r.json()
      setMessage(`✓ Routed to ${data.routed_to}`)
      setInput('')
      onTaskCreated()
    } catch (e) {
      setMessage(`✗ Error: ${e.message}`)
    }
    setLoading(false)
  }

  return (
    <div>
      <h1 style={{ fontFamily: 'Lora', fontSize: '28px', marginBottom: '20px', color: colors.accent }}>
        Command Centre
      </h1>

      <div style={{
        backgroundColor: colors.card,
        border: `1px solid ${colors.border}`,
        borderRadius: '8px',
        padding: '24px',
        marginBottom: '24px',
      }}>
        <form onSubmit={handleCommand}>
          <div style={{ marginBottom: '12px' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontSize: '12px', color: colors.muted, textTransform: 'uppercase' }}>
              Instruction
            </label>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="e.g., fix CK-MANI, test Baldrick, write prd for X"
              style={{
                width: '100%',
                backgroundColor: colors.bg,
                border: `1px solid ${colors.border}`,
                borderRadius: '8px',
                padding: '12px',
                color: colors.text,
                fontSize: '14px',
                boxSizing: 'border-box',
                fontFamily: 'Inter',
              }}
            />
          </div>
          <button
            type="submit"
            disabled={loading || !input.trim()}
            style={{
              backgroundColor: colors.accent,
              color: colors.bg,
              border: 'none',
              borderRadius: '8px',
              padding: '10px 16px',
              fontWeight: 600,
              cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
              opacity: loading || !input.trim() ? 0.5 : 1,
            }}
          >
            {loading ? 'Routing...' : 'Send'}
          </button>
        </form>

        {message && (
          <div style={{ marginTop: '12px', fontSize: '12px', color: colors.accent }}>
            {message}
          </div>
        )}
      </div>

      <h2 style={{ fontSize: '16px', fontFamily: 'Lora', marginBottom: '12px', color: colors.accent }}>
        Recent Tasks
      </h2>
      {tasks && tasks.slice(0, 5).map(t => (
        <TaskCard key={t.id} task={t} />
      ))}
    </div>
  )
}

// Screen 2: Fleet Dashboard
function FleetDashboard() {
  const apps = [
    { name: 'ELAINE', port: 5000, sure_score: 97, h11_score: null },
    { name: 'Baldrick', port: 5050, sure_score: 96, h11_score: 34 },
    { name: 'Costanza', port: 5201, sure_score: 95, h11_score: null },
    { name: 'CK-MANI', port: 5012, sure_score: 88, h11_score: 12 },
    { name: 'Workshop', port: 5001, sure_score: 92, h11_score: null },
  ]

  const getScoreColor = (score) => {
    if (score >= 95) return colors.success
    if (score >= 85) return colors.warning
    return colors.error
  }

  return (
    <div>
      <h1 style={{ fontFamily: 'Lora', fontSize: '28px', marginBottom: '20px', color: colors.accent }}>
        Fleet Dashboard
      </h1>

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: `2px solid ${colors.border}` }}>
            <th style={{ padding: '12px', textAlign: 'left', color: colors.muted, fontSize: '12px', fontWeight: 600, textTransform: 'uppercase' }}>App</th>
            <th style={{ padding: '12px', textAlign: 'left', color: colors.muted, fontSize: '12px', fontWeight: 600, textTransform: 'uppercase' }}>Port</th>
            <th style={{ padding: '12px', textAlign: 'left', color: colors.muted, fontSize: '12px', fontWeight: 600, textTransform: 'uppercase' }}>Sure? Score</th>
            <th style={{ padding: '12px', textAlign: 'left', color: colors.muted, fontSize: '12px', fontWeight: 600, textTransform: 'uppercase' }}>H11 Test Score</th>
          </tr>
        </thead>
        <tbody>
          {apps.map(app => (
            <tr key={app.name} style={{ borderBottom: `1px solid ${colors.border}` }}>
              <td style={{ padding: '12px', color: colors.text }}>{app.name}</td>
              <td style={{ padding: '12px', color: colors.muted, fontSize: '12px', fontFamily: 'JetBrains Mono' }}>{app.port}</td>
              <td style={{ padding: '12px' }}>
                <span style={{ color: getScoreColor(app.sure_score), fontWeight: 600 }}>
                  {app.sure_score}/100 {app.sure_score >= 95 ? '✓' : '⚠'}
                </span>
              </td>
              <td style={{ padding: '12px', color: colors.muted }}>
                {app.h11_score ? `${app.h11_score}/35 ${app.h11_score >= 30 ? '✓' : '⚠'}` : 'n/a'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Screen 3: Terminals
function TerminalsScreen() {
  const [terminals, setTerminals] = useState([])
  const [loading, setLoading] = useState(true)
  const { subscribe } = useWebSocket('/paperclip/ws')

  // Fetch initial terminals
  useEffect(() => {
    const fetchTerminals = async () => {
      setLoading(true)
      try {
        const r = await fetch('/paperclip/api/terminals')
        if (r.ok) {
          setTerminals(await r.json())
        }
      } catch (e) {
        console.error('Failed to fetch terminals:', e)
      }
      setLoading(false)
    }
    fetchTerminals()
  }, [])

  // Subscribe to terminal status updates
  useEffect(() => {
    return subscribe((msg) => {
      if (msg.type === 'terminal_update') {
        setTerminals(prev => prev.map(t =>
          t.id === msg.terminal_id
            ? { ...t, status: msg.status, current_task: msg.current_task }
            : t
        ))
      }
    })
  }, [subscribe])

  if (loading && !terminals.length) return <div>Loading terminals...</div>

  return (
    <div>
      <h1 style={{ fontFamily: 'Lora', fontSize: '28px', marginBottom: '20px', color: colors.accent }}>
        Terminals (7)
      </h1>

      {terminals.map(t => (
        <div key={t.id} style={{
          backgroundColor: colors.card,
          border: `1px solid ${colors.border}`,
          borderRadius: '8px',
          padding: '16px',
          marginBottom: '12px',
          display: 'grid',
          gridTemplateColumns: '100px 1fr 150px 150px',
          gap: '16px',
          alignItems: 'center',
        }}>
          <strong style={{ color: colors.accent }}>{t.id}</strong>
          <div>
            <div style={{ fontWeight: 500, marginBottom: '4px' }}>{t.name}</div>
            <div style={{ fontSize: '12px', color: colors.muted }}>{t.role}</div>
          </div>
          <StatusBadge status={t.status} />
          <div style={{ fontSize: '12px', color: colors.muted, textAlign: 'right' }}>
            {t.current_task ? `Task: ${t.current_task}` : 'Idle'}
          </div>
        </div>
      ))}
    </div>
  )
}

// Screen 4: Hands
function HandsScreen() {
  const [hands, setHands] = useState([])
  const [loading, setLoading] = useState(true)
  const { subscribe } = useWebSocket('/paperclip/ws')

  // Fetch initial hands
  useEffect(() => {
    const fetchHands = async () => {
      setLoading(true)
      try {
        const r = await fetch('/paperclip/api/hands')
        if (r.ok) {
          setHands(await r.json())
        }
      } catch (e) {
        console.error('Failed to fetch hands:', e)
      }
      setLoading(false)
    }
    fetchHands()
  }, [])

  // Subscribe to hand status updates
  useEffect(() => {
    return subscribe((msg) => {
      if (msg.type === 'hand_update') {
        setHands(prev => prev.map(h =>
          h.id === msg.hand_id
            ? { ...h, status: msg.status, current_task: msg.current_task }
            : h
        ))
      }
    })
  }, [subscribe])

  if (loading && !hands.length) return <div>Loading hands...</div>

  return (
    <div>
      <h1 style={{ fontFamily: 'Lora', fontSize: '28px', marginBottom: '20px', color: colors.accent }}>
        Hands (11)
      </h1>

      {hands.map(h => (
        <div key={h.id} style={{
          backgroundColor: colors.card,
          border: `1px solid ${colors.border}`,
          borderRadius: '8px',
          padding: '16px',
          marginBottom: '12px',
          display: 'grid',
          gridTemplateColumns: '100px 1fr 150px 150px',
          gap: '16px',
          alignItems: 'center',
        }}>
          <strong style={{ color: colors.accent }}>{h.id}</strong>
          <div>
            <div style={{ fontWeight: 500, marginBottom: '4px' }}>{h.name}</div>
            <div style={{ fontSize: '12px', color: colors.muted }}>{h.role}</div>
          </div>
          <StatusBadge status={h.status} />
          <div style={{ fontSize: '12px', color: colors.muted, textAlign: 'right' }}>
            {h.current_task ? `Task: ${h.current_task}` : 'Idle'}
          </div>
        </div>
      ))}
    </div>
  )
}

// Screen 5: Task History
function TaskHistory() {
  const [tasks, setTasks] = useState([])
  const { subscribe } = useWebSocket('/paperclip/ws')

  // Fetch initial tasks
  useEffect(() => {
    const fetchTasks = async () => {
      try {
        const r = await fetch('/paperclip/api/tasks?limit=100')
        if (r.ok) {
          const result = await r.json()
          setTasks(result.items || [])
        }
      } catch (e) {
        console.error('Failed to fetch tasks:', e)
      }
    }
    fetchTasks()
  }, [])

  // Subscribe to task updates
  useEffect(() => {
    return subscribe((msg) => {
      if (msg.type === 'task_update') {
        setTasks(prev => prev.map(t =>
          t.id === msg.task_id
            ? { ...t, status: msg.status, output: msg.output }
            : t
        ))
      } else if (msg.type === 'task_created') {
        // New task arrived, add to beginning
        setTasks(prev => [{
          id: msg.task_id,
          instruction: msg.instruction,
          assigned_to: msg.assigned_to,
          assigned_to_type: msg.assigned_to_type,
          status: 'pending',
          created_at: new Date().toISOString(),
        }, ...prev])
      }
    })
  }, [subscribe])

  return (
    <div>
      <h1 style={{ fontFamily: 'Lora', fontSize: '28px', marginBottom: '20px', color: colors.accent }}>
        Task History
      </h1>

      {tasks && tasks.map(t => (
        <TaskCard key={t.id} task={t} />
      ))}
    </div>
  )
}

// Main App
export default function App() {
  const [activeTab, setActiveTab] = useState('command')
  const [taskUpdated, setTaskUpdated] = useState(0)
  const { connected: wsConnected } = useWebSocket('/paperclip/ws')

  const tabs = [
    { id: 'command', label: 'Command Centre', icon: '⚡' },
    { id: 'fleet', label: 'Fleet', icon: '📊' },
    { id: 'terminals', label: 'Terminals', icon: '🖥️' },
    { id: 'hands', label: 'Hands', icon: '👐' },
    { id: 'history', label: 'Task History', icon: '📋' },
    { id: 'costs', label: 'Costs', icon: '💰' },
    { id: 'audit', label: 'Audit Log', icon: '📋' },
  ]

  return (
    <div style={{ minHeight: '100vh', backgroundColor: colors.bg, color: colors.text }}>
      {/* Header */}
      <header style={{
        backgroundColor: colors.card,
        borderBottom: `1px solid ${colors.border}`,
        padding: '16px 24px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <h1 style={{ margin: 0, fontSize: '20px', fontFamily: 'Lora', color: colors.accent }}>
          🎯 Paperclip
        </h1>
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <div style={{ fontSize: '12px', color: colors.muted }}>AMTL Fleet Command Centre</div>
          <div style={{
            display: 'inline-block',
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: wsConnected ? colors.success : colors.error,
            marginRight: '4px',
          }} title={wsConnected ? 'WebSocket connected' : 'WebSocket disconnected'} />
          <span style={{ fontSize: '11px', color: wsConnected ? colors.success : colors.error }}>
            {wsConnected ? 'Live' : 'Polling'}
          </span>
        </div>
      </header>

      {/* Tab navigation */}
      <nav style={{
        backgroundColor: colors.card,
        borderBottom: `1px solid ${colors.border}`,
        display: 'flex',
        padding: '8px 24px',
        gap: '8px',
      }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              background: 'none',
              border: 'none',
              color: activeTab === tab.id ? colors.accent : colors.muted,
              padding: '8px 12px',
              cursor: 'pointer',
              fontSize: '12px',
              fontWeight: activeTab === tab.id ? 600 : 400,
              borderBottom: activeTab === tab.id ? `2px solid ${colors.accent}` : 'none',
              marginBottom: activeTab === tab.id ? '-8px' : '0',
              transition: 'color 0.2s',
            }}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
        {activeTab === 'command' && <CommandCentre onTaskCreated={() => setTaskUpdated(t => t + 1)} wsConnected={wsConnected} />}
        {activeTab === 'fleet' && <FleetDashboard />}
        {activeTab === 'terminals' && <TerminalsScreen />}
        {activeTab === 'hands' && <HandsScreen />}
        {activeTab === 'history' && <TaskHistory />}
        {activeTab === 'costs' && <CostDashboard />}
        {activeTab === 'audit' && <AuditLog />}
      </main>
    </div>
  )
}
