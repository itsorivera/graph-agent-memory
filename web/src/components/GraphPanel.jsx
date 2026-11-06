import { useEffect, useMemo, useRef, useState } from 'react'
import { InteractiveNvlWrapper } from '@neo4j-nvl/react'
import { colorForLabels, LAYER_LABELS } from '../palette.js'

function caption(node) {
  const p = node.properties ?? {}
  const text = p.name || p.title || p.preference || p.content || p.task ||
    p.action || p.actionTaken || p.tool_name || p.toolName || node.labels?.[0] || node.id
  return String(text).slice(0, 55)
}

export default function GraphPanel({ refreshKey, onError, ready, module, sessionId, savedReplay, onReplayChange }) {
  const [layer, setLayer] = useState('all')
  const [scope, setScope] = useState('current')
  const [graph, setGraph] = useState({ nodes: [], relationships: [] })
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [localError, setLocalError] = useState(null)
  const [reload, setReload] = useState(0)
  const [nams, setNams] = useState(false)
  const nvl = useRef(null)

  useEffect(() => {
    if (!ready) return
    let cancelled = false
    fetch('/api/replays').then(r => r.json()).then(d => { if (!cancelled) setRuns(d.runs ?? []) }).catch(() => {})
    return () => { cancelled = true }
  }, [ready, refreshKey, reload])

  useEffect(() => {
    if (!ready) return
    let cancelled = false
    const isReplay = !nams && scope.startsWith('replay:')
    setLoading(true); setLocalError(null)
    onReplayChange(isReplay ? { pending: true } : null)
    const activeSession = scope.startsWith('session:') ? scope.slice(8) : scope === 'current' ? sessionId : null
    const url = nams ? '/api/graph/nams' : scope.startsWith('replay:')
      ? `/api/replays/${encodeURIComponent(scope.slice(7))}`
      : `/api/graph?layer=${layer}${activeSession ? `&session_id=${encodeURIComponent(activeSession)}` : ''}`
    fetch(url).then(r => { if (!r.ok) throw new Error(`Graph request failed (HTTP ${r.status})`); return r.json() })
      .then(data => { if (!cancelled) { setGraph(data.graph ?? data); onReplayChange(data.graph ? data : null); setSelectedId(null) } })
      .catch(e => {
        if (cancelled) return
        setLocalError(e.message); onError?.(e.message)
        if (isReplay) onReplayChange({ loadError: e.message })
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [ready, layer, scope, sessionId, refreshKey, reload, nams, onError, onReplayChange])

  const nodes = useMemo(() => (graph.nodes ?? []).map(n => ({ id: String(n.id), caption: caption(n), color: colorForLabels(n.labels).fill, size: 32, captionSize: 2 })), [graph])
  const rels = useMemo(() => (graph.relationships ?? []).map(r => ({ id: String(r.id), from: String(r.from), to: String(r.to), caption: r.type === 'RELATED_TO' && r.properties?.type ? r.properties.type : r.type })), [graph])
  // NVL registers onLayoutDone once, at initialization; read the current IDs through a ref
  // so a later graph (another view or layer) is fitted instead of the first one.
  const nodeIds = useRef([])
  nodeIds.current = nodes.map(n => n.id)
  const fitAll = () => { if (nodeIds.current.length) nvl.current?.fit(nodeIds.current) }
  useEffect(() => {
    const timer = setTimeout(fitAll, 600)
    return () => clearTimeout(timer)
  }, [nodes])
  const nodeById = useMemo(() => new Map((graph.nodes ?? []).map(n => [String(n.id), n])), [graph])
  const selected = nodeById.get(selectedId)
  const adjacent = selected ? rels.filter(r => r.from === selectedId || r.to === selectedId) : []
  const selectNode = node => { setSelectedId(String(node.id)); nvl.current?.fit?.([String(node.id)]) }
  const selectedReplay = runs.find(r => scope === `replay:${r.id}`)

  return <div className="graph-panel"><div className="panel-header"><span className="panel-title">Memory graph</span><div className="graph-controls">
    <label className="sr-only" htmlFor="graph-view">Graph view</label><select id="graph-view" aria-label="Graph view" value={nams ? 'nams' : scope} disabled={nams} onChange={e => setScope(e.target.value)}>
      {nams && <option value="nams">Hosted NAMS workspace</option>}
      <option value="current">Current conversation</option><option value="all">All stored memory</option>{runs.map(r => <option key={r.id} value={`replay:${r.id}`}>Saved replay · {r.title}</option>)}
      {module > 1 && runs.filter(r => r.module > 1).flatMap(r => (r.session_ids ?? []).map(id => <option key={`${r.id}-${id}`} value={`session:${id}`}>Live memory · {r.title} · {id.split(':').slice(1).join(':') || id}</option>))}
    </select>
    <select aria-label="Memory layer" value={layer} disabled={scope.startsWith('replay:') || nams} onChange={e => setLayer(e.target.value)}>{['all', 'short_term', 'long_term', 'reasoning'].map(l => <option key={l} value={l}>{l.replace('_', ' ')}</option>)}</select>
    <button className="btn" onClick={() => setReload(k => k + 1)}>Refresh graph</button>
    <button className="btn" disabled={!nodes.length} onClick={fitAll}>Fit graph</button>
    {module === 5 && <label><input type="checkbox" checked={nams} onChange={e => setNams(e.target.checked)} /> NAMS</label>}
  </div></div>
  <div className="graph-canvas">
    {graph.truncated && <p className="graph-notice">Showing the newest bounded subset. Choose a conversation or replay for a complete lesson view.</p>}
    {!nams && scope.startsWith('replay:') && <p className="graph-notice">Recorded replay output · {selectedReplay?.title}. {savedReplay?.protocol} This is a saved projection. {module > 1 && selectedReplay?.module > 1 && selectedReplay.session_ids?.length > 0 && 'Choose Live memory for persisted links.'}</p>}
    {!nams && scope.startsWith('session:') && <p className="graph-notice">Live stored memory · {scope.slice(8)}</p>}
    {loading && <div className="graph-loading" role="status">Loading graph…</div>}
    {localError ? <div className="graph-empty">{localError}. Retry with Refresh graph.</div> : nodes.length ? <InteractiveNvlWrapper ref={nvl} nodes={nodes} rels={rels}
      nvlCallbacks={{ onLayoutDone: fitAll }}
      onInitializationError={error => setLocalError(`Graph initialization failed: ${String(error)}`)}
      mouseEventCallbacks={{ onNodeClick: selectNode, onPan: true, onZoom: true, onDrag: true }}
      nvlOptions={{ initialZoom: 1.2, allowDynamicMinZoom: true, disableTelemetry: true }} />
      : !loading && <div className="graph-empty">{module === 1 ? 'Module 1 is stateless. It does not create memory.' : nams && graph.unavailable ? 'NAMS workspace unavailable. Check access with make nams-check. For the fallback, run make s5-fresh-agent WITH_SKILL=fallback.' : nams ? 'No hosted skill versions are visible. On the hosted route, finish make nams-distill after seeding. At the five-minute cutoff, run make s5-fresh-agent WITH_SKILL=fallback.' : 'No memory in this view. Send a message, select a saved replay, or choose All stored memory.'}</div>}
    {nodes.length > 0 && <details className="graph-accessible-list"><summary>Inspect nodes by keyboard ({nodes.length})</summary>{graph.nodes.map(n => <button key={n.id} onClick={() => selectNode(n)}>{caption(n)}</button>)}</details>}
    <div className="graph-legend">{LAYER_LABELS.filter(l => module === 5 || l.key !== 'skills').map(l => <span key={l.key} className="legend-item"><span className="dot" style={{ backgroundColor: l.fill }} />{l.key.replace('_', ' ')}</span>)}</div>
  </div>
  {selected && <aside className="details-drawer"><div className="details-header"><div><strong>{caption(selected)}</strong><p>{selected.labels?.join(' · ')}</p></div><button aria-label="Close node details" onClick={() => setSelectedId(null)}>×</button></div>
    {adjacent.length > 0 && <div className="node-connections" role="group" aria-label="Connected nodes">{adjacent.map(rel => {
      const outgoing = rel.from === selectedId
      const neighbor = nodeById.get(outgoing ? rel.to : rel.from)
      return neighbor && <button className="btn" key={rel.id} onClick={() => selectNode(neighbor)}>
        {outgoing ? 'Outgoing' : 'Incoming'} · {rel.caption} · {caption(neighbor)}
      </button>
    })}</div>}
    <table className="details-table"><tbody>{Object.entries(selected.properties ?? {}).map(([key, value]) => <tr key={key}><th>{key}</th><td>{typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—')}</td></tr>)}</tbody></table></aside>}
  </div>
}
