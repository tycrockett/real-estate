import { useState, useEffect, useRef } from 'react'
import { fetchLeads, fetchQuoMessages, sendQuoMessage } from '../api'

export default function MessagesPage() {
  const [leads, setLeads] = useState([])
  const [selectedLeadId, setSelectedLeadId] = useState(null)
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [loadingMsgs, setLoadingMsgs] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    fetchLeads().then(setLeads)
  }, [])

  const selected = leads.find(l => l.id === selectedLeadId)
  const prop = selected?.property_data || {}
  const raw = prop.raw || {}
  const selectedPhone = (selected?.phones || [])[0]?.phone || ''

  const loadMessages = async (phone) => {
    if (!phone) { setMessages([]); return }
    setLoadingMsgs(true)
    const result = await fetchQuoMessages(phone)
    setMessages(result.messages || [])
    setLoadingMsgs(false)
  }

  useEffect(() => {
    if (selectedPhone) {
      loadMessages(selectedPhone)
    } else {
      setMessages([])
    }
  }, [selectedLeadId, selectedPhone])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-refresh every 10 seconds when a conversation is open
  useEffect(() => {
    if (!selectedPhone) return
    const interval = setInterval(() => loadMessages(selectedPhone), 10000)
    return () => clearInterval(interval)
  }, [selectedPhone])

  const handleSend = async () => {
    if (!selectedPhone || !draft.trim()) return
    setSending(true)
    setError(null)

    const result = await sendQuoMessage(selected.id, selectedPhone, draft.trim())
    if (result.error) {
      setError(result.error)
    } else {
      setDraft('')
      await loadMessages(selectedPhone)
    }
    setSending(false)
  }

  const handleSelect = (lead) => {
    setSelectedLeadId(lead.id)
    setError(null)
  }

  return (
    <div className="messages-page">
      {/* Left — lead list */}
      <div className="msg-list">
        <div className="msg-list-header">
          <span className="msg-list-title">Conversations</span>
        </div>
        <div className="msg-list-items">
          {leads.length === 0 && (
            <p className="leads-empty">No leads yet.</p>
          )}
          {leads.map(lead => {
            const lp = lead.property_data || {}
            const lr = lp.raw || {}
            const phone = (lead.phones || [])[0]?.phone
            if (!phone) return null
            return (
              <div
                key={lead.id}
                className={`msg-list-item ${selectedLeadId === lead.id ? 'selected' : ''}`}
                onClick={() => handleSelect(lead)}
              >
                <div className="msg-item-name">{lr.owner_name || 'Unknown'}</div>
                <div className="msg-item-addr">{lp.address}, {lp.city}</div>
                <div className="msg-item-contact">
                  <span>{phone}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Right — conversation */}
      <div className="msg-conversation">
        {selected ? (
          <>
            <div className="msg-conv-header">
              <div>
                <span className="msg-conv-name">{raw.owner_name || 'Unknown'}</span>
                <span className="msg-conv-detail">
                  {prop.address}, {prop.city} — {selectedPhone}
                </span>
              </div>
            </div>

            {!selectedPhone && (
              <div className="msg-setup-warning">
                No phone number on this lead. Add one from the Leads tab.
              </div>
            )}

            {/* Messages */}
            <div className="msg-thread">
              {loadingMsgs && messages.length === 0 && (
                <div className="msg-empty">Loading messages...</div>
              )}
              {!loadingMsgs && messages.length === 0 && selectedPhone && (
                <div className="msg-empty">
                  No messages yet. Send the first one below.
                </div>
              )}
              {messages.map(msg => (
                <div key={msg.id} className={`msg-bubble ${msg.direction}`}>
                  <div className="msg-bubble-header">
                    <span className="msg-bubble-channel">SMS</span>
                    <span className="msg-bubble-time">
                      {new Date(msg.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="msg-bubble-body">{msg.body}</div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            {/* Compose */}
            {selectedPhone && (
              <div className="msg-compose">
                <div className="msg-compose-to">
                  To: {selectedPhone}
                </div>
                <div className="msg-compose-row">
                  <textarea
                    className="msg-input"
                    placeholder="Type your message..."
                    value={draft}
                    onChange={e => setDraft(e.target.value)}
                    rows={2}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        handleSend()
                      }
                    }}
                  />
                  <button
                    className="msg-send-btn"
                    onClick={handleSend}
                    disabled={sending || !draft.trim()}
                  >
                    {sending ? 'Sending...' : 'Send'}
                  </button>
                </div>
                {error && <div className="msg-error">{error}</div>}
              </div>
            )}
          </>
        ) : (
          <div className="msg-empty-state">
            Select a lead to view messages
          </div>
        )}
      </div>
    </div>
  )
}
