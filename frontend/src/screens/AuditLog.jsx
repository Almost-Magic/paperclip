import React, { useState, useEffect } from 'react'

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

const actionColors = {
  'task_created': colors.success,
  'task_completed': colors.success,
  'login': colors.accent,
  'preference_set': colors.warning,
  'command_routed': colors.accent,
  'cost_recorded': colors.warning,
  'default': colors.muted,
}

export function AuditLog() {
  const [entries, setEntries] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filterAction, setFilterAction] = useState('')
  const [offset, setOffset] = useState(0)
  const limit = 20

  const fetchData = async (off = 0) => {
    setLoading(true)
    try {
      // Fetch audit log
      const params = new URLSearchParams({
        hours: 24,
        limit: limit,
        offset: off,
      })
      if (filterAction) params.append('action', filterAction)

      const logsRes = await fetch(`/paperclip/api/audit-log?${params}`)
      if (logsRes.ok) setEntries(await logsRes.json())

      // Fetch summary
      const summaryRes = await fetch('/paperclip/api/audit-summary?hours=24')
      if (summaryRes.ok) setSummary(await summaryRes.json())
    } catch (e) {
      console.error('Failed to fetch audit log:', e)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchData(offset)
  }, [filterAction, offset])

  if (loading && !entries.entries) {
    return <div style={{ color: colors.muted }}>Loading audit log...</div>
  }

  const auditData = entries.entries || []
  const total = entries.total || 0
  const hasMore = entries.has_more || false

  return (
    <div>
      <h1 style={{ fontFamily: 'Lora', fontSize: '28px', marginBottom: '20px', color: colors.accent }}>
        📋 Audit Log
      </h1>

      {/* Summary Stats */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '24px' }}>
          <div style={{
            backgroundColor: colors.card,
            border: `1px solid ${colors.border}`,
            borderRadius: '8px',
            padding: '16px',
          }}>
            <div style={{ fontSize: '12px', color: colors.muted, marginBottom: '8px', textTransform: 'uppercase' }}>Total Events (24h)</div>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: colors.accent }}>
              {summary.total_events || 0}
            </div>
          </div>

          <div style={{
            backgroundColor: colors.card,
            border: `1px solid ${colors.border}`,
            borderRadius: '8px',
            padding: '16px',
          }}>
            <div style={{ fontSize: '12px', color: colors.muted, marginBottom: '8px', textTransform: 'uppercase' }}>Unique Users</div>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: colors.success }}>
              {summary.unique_users || 0}
            </div>
          </div>

          <div style={{
            backgroundColor: colors.card,
            border: `1px solid ${colors.border}`,
            borderRadius: '8px',
            padding: '16px',
          }}>
            <div style={{ fontSize: '12px', color: colors.muted, marginBottom: '8px', textTransform: 'uppercase' }}>Top Action</div>
            <div style={{ fontSize: '16px', fontWeight: 'bold', color: colors.warning }}>
              {Object.keys(summary.action_breakdown || {}).length > 0
                ? Object.entries(summary.action_breakdown).sort(([, a], [, b]) => b - a)[0][0]
                : 'N/A'}
            </div>
          </div>
        </div>
      )}

      {/* Filter */}
      <div style={{ marginBottom: '16px' }}>
        <label style={{ fontSize: '12px', color: colors.muted, display: 'block', marginBottom: '8px', textTransform: 'uppercase' }}>
          Filter by Action
        </label>
        <select
          value={filterAction}
          onChange={(e) => {
            setFilterAction(e.target.value)
            setOffset(0)
          }}
          style={{
            width: '200px',
            backgroundColor: colors.card,
            border: `1px solid ${colors.border}`,
            borderRadius: '8px',
            padding: '8px 12px',
            color: colors.text,
            fontSize: '14px',
            cursor: 'pointer',
          }}
        >
          <option value="">All Actions</option>
          <option value="task_created">Task Created</option>
          <option value="task_completed">Task Completed</option>
          <option value="login">Login</option>
          <option value="preference_set">Preference Set</option>
          <option value="command_routed">Command Routed</option>
          <option value="cost_recorded">Cost Recorded</option>
        </select>
      </div>

      {/* Audit Log Entries */}
      <div style={{
        backgroundColor: colors.card,
        border: `1px solid ${colors.border}`,
        borderRadius: '8px',
        overflow: 'hidden',
      }}>
        {auditData.length > 0 ? (
          <div>
            {auditData.map((entry, i) => (
              <div
                key={i}
                style={{
                  borderBottom: i < auditData.length - 1 ? `1px solid ${colors.border}` : 'none',
                  padding: '16px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '8px' }}>
                  <div>
                    <span style={{
                      display: 'inline-block',
                      backgroundColor: actionColors[entry.action] || actionColors.default,
                      color: colors.bg,
                      padding: '4px 8px',
                      borderRadius: '4px',
                      fontSize: '11px',
                      fontWeight: 'bold',
                      marginRight: '8px',
                    }}>
                      {entry.action}
                    </span>
                    <span style={{ color: colors.accent, fontWeight: '500' }}>
                      {entry.username}
                    </span>
                  </div>
                  <span style={{ fontSize: '11px', color: colors.muted }}>
                    {entry.created_at ? new Date(entry.created_at).toLocaleString() : 'N/A'}
                  </span>
                </div>

                <div style={{ fontSize: '12px', color: colors.muted, marginBottom: '8px' }}>
                  {entry.resource_type && <span>{entry.resource_type}</span>}
                  {entry.resource_id && <span> • {entry.resource_id}</span>}
                  {entry.ip_address && <span> • {entry.ip_address}</span>}
                </div>

                {entry.details && (
                  <pre style={{
                    backgroundColor: colors.bg,
                    border: `1px solid ${colors.border}`,
                    borderRadius: '4px',
                    padding: '8px 12px',
                    fontSize: '11px',
                    color: colors.accent,
                    margin: 0,
                    overflow: 'auto',
                    maxHeight: '100px',
                    fontFamily: 'JetBrains Mono',
                  }}>
                    {JSON.stringify(entry.details, null, 2)}
                  </pre>
                )}
              </div>
            ))}

            {/* Pagination */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '16px',
              borderTop: `1px solid ${colors.border}`,
              fontSize: '12px',
              color: colors.muted,
            }}>
              <span>
                Showing {offset + 1}-{Math.min(offset + limit, total)} of {total}
              </span>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  disabled={offset === 0}
                  style={{
                    backgroundColor: offset === 0 ? colors.border : colors.accent,
                    color: offset === 0 ? colors.muted : colors.bg,
                    border: 'none',
                    borderRadius: '4px',
                    padding: '4px 12px',
                    cursor: offset === 0 ? 'not-allowed' : 'pointer',
                    fontSize: '11px',
                  }}
                >
                  Previous
                </button>
                <button
                  onClick={() => setOffset(offset + limit)}
                  disabled={!hasMore}
                  style={{
                    backgroundColor: !hasMore ? colors.border : colors.accent,
                    color: !hasMore ? colors.muted : colors.bg,
                    border: 'none',
                    borderRadius: '4px',
                    padding: '4px 12px',
                    cursor: !hasMore ? 'not-allowed' : 'pointer',
                    fontSize: '11px',
                  }}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ padding: '24px', textAlign: 'center', color: colors.muted }}>
            No audit log entries found
          </div>
        )}
      </div>
    </div>
  )
}
