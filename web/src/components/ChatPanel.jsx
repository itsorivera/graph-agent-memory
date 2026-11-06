import { useEffect, useRef, useState } from 'react'
import { LAYER_LABELS } from '../palette.js'

function layerColor(key) {
  return LAYER_LABELS.find((l) => l.key === key) ?? null
}

function FormattedReply({ text }) {
  return String(text).split('\n').map((line, index) => <div key={index}>{line.split(/(\*\*[^*]+\*\*)/g).map((piece, n) => piece.startsWith('**') ? <strong key={n}>{piece.slice(2, -2)}</strong> : piece)}{!line && <br />}</div>)
}

export default function ChatPanel({ messages, onSend, sending, health }) {
  const [input, setInput] = useState('')
  const listRef = useRef(null)

  // Auto-scroll to the newest message.
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, sending])

  function submit() {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    onSend(text)
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const memoryLayers = Array.isArray(health?.memory_layers) ? health.memory_layers : []

  return (
    <div className="chat-panel">
      <div className="panel-header">
        <span className="panel-title">Chat</span>
        <div className="chat-badges">
          {health?.module != null && (
            <span className="badge module-badge">Module {health.module}</span>
          )}
          {memoryLayers.map((layer) => {
            const c = layerColor(layer)
            return (
              <span key={layer} className="badge layer-badge" title={c?.label ?? layer}>
                <span
                  className="dot"
                  style={{ backgroundColor: c?.fill ?? '#adb5bd', borderColor: c?.stroke ?? '#868e96' }}
                />
                {layer.replace(/_/g, ' ')}
              </span>
            )
          })}
        </div>
      </div>

      <div className="message-list" ref={listRef}>
        {messages.length === 0 && !sending && (
          <div className="chat-empty">
            Ask the SupportBot something — e.g. “Hi, I have a billing question.”
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble-row ${m.role === 'user' ? 'from-user' : 'from-agent'}`}>
            <div className={`bubble ${m.role === 'user' ? 'bubble-user' : 'bubble-agent'}`}>
              <FormattedReply text={m.content} />
            </div>
          </div>
        ))}
        {sending && (
          <div className="bubble-row from-agent">
            <div className="bubble bubble-agent bubble-loading">
              <span className="spinner" /> thinking…
            </div>
          </div>
        )}
      </div>

      <div className="chat-input-row">
        <label className="composer-label" htmlFor="chat-message">Message to SupportBot</label>
        <input
          id="chat-message"
          className="chat-input"
          type="text"
          placeholder="Type a message and press Enter…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={sending}
        />
        <button className="btn btn-send" onClick={submit} disabled={sending || !input.trim()}>
          {sending ? <span className="spinner spinner-light" /> : 'Send'}
        </button>
      </div>
    </div>
  )
}
