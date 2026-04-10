import { useState, useEffect } from 'react'
import { fetchLeads, updateLead, getShortCode } from '../api'

const LEAD_STATUSES = [
  'new', 'contacted', 'callback', 'interested',
  'negotiating', 'under_contract', 'closed', 'dead',
]

const STATUS_COLORS = {
  new: 'var(--accent)',
  contacted: 'var(--yellow)',
  callback: 'var(--orange)',
  interested: 'var(--green)',
  negotiating: 'var(--green)',
  under_contract: 'var(--green)',
  closed: 'var(--text-dim)',
  dead: 'var(--red)',
}

function fmt(val) {
  if (val == null) return '—'
  return '$' + Number(val).toLocaleString(undefined, { maximumFractionDigits: 0 })
}

function estimateReinstatement(raw, valuation) {
  if (!valuation?.monthly_payment || !raw?.fore_effective) return null
  const [m, d, y] = raw.fore_effective.split('/')
  const effDate = new Date(+y, +m - 1, +d)
  const now = new Date()
  const monthsBehind = Math.max(1, Math.round((now - effDate) / (30.44 * 24 * 60 * 60 * 1000)))
  const pastDue = monthsBehind * valuation.monthly_payment
  const lateFees = pastDue * 0.05
  const legalFees = 3000
  const total = pastDue + lateFees + legalFees
  return { monthsBehind, pastDue, lateFees, legalFees, total }
}

function statusLabel(s) {
  return s.replace(/_/g, ' ')
}

