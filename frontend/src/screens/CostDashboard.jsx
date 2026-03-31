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

export function CostDashboard() {
  const [summary, setSummary] = useState(null)
  const [trend, setTrend] = useState([])
  const [byAgent, setByAgent] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        // Fetch cost summary
        const summaryRes = await fetch('/paperclip/api/costs/summary?hours=24')
        if (summaryRes.ok) setSummary(await summaryRes.json())

        // Fetch trend
        const trendRes = await fetch('/paperclip/api/costs/trend?days=7')
        if (trendRes.ok) setTrend(await trendRes.json())

        // Fetch by agent
        const agentRes = await fetch('/paperclip/api/costs/by-agent?hours=24')
        if (agentRes.ok) setByAgent(await agentRes.json())
      } catch (e) {
        console.error('Failed to fetch cost data:', e)
      }
      setLoading(false)
    }

    fetchData()
    const interval = setInterval(fetchData, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [])

  if (loading && !summary) {
    return <div style={{ color: colors.muted }}>Loading cost dashboard...</div>
  }

  return (
    <div>
      <h1 style={{ fontFamily: 'Lora', fontSize: '28px', marginBottom: '20px', color: colors.accent }}>
        💰 Cost Dashboard
      </h1>

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        {summary && (
          <>
            <div style={{
              backgroundColor: colors.card,
              border: `1px solid ${colors.border}`,
              borderRadius: '8px',
              padding: '16px',
            }}>
              <div style={{ fontSize: '12px', color: colors.muted, marginBottom: '8px', textTransform: 'uppercase' }}>Total Cost (24h)</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: colors.accent }}>
                ${summary.total_cost_aud?.toFixed(2) || '0.00'} AUD
              </div>
              <div style={{ fontSize: '11px', color: colors.muted, marginTop: '4px' }}>
                {summary.task_count || 0} tasks
              </div>
            </div>

            <div style={{
              backgroundColor: colors.card,
              border: `1px solid ${colors.border}`,
              borderRadius: '8px',
              padding: '16px',
            }}>
              <div style={{ fontSize: '12px', color: colors.muted, marginBottom: '8px', textTransform: 'uppercase' }}>Avg Cost/Task</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: colors.success }}>
                ${summary.avg_cost_aud?.toFixed(4) || '0.00'} AUD
              </div>
              <div style={{ fontSize: '11px', color: colors.muted, marginTop: '4px' }}>
                {summary.unique_agents || 0} agents used
              </div>
            </div>

            <div style={{
              backgroundColor: colors.card,
              border: `1px solid ${colors.border}`,
              borderRadius: '8px',
              padding: '16px',
            }}>
              <div style={{ fontSize: '12px', color: colors.muted, marginBottom: '8px', textTransform: 'uppercase' }}>Total Tokens</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: colors.warning }}>
                {(((summary.total_tokens_input || 0) + (summary.total_tokens_output || 0)) / 1000).toFixed(1)}K
              </div>
              <div style={{ fontSize: '11px', color: colors.muted, marginTop: '4px' }}>
                input + output
              </div>
            </div>
          </>
        )}
      </div>

      {/* Cost Trend Chart (7-day) */}
      <div style={{
        backgroundColor: colors.card,
        border: `1px solid ${colors.border}`,
        borderRadius: '8px',
        padding: '16px',
        marginBottom: '24px',
      }}>
        <h2 style={{ fontSize: '16px', fontFamily: 'Lora', color: colors.accent, marginBottom: '12px' }}>
          7-Day Cost Trend
        </h2>

        {trend?.daily_data && trend.daily_data.length > 0 ? (
          <div style={{
            display: 'flex',
            gap: '8px',
            height: '150px',
            alignItems: 'flex-end',
            justifyContent: 'space-around',
          }}>
            {trend.daily_data.map((day, i) => {
              const maxCost = Math.max(...trend.daily_data.map(d => d.cost_aud))
              const height = maxCost > 0 ? (day.cost_aud / maxCost) * 150 : 20
              return (
                <div
                  key={i}
                  style={{
                    flex: 1,
                    height: `${height}px`,
                    backgroundColor: colors.accent,
                    borderRadius: '4px',
                    position: 'relative',
                  }}
                  title={`${day.date}: $${day.cost_aud.toFixed(2)} (${day.task_count} tasks)`}
                />
              )
            })}
          </div>
        ) : (
          <div style={{ color: colors.muted, fontSize: '12px' }}>No cost data yet</div>
        )}

        {trend?.total_cost_aud && (
          <div style={{
            marginTop: '12px',
            fontSize: '12px',
            color: colors.muted,
            display: 'flex',
            justifyContent: 'space-between',
          }}>
            <span>Total: ${trend.total_cost_aud.toFixed(2)}</span>
            <span>Daily Avg: ${trend.avg_daily_aud?.toFixed(2) || '0.00'}</span>
          </div>
        )}
      </div>

      {/* Agent Cost Breakdown */}
      <div style={{
        backgroundColor: colors.card,
        border: `1px solid ${colors.border}`,
        borderRadius: '8px',
        padding: '16px',
      }}>
        <h2 style={{ fontSize: '16px', fontFamily: 'Lora', color: colors.accent, marginBottom: '12px' }}>
          Cost by Agent (24h)
        </h2>

        {byAgent?.agents && byAgent.agents.length > 0 ? (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${colors.border}` }}>
                <th style={{ padding: '8px', textAlign: 'left', color: colors.muted, fontSize: '12px' }}>Agent</th>
                <th style={{ padding: '8px', textAlign: 'right', color: colors.muted, fontSize: '12px' }}>Tasks</th>
                <th style={{ padding: '8px', textAlign: 'right', color: colors.muted, fontSize: '12px' }}>Total Cost</th>
                <th style={{ padding: '8px', textAlign: 'right', color: colors.muted, fontSize: '12px' }}>Avg Cost</th>
              </tr>
            </thead>
            <tbody>
              {byAgent.agents.map((agent, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${colors.border}` }}>
                  <td style={{ padding: '8px', color: colors.text, fontWeight: '500' }}>
                    {agent.agent_id}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', color: colors.muted }}>
                    {agent.task_count}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', color: colors.accent, fontWeight: '500' }}>
                    ${agent.total_cost_aud.toFixed(2)}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', color: colors.muted }}>
                    ${agent.avg_cost_aud.toFixed(4)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ color: colors.muted, fontSize: '12px' }}>No agent cost data</div>
        )}
      </div>
    </div>
  )
}
