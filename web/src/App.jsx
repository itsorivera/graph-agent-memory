import { useEffect, useState } from 'react'
import ChatPanel from './components/ChatPanel.jsx'
import GraphPanel from './components/GraphPanel.jsx'
import TracePanel from './components/TracePanel.jsx'
import EvalScorecard from './components/EvalScorecard.jsx'

const load = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback } catch { return fallback } }

export default function App() {
  const [health, setHealth] = useState(null)
  const [starting, setStarting] = useState(true)
  const [retry, setRetry] = useState(0)
  const [sessions, setSessions] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [accounts, setAccounts] = useState([])
  const [cases, setCases] = useState([])
  const [account, setAccount] = useState('')
  const [incident, setIncident] = useState('')
  const [authorize, setAuthorize] = useState(false)
  const [plan, setPlan] = useState('')
  const [graphRefreshKey, setGraphRefreshKey] = useState(0)
  const [savedReplay, setSavedReplay] = useState(null)
  const [evalOpen, setEvalOpen] = useState(false)

  useEffect(() => {
    let stopped = false, timer, attempts = 0
    setStarting(true)
    async function check() {
      try {
        const response = await fetch('/api/health')
        if (!response.ok) throw new Error('Backend is starting')
        const ready = await response.json()
        if (stopped) return
        setHealth(ready); setStarting(false); setError(null)
        const saved = load(`workshop-sessions-${ready.module}`, [])
        const active = saved[0] ?? { id: crypto.randomUUID(), messages: [] }
        setSessions(saved.length ? saved : [active]); setSessionId(active.id); setMessages(active.messages)
        const [a, c] = await Promise.all([fetch('/api/accounts'), fetch('/api/cases')])
        if (!stopped) { setAccounts(await a.json()); setCases(await c.json()) }
      } catch {
        if (!stopped) {
          attempts += 1
          if (attempts < 90) timer = setTimeout(check, Math.min(500 * attempts, 2000))
          else { setStarting(false); setError('Backend did not become ready. Check the server terminal, then Retry.') }
        }
      }
    }
    check()
    return () => { stopped = true; clearTimeout(timer) }
  }, [retry])

  useEffect(() => {
    if (!health || !sessionId) return
    const updated = [{ id: sessionId, messages }, ...sessions.filter(s => s.id !== sessionId)].slice(0, 20)
    localStorage.setItem(`workshop-sessions-${health.module}`, JSON.stringify(updated))
  }, [messages, sessionId, health, sessions])

  function switchSession(id) {
    const stored = load(`workshop-sessions-${health.module}`, [])
    const selected = stored.find(s => s.id === id) ?? { id, messages: [] }
    setSessions(stored); setSessionId(selected.id); setMessages(selected.messages)
    setAccount(''); setIncident(''); setAuthorize(false); setPlan('')
  }

  async function handleSend(text) {
    if (!text.trim() || sending || !health) return
    const requestId = crypto.randomUUID()
    setMessages(previous => [...previous, { role: 'user', content: text, request_id: requestId }])
    setSending(true); setError(null)
    const confirmed = authorize
    setAuthorize(false); setPlan('')
    try {
      const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId, request_id: requestId,
          account_email: account || null, incident_id: incident || null, authorize_refund: confirmed, policy_plan: plan || null }) })
      if (!response.ok) throw new Error(`Chat failed (HTTP ${response.status}). Operation ${requestId}; check its receipt before retrying.`)
      const data = await response.json()
      // The backend canonicalizes the session with a workspace namespace.
      if (data.session_id && data.session_id !== sessionId) setSessions(previous => previous.filter(s => s.id !== sessionId))
      setSessionId(data.session_id || sessionId)
      setMessages(previous => [...previous, { role: 'assistant', content: data.reply, ...data }])
      setGraphRefreshKey(k => k + 1)
    } catch (e) { setError(e.message) }
    finally { setSending(false) }
  }

  const history = sessions
  const traces = messages.filter(m => m.role === 'assistant')
  return <div className="app">
    <header className="header"><h1 className="header-title">Road to Agent Memory — Acme Cloud SupportBot</h1>
      <button className="btn btn-eval" disabled={!health} onClick={() => setEvalOpen(true)}>Evaluation lab</button></header>
    {starting && <div className="starting-banner" role="status">Starting backend… Connection is retried automatically.</div>}
    {error && <div className="error-banner" role="alert">{error}<button className="btn" onClick={() => setRetry(k => k + 1)}>Retry connection</button><button aria-label="Dismiss" onClick={() => setError(null)}>×</button></div>}
    <div className="operator-controls">
      <button className="btn" disabled={!health || sending} onClick={() => switchSession(crypto.randomUUID())}>New conversation</button>
      <label>Resume <select aria-label="Resume conversation" disabled={!health || sending} value={sessionId ?? ''} onChange={e => switchSession(e.target.value)}>
        {[...new Map([{ id: sessionId, messages }, ...history].filter(s => s.id).map(s => [s.id, s])).values()].map(s => <option key={s.id} value={s.id}>{s.id.slice(-12)}</option>)}</select></label>
      <label>Customer <select aria-label="Customer" value={account} onChange={e => { setAccount(e.target.value); setIncident(''); setAuthorize(false) }}><option value="">Unidentified</option>{accounts.map(a => <option key={a.email} value={a.email}>{a.name} · {a.email}</option>)}</select></label>
      <label>Billing case <select aria-label="Billing case" value={incident} onChange={e => { const c = cases.find(c => c.id === e.target.value); setIncident(c?.id || ''); if (c) setAccount(c.email); setAuthorize(false) }}><option value="">No refund action</option>{cases.map(c => <option key={c.id} value={c.id}>{c.customer} · {c.plan} · ${c.amount} · {c.description}</option>)}</select></label>
      <label><input type="checkbox" checked={authorize} disabled={!incident || sending} onChange={e => setAuthorize(e.target.checked)} /> Authorize selected refund for this message</label>
      <label>Policy question <select aria-label="Policy plan" value={plan} onChange={e => setPlan(e.target.value)}><option value="">No specific plan</option>{['Free', 'Pro', 'Enterprise'].map(p => <option key={p}>{p}</option>)}</select></label>
    </div>
    <main className="main"><section className="panel chat-panel-container"><ChatPanel messages={messages} onSend={handleSend} sending={sending || !health} health={health} /></section>
      <div className="right-column"><section className="panel graph-panel-container"><GraphPanel refreshKey={graphRefreshKey} onError={setError} ready={Boolean(health)} module={health?.module} sessionId={sessionId} savedReplay={savedReplay} onReplayChange={setSavedReplay} /></section>
        <section className="panel trace-panel-container"><TracePanel turns={traces} replay={savedReplay} /></section></div></main>
    <EvalScorecard module={health?.module} open={evalOpen} onClose={() => setEvalOpen(false)} />
  </div>
}
