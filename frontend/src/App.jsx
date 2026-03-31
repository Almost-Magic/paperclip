import React, { useState, useEffect } from 'react'

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

// Hook: usePolling
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
function CommandCentre({ onTaskCreated }) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const { data: tasks } = usePolling('/paperclip/api/tasks', 5000)

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
  const { data: terminals, loading } = usePolling('/paperclip/api/terminals', 3000)

  if (loading && !terminals) return <div>Loading terminals...</div>

  return (
    <div>
      <h1 style={{ fontFamily: 'Lora', fontSize: '28px', marginBottom: '20px', color: colors.accent }}>
        Terminals (7)
      </h1>

      {terminals && terminals.map(t => (
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
  const { data: hands, loading } = usePolling('/paperclip/api/hands', 3000)

  if (loading && !hands) return <div>Loading hands...</div>

  return (
    <div>
      <h1 style={{ fontFamily: 'Lora', fontSize: '28px', marginBottom: '20px', color: colors.accent }}>
        Hands (11)
      </h1>

      {hands && hands.map(h => (
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
  const { data: tasks } = usePolling('/paperclip/api/tasks', 5000)

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

  const tabs = [
    { id: 'command', label: 'Command Centre', icon: '⚡' },
    { id: 'fleet', label: 'Fleet', icon: '📊' },
    { id: 'terminals', label: 'Terminals', icon: '🖥️' },
    { id: 'hands', label: 'Hands', icon: '👐' },
    { id: 'history', label: 'Task History', icon: '📋' },
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
        <div style={{ fontSize: '12px', color: colors.muted }}>AMTL Fleet Command Centre</div>
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
        {activeTab === 'command' && <CommandCentre onTaskCreated={() => setTaskUpdated(t => t + 1)} />}
        {activeTab === 'fleet' && <FleetDashboard />}
        {activeTab === 'terminals' && <TerminalsScreen />}
        {activeTab === 'hands' && <HandsScreen />}
        {activeTab === 'history' && <TaskHistory />}
      </main>
    </div>
  )
}
