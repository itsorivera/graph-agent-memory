function TurnEvidence({ turn, index, last, message }) {
  return <details className="trace-details" open={last}>
    <summary>Turn {index + 1} · {turn.status || 'completed'} · {turn.tool_calls?.length || 0} calls · {turn.timing?.total_seconds ?? '—'}s</summary>
    {message && <><p><strong>Customer</strong> {message}</p><p><strong>SupportBot</strong> {turn.reply}</p></>}
    <p className="mono">Operation: {turn.request_id} · Business result: {turn.business_status || 'no action'}</p>
    {turn.timing?.input_tokens != null && <p>Tokens: {turn.timing.input_tokens} in · {turn.timing.output_tokens} out</p>}
    {turn.warnings?.length > 0 && <p role="status">Partial completion: {turn.warnings.map(w => `${w.phase}: ${w.error}`).join('; ')}. The operation receipt retains the reply.</p>}
    <details><summary>Retrieved evidence and memory writes</summary><pre>{JSON.stringify(turn.context, null, 2)}</pre></details>
    {!turn.tool_calls?.length && <p>No tools in this turn.</p>}
    {turn.tool_calls?.map((call, i) => <details key={i}><summary>{call.name} · {call.duration_ms}ms {call.origin && `· ${call.origin}`}</summary><pre>{JSON.stringify({ input: call.input, output: call.output }, null, 2)}</pre>{call.sql && <pre aria-label="Executed SQL">{call.sql}</pre>}</details>)}
  </details>
}

export default function TracePanel({ turns = [], replay }) {
  const recordings = replay?.branches ?? (replay?.turns ? [replay] : [])
  return <div className="trace-panel"><div className="panel-header">
    <span className="panel-title">Execution evidence · {replay ? 'Saved replay' : 'browser conversation'}</span>
  </div><div className="trace-body">
    {replay ? <>
      {replay.title && <p><strong>{replay.title}</strong></p>}
      {replay.pending && <p role="status">Loading saved replay…</p>}
      {replay.loadError && <p role="alert">{replay.loadError}. Retry with Refresh graph.</p>}
      {replay.status === 'starting' && <p role="status">This recording is in progress. Refresh graph after the terminal command finishes.</p>}
      {replay.status === 'failed' && <p role="alert">Recorded run failed{replay.error ? ` (${replay.error})` : ''}. Completed turns appear below.</p>}
      {replay.transcript_sha256 && <p>Transcript SHA-256 <code>{replay.transcript_sha256}</code></p>}
      {replay.process_ids && <p>Process IDs: {replay.process_ids.join(', ')}</p>}
      {recordings.map(recording => <section key={recording.id}>
        {replay.branches && <h3>{recording.title}</h3>}
        {recording.turns.map(({ message, result }, index) =>
          <TurnEvidence key={result.request_id ?? index} turn={result} message={message} index={index} last={index === recording.turns.length - 1} />)}
      </section>)}
      {!recordings.length && !replay.pending && !replay.loadError && <p>Inspect the snapshot’s nodes in the memory graph.</p>}
    </> : <>
      {!turns.length && <p className="trace-empty">Send a browser message or select a Saved replay to inspect its execution.</p>}
      {turns.map((turn, index) => <TurnEvidence key={turn.request_id ?? index} turn={turn} index={index} last={index === turns.length - 1} />)}
    </>}
  </div></div>
}
