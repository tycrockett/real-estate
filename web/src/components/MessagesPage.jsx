import { useState, useEffect, useRef } from 'react'
import { fetchLeads, getMessages, sendMessage, getMessagingStatus } from '../api'

export default function MessagesPage() {
  const [leads, setLeads] = useState([])
  const [selectedLeadId, setSelectedLeadId] = useState(null)
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [subject, setSubject] = useState('')
  const [channel, setChannel] = useState('sms')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState(null)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    fetchLeads().then(setLeads)
    getMessagingStatus().then(setStatus)
  }, [])

  const selected = leads.find(l => l.id === selectedLeadId)
  const prop = selected?.property_data || {}
  const raw = prop.raw || {}

  useEffect(() => {
    if (selectedLeadId) {
      getMessages(selectedLeadId).then(setMessages)
    }
  }, [selectedLeadId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const getTo = () => {
    if (!selected) return ''
    if (channel === 'sms') return selected.phone_1 || selected.phone_2 || ''
    return selected.email_1 || ''
  }

  const handleSend = async () => {
    const to = getTo()
    if (!to || !draft.trim()) return

    setSending(true)
    setError(null)

    const result = await sendMessage(
      selectedLeadId,
      channel,
      to,
      draft.trim(),
      channel === 'email' ? subject : '',
    )

    if (result.error) {
      setError(result.error)
    } else {
      setDraft('')
      setSubject('')
      const updated = await getMessages(selectedLeadId)
      setMessages(updated)
    }
    setSending(false)
  }

  const handleSelect = (lead) => {
    setSelectedLeadId(lead.id)
    setError(null)
  }

  const refreshMessages = async () => {
    if (selectedLeadId) {
      const updated = await getMessages(selectedLeadId)
      setMessages(updated)
    }
  }

  // Auto-refresh every 10 seconds when a conversation is open
  useEffect(() => {
    if (!selectedLeadId) return
    const interval = setInterval(refreshMessages, 10000)
    return () => clearInterval(interval)
  }, [selectedLeadId])

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
            return (
              <div
                key={lead.id}
                className={`msg-list-item ${selectedLeadId === lead.id ? 'selected' : ''}`}
                onClick={() => handleSelect(lead)}
              >
                <div className="msg-item-name">{lr.owner_name || 'Unknown'}</div>
                <div className="msg-item-addr">{lp.address}, {lp.city}</div>
                <div className="msg-item-contact">
                  {lead.phone_1 && <span>{lead.phone_1}</span>}
                  {lead.email_1 && <span>{lead.email_1}</span>}
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
                  {prop.address}, {prop.city} — {raw.doc_type || ''}
                </span>
              </div>
              <div className="msg-channel-toggle">
                <button
                  className={`msg-channel-btn ${channel === 'sms' ? 'active' : ''}`}
                  onClick={() => setChannel('sms')}
                  disabled={!selected.phone_1}
                  title={selected.phone_1 || 'No phone number'}
                >
                  SMS
                </button>
                <button
                  className={`msg-channel-btn ${channel === 'email' ? 'active' : ''}`}
                  onClick={() => setChannel('email')}
                  disabled={!selected.email_1}
                  title={selected.email_1 || 'No email'}
                >
                  Email
                </button>
              </div>
            </div>

            {/* Setup warning */}
            {status && !status.twilio && channel === 'sms' && (
              <div className="msg-setup-warning">
                Twilio not configured. Add TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER to your .env file.
              </div>
            )}
            {status && !status.sendgrid && channel === 'email' && (
              <div className="msg-setup-warning">
                SendGrid not configured. Add SENDGRID_API_KEY and SENDGRID_FROM_EMAIL to your .env file.
              </div>
            )}

            {/* Messages */}
            <div className="msg-thread">
              {messages.length === 0 && (
                <div className="msg-empty">
                  No messages yet. Send the first one below.
                </div>
              )}
              {messages.map(msg => (
                <div key={msg.id} className={`msg-bubble ${msg.direction}`}>
                  <div className="msg-bubble-header">
                    <span className="msg-bubble-channel">{msg.channel.toUpperCase()}</span>
                    <span className="msg-bubble-to">to {msg.to_addr}</span>
                    <span className="msg-bubble-time">
                      {new Date(msg.created_at).toLocaleString()}
                    </span>
                  </div>
                  {msg.subject && <div className="msg-bubble-subject">{msg.subject}</div>}
                  <div className="msg-bubble-body">{msg.body}</div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            {/* Compose */}
            <div className="msg-compose">
              <div className="msg-compose-to">
                To: {getTo() || <span className="msg-no-contact">No {channel === 'sms' ? 'phone' : 'email'} on this lead</span>}
              </div>
              {channel === 'email' && (
                <input
                  className="msg-subject-input"
                  placeholder="Subject"
                  value={subject}
                  onChange={e => setSubject(e.target.value)}
                />
              )}
              <div className="msg-compose-row">
                <textarea
                  className="msg-input"
                  placeholder={`Type your ${channel === 'sms' ? 'message' : 'email'}...`}
                  value={draft}
                  onChange={e => setDraft(e.target.value)}
                  rows={channel === 'sms' ? 2 : 4}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey && channel === 'sms') {
                      e.preventDefault()
                      handleSend()
                    }
                  }}
                />
                <button
                  className="msg-send-btn"
                  onClick={handleSend}
                  disabled={sending || !draft.trim() || !getTo()}
                >
                  {sending ? 'Sending...' : 'Send'}
                </button>
              </div>
              {error && <div className="msg-error">{error}</div>}
            </div>
          </>
        ) : (
          <div className="msg-empty-state">
            Select a lead to start messaging
          </div>
        )}
      </div>
    </div>
  )
}