export default function LeadsPage() {
  const [leads, setLeads] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [linkCopied, setLinkCopied] = useState(false)

  const handleCopyLink = async () => {
    const result = await getShortCode(selected.property_id)
    if (result.code) {
      const url = `${window.location.origin}/?p=${result.code}`
      await navigator.clipboard.writeText(url)
      setLinkCopied(true)
      setTimeout(() => setLinkCopied(false), 2000)
    }
  }

  useEffect(() => {
    setLoading(true)
    fetchLeads(statusFilter || null).then(data => {
      setLeads(data)
      setLoading(false)
      if (data.length > 0 && !selectedId) {
        setSelectedId(data[0].id)
        setNotes(data[0].notes || '')
      }
    })
  }, [statusFilter])

  const selected = leads.find(l => l.id === selectedId)
  const prop = selected?.property_data || {}
  const raw = prop.raw || {}

  const handleSelect = (lead) => {
    setSelectedId(lead.id)
    setNotes(lead.notes || '')
    setLinkCopied(false)
  }

  const handleStatusChange = async (newStatus) => {
    const result = await updateLead(selected.id, { status: newStatus })
    if (result.lead) {
      setLeads(prev => prev.map(l => l.id === selected.id ? { ...l, ...result.lead } : l))
    }
  }

  const handleSaveNotes = async () => {
    setSaving(true)
    const result = await updateLead(selected.id, { notes })
    if (result.lead) {
      setLeads(prev => prev.map(l => l.id === selected.id ? { ...l, ...result.lead } : l))
    }
    setSaving(false)
  }

  const handleFieldUpdate = async (field, value) => {
    const result = await updateLead(selected.id, { [field]: value })
    if (result.lead) {
      setLeads(prev => prev.map(l => l.id === selected.id ? { ...l, ...result.lead } : l))
    }
  }

  if (loading) {
    return <div className="leads-page"><p style={{ color: 'var(--text-dim)' }}>Loading leads...</p></div>
  }

  return (
    <div className="leads-page">
      {/* Left panel — lead list */}
      <div className="leads-list">
        <div className="leads-list-header">
          <span className="leads-list-title">Leads ({leads.length})</span>
          <select
            className="leads-filter"
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value); setSelectedId(null) }}
          >
            <option value="">All Statuses</option>
            {LEAD_STATUSES.map(s => (
              <option key={s} value={s}>{statusLabel(s)}</option>
            ))}
          </select>
        </div>

        <div className="leads-list-items">
          {leads.length === 0 && (
            <p className="leads-empty">No leads yet. Create leads from the Dashboard tab.</p>
          )}
          {leads.map(lead => {
            const lp = lead.property_data || {}
            const lr = lp.raw || {}
            return (
              <div
                key={lead.id}
                className={`leads-list-item ${selectedId === lead.id ? 'selected' : ''}`}
                onClick={() => handleSelect(lead)}
              >
                <div className="leads-item-top">
                  <span className="leads-item-addr">{lp.address || lead.address}</span>
                  <span className="leads-item-status" style={{ color: STATUS_COLORS[lead.status] }}>
                    {statusLabel(lead.status)}
                  </span>
                </div>
                <div className="leads-item-bottom">
                  <span className="leads-item-city">{lp.city}, {lp.state}</span>
                  <span className="leads-item-owner">{lr.owner_name || ''}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Right panel — lead detail */}
      <div className="leads-detail">
        {selected ? (
          <>
            <div className="leads-detail-header">
              <div>
                <h2 className="leads-detail-addr">{prop.address}</h2>
                <span className="leads-detail-city">{prop.city}, {prop.state} {prop.zip_code}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button className="btn-lookup" onClick={handleCopyLink}>
                  {linkCopied ? 'Copied!' : 'Copy Link'}
                </button>
                <select
                  className="lead-status-select lead-status-lg"
                  value={selected.status}
                  onChange={e => handleStatusChange(e.target.value)}
                  style={{ color: STATUS_COLORS[selected.status] }}
                >
                  {LEAD_STATUSES.map(s => (
                    <option key={s} value={s}>{statusLabel(s)}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Contact */}
            <div className="leads-detail-section">
              <div className="leads-section-header">
                <span className="label">Contact</span>
                {raw.owner_name && (
                  <a
                    className="btn-lookup"
                    href={`https://www.fastpeoplesearch.com/name/${raw.owner_name.toLowerCase().replace(/\s+&\s+.*/,'').replace(/\s+/g, '-')}_${(prop.city || '').toLowerCase().replace(/\s+/g, '-')}-${(prop.state || '').toLowerCase()}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={e => e.stopPropagation()}
                  >
                    Look Up
                  </a>
                )}
              </div>
              <div className="leads-detail-grid">
                <div className="leads-detail-field">
                  <span className="leads-field-label">Owner</span>
                  <span className="leads-field-value">{raw.owner_name || '—'}</span>
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">Phone 1</span>
                  <EditableField
                    value={selected.phone_1}
                    onSave={v => handleFieldUpdate('phone_1', v)}
                    placeholder="No phone"
                    formatPhone
                  />
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">Phone 2</span>
                  <EditableField
                    value={selected.phone_2}
                    onSave={v => handleFieldUpdate('phone_2', v)}
                    placeholder="No phone"
                    formatPhone
                  />
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">Email</span>
                  <EditableField
                    value={selected.email_1}
                    onSave={v => handleFieldUpdate('email_1', v)}
                    placeholder="No email"
                  />
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">Mailing Address</span>
                  <span className="leads-field-value">
                    {raw.owner_mail_street || '—'}
                    {raw.owner_mail_city_state_zip ? `, ${raw.owner_mail_city_state_zip}` : ''}
                  </span>
                </div>
              </div>
            </div>

            {/* Equity + Property Info */}
            {selected.valuation && (selected.valuation.estimated_market_value || selected.valuation.remaining_balance) && (
              <div className="equity-prop-row">
                <div className="leads-detail-section equity-section-lead">
                  <span className="label">Equity Estimate</span>
                  <div className="equity-main">
                    <div className="equity-stat">
                      <span className="equity-stat-label">Est. Market Value</span>
                      <span className="equity-stat-value">{fmt(selected.valuation.estimated_market_value)}</span>
                      <span className="equity-stat-sub">Assessed: {fmt(selected.valuation.assessed_value)}</span>
                    </div>
                    <div className="equity-stat">
                      <span className="equity-stat-label">Est. Balance Owed</span>
                      <span className="equity-stat-value">{fmt(selected.valuation.remaining_balance)}</span>
                      <span className="equity-stat-sub">{fmt(selected.valuation.monthly_payment)}/mo at {selected.valuation.rate_used}%</span>
                    </div>
                    {selected.valuation.estimated_equity != null && (
                      <div className="equity-stat">
                        <span className="equity-stat-label">Est. Equity</span>
                        <span className="equity-stat-value" style={{
                          color: selected.valuation.estimated_equity > 0 ? 'var(--green)' : 'var(--red)'
                        }}>
                          {fmt(selected.valuation.estimated_equity)}
                        </span>
                        <span className="equity-stat-sub">{selected.valuation.equity_percent?.toFixed(1) ?? '—'}% equity</span>
                      </div>
                    )}
                  </div>
                  {(selected.valuation.bldg_sqft || selected.valuation.built_yr) && (
                    <div className="equity-extra">
                      {selected.valuation.bldg_sqft && <span>Sqft: {selected.valuation.bldg_sqft.toLocaleString()}</span>}
                      {selected.valuation.built_yr && <span>Built: {selected.valuation.built_yr}</span>}
                    </div>
                  )}
                </div>
                {(() => {
                  const reinstate = estimateReinstatement(raw, selected.valuation)
                  return (
                    <div className="leads-detail-section prop-info-section">
                      <span className="label">Deal Analysis</span>
                      {reinstate ? (
                        <div className="deal-layout">
                          <div className="equity-main">
                            <div className="equity-stat">
                              <span className="equity-stat-label">Est. Reinstatement</span>
                              <span className="equity-stat-value">{fmt(reinstate.total)}</span>
                              <span className="equity-stat-sub">{reinstate.monthsBehind}mo behind + late fees</span>
                            </div>
                            <div className="equity-stat">
                              <span className="equity-stat-label">Monthly Payment</span>
                              <span className="equity-stat-value">{fmt(selected.valuation.monthly_payment)}</span>
                              <span className="equity-stat-sub">at {selected.valuation.rate_used}%</span>
                            </div>
                          </div>
                          <div className="deal-detail">
                            <div className="deal-detail-line"><span>Past due ({reinstate.monthsBehind}mo)</span><span>{fmt(reinstate.pastDue)}</span></div>
                            <div className="deal-detail-line"><span>Late fees (5%)</span><span>{fmt(reinstate.lateFees)}</span></div>
                            <div className="deal-detail-line"><span>Legal/trustee est.</span><span>{fmt(reinstate.legalFees)}</span></div>
                          </div>
                        </div>
                      ) : (
                        <span className="deal-na">Insufficient data</span>
                      )}
                    </div>
                  )
                })()}
              </div>
            )}

            {/* Property Info */}
            <div className="leads-detail-section">
              <span className="label">Property</span>
              <div className="leads-detail-grid">
                <div className="leads-detail-field">
                  <span className="leads-field-label">Doc Type</span>
                  <span className="leads-field-value">{raw.doc_type || '—'}</span>
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">Lien Position</span>
                  <span className="leads-field-value">{raw.lien_position || '—'}</span>
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">Orig Mortgage</span>
                  <span className="leads-field-value">{raw.orig_mtg_amt ? fmt(raw.orig_mtg_amt) : '—'}</span>
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">Loan Originated</span>
                  <span className="leads-field-value">{raw.orig_rec_date || '—'}</span>
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">Recording Date</span>
                  <span className="leads-field-value">{raw.recording_date || '—'}</span>
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">Owner Occupied</span>
                  <span className="leads-field-value">{raw.owner_occupied === 'Y' ? 'Yes' : raw.owner_occupied === 'N' ? 'No' : '—'}</span>
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">Parcel ID</span>
                  <span className="leads-field-value">{raw.parcel_id || '—'}</span>
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">County</span>
                  <span className="leads-field-value">{raw.county || '—'}</span>
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">Lender</span>
                  <span className="leads-field-value">{raw.lender || '—'}</span>
                </div>
                <div className="leads-detail-field">
                  <span className="leads-field-label">Trustee</span>
                  <span className="leads-field-value">{raw.trustee || '—'}</span>
                </div>
              </div>
            </div>

            {/* Notes */}
            <div className="leads-detail-section">
              <span className="label">Notes</span>
              <div className="leads-notes-area">
                <textarea
                  className="leads-notes-input"
                  placeholder="Add notes about this lead..."
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  rows={4}
                />
                {notes !== (selected.notes || '') && (
                  <button className="btn-save-notes" onClick={handleSaveNotes} disabled={saving}>
                    {saving ? 'Saving...' : 'Save Notes'}
                  </button>
                )}
              </div>
            </div>

            <div className="leads-detail-meta">
              Created {selected.created_at?.split('T')[0]} | Updated {selected.updated_at?.split('T')[0]}
            </div>
          </>
        ) : (
          <div className="leads-detail-empty">
            <p>Select a lead to view details</p>
          </div>
        )}
      </div>
    </div>
  )
}

function formatE164(input) {
  const digits = input.replace(/\D/g, '')
  if (digits.length === 10) return `+1${digits}`
  if (digits.length === 11 && digits[0] === '1') return `+${digits}`
  return input
}

function EditableField({ value, onSave, placeholder, formatPhone }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value || '')

  const save = () => {
    const formatted = formatPhone ? formatE164(draft) : draft
    onSave(formatted)
    setEditing(false)
  }

  if (editing) {
    return (
      <div className="editable-field-edit">
        <input
          className="editable-input"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') save()
            if (e.key === 'Escape') { setDraft(value || ''); setEditing(false) }
          }}
          autoFocus
        />
        <button className="editable-save" onClick={save}>Save</button>
      </div>
    )
  }

  return (
    <span
      className={`leads-field-value editable ${value ? '' : 'empty'}`}
      onClick={() => { setDraft(value || ''); setEditing(true) }}
    >
      {value || placeholder || '—'}
    </span>
  )
}
