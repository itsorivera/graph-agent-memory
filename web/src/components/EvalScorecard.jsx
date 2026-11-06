import { useEffect, useState } from 'react'

export default function EvalScorecard({ open, onClose, module }) {
  const storageKey = `workshop-eval-id-${module}`
  const [id, setId] = useState(null)
  useEffect(() => { setId(localStorage.getItem(storageKey)); setRun(null); setError(null) }, [storageKey])
  const [run, setRun] = useState(null)
  const [error, setError] = useState(null)
  const [starting, setStarting] = useState(false)
  async function start(reuse = false) {
    const next = reuse && id ? id : crypto.randomUUID()
    setId(next); localStorage.setItem(storageKey, next); setStarting(true); setError(null)
    try {
      const r = await fetch('/api/eval', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: next }) })
      if (!r.ok) throw new Error(`Evaluation start failed: ${r.status}`)
      setRun({ ...(await r.json()), questions: [] })
    } catch (e) { setError(e.message) }
    finally { setStarting(false) }
  }
  // Without a run started in this browser, show the latest saved run for this module,
  // e.g. one from `make eval MODULE=N`. Listing reads files only; it starts nothing.
  useEffect(() => {
    if (!open || id) return
    let cancelled = false
    fetch('/api/eval').then(r => r.json())
      .then(d => { const latest = (d.runs ?? []).find(r => r.module === module); if (!cancelled && latest) setId(latest.id) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [open, id, module])
  useEffect(() => {
    if (!open || !id) return
    let cancelled = false, timer
    async function poll() {
      try {
        const r = await fetch(`/api/eval/${encodeURIComponent(id)}`)
        if (!r.ok) throw new Error(`No evaluation result yet (HTTP ${r.status}). Retry start to recover this run.`)
        const data = await r.json()
        if (!cancelled) { setRun(data); setError(null); if (data.status === 'running') timer = setTimeout(poll, 1500) }
      } catch (e) { if (!cancelled) setError(e.message) }
    }
    poll(); return () => { cancelled = true; clearTimeout(timer) }
  }, [open, id, starting])
  if (!open) return null
  return <div className="modal-overlay"><div className="modal" role="dialog" aria-modal="true" aria-label="Controlled evaluation lab">
    <div className="modal-header"><h2>Controlled evaluation lab</h2><button aria-label="Close evaluation" onClick={onClose}>×</button></div>
    <div className="modal-body"><p>New runs use a private SQLite copy, unique memory fixtures and no business-action tools. They test retrieval under controlled conditions, not overall model quality.</p>
      <button className="btn" disabled={starting || run?.status === 'running'} onClick={() => start(false)}>Start new isolated evaluation</button>
      {error && <p role="alert">{error}<button className="btn" disabled={starting} onClick={() => start(true)}>Retry start / recover run</button></p>}
      {run && <p role="status">Module {run.module ?? module} · Run {id?.slice(-8)} · {run.status} · {run.questions?.length ?? 0}/4 questions recorded</p>}
      <ul className="eval-list">{run?.questions?.map(q => <li className="eval-item" key={q.id}><span aria-label={q.answered ? 'passed' : q.error ? 'error' : 'not answered'}>{q.answered ? '✅' : q.error ? '⚠️' : '❌'}</span><div><strong>{q.question}</strong><p>{q.answer ?? q.error}</p><p>Checks: {q.checks?.join(' · ')} · Sources: {q.sources?.join(', ') || 'none'}</p></div></li>)}</ul>
      {run?.error && <p role="alert">Run incomplete: {run.error}. Completed results remain above.</p>}
    </div></div></div>
}
