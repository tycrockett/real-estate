import { useState } from 'react'
import { createLead, updateLead } from '../api'

function loanAge(origRecDate) {
  if (!origRecDate) return null
  const [month, day, year] = origRecDate.split('/')
  const orig = new Date(+year, +month - 1, +day)
  const now = new Date()
  const years = ((now - orig) / (365.25 * 24 * 60 * 60 * 1000))
  if (years < 1) return `${Math.round(years * 12)} months`
  return `${years.toFixed(1)} years`
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

function scoreColor(value) {
  if (value >= 70) return 'var(--green)'
  if (value >= 55) return 'var(--yellow)'
  if (value >= 40) return 'var(--orange)'
  return 'var(--red)'
}

function fmt(val) {
  if (val == null) return '—'
  return '$' + Number(val).toLocaleString(undefined, { maximumFractionDigits: 0 })
}

const SCORE_LABELS = {
  distress_stage: 'Distress Stage',
  loan_age: 'Loan Age',
  equity_estimate: 'Equity Estimate',
  time_pressure: 'Time Pressure',
  owner_occupied: 'Owner Occupied',
}

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

export default function PropertyDetail({ property, onPropertyUpdate }) {
  const raw = property.raw || {}
  const scores = property._scores || {}
  const valuation = property._valuation
  const lead = property._lead

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [notes, setNotes] = useState(lead?.notes || '')
  const [saving, setSaving] = useState(false)

  const handleCreateLead = async (e) => {
    e.stopPropagation()
    setLoading(true)
    setError(null)
    try {
      const result = await createLead(property._id)
      if (result.error) {
        setError(result.error)
      } else if (onPropertyUpdate) {
        onPropertyUpdate(property._id, { _lead: result.lead })
      }
    } catch (err) {
      setError('Request failed')
    }
    setLoading(false)
  }

  const handleStatusChange = async (e) => {
    e.stopPropagation()
    const newStatus = e.target.value
    const result = await updateLead(lead.id, { status: newStatus })
    if (result.lead && onPropertyUpdate) {
      onPropertyUpdate(property._id, { _lead: result.lead })
    }
  }

  const handleSaveNotes = async (e) => {
    e.stopPropagation()
    setSaving(true)
    const result = await updateLead(lead.id, { notes })
    if (result.lead && onPropertyUpdate) {
      onPropertyUpdate(property._id, { _lead: result.lead })
    }
    setSaving(false)
  }

  const fields = [
    { label: 'Owner Name', value: raw.owner_name },
    { label: 'Mailing Address', value: raw.owner_mail_street },
    { label: 'Mailing City/State/Zip', value: raw.owner_mail_city_state_zip },
    { label: 'Parcel ID', value: raw.parcel_id },
    { label: 'County', value: raw.county },
    { label: 'Address', value: `${property.address}, ${property.city}, ${property.state} ${property.zip_code}` },
    { label: 'Doc Type', value: raw.doc_type },
    { label: 'Recording Date', value: raw.recording_date },
    { label: 'Foreclosure Effective', value: raw.fore_effective },
    { label: 'Loan Originated', value: raw.orig_rec_date },
    { label: 'Loan Age', value: loanAge(raw.orig_rec_date) },
    { label: 'Lien Position', value: raw.lien_position },
    { label: 'Owner Occupied', value: raw.owner_occupied === 'Y' ? 'Yes' : raw.owner_occupied === 'N' ? 'No' : '—' },
    { label: 'Property Type', value: raw.property_type_raw || property.property_type },
    { label: 'Original Mortgage', value: raw.orig_mtg_amt ? `$${Number(raw.orig_mtg_amt).toLocaleString()}` : '—' },
    { label: 'Lender', value: raw.lender || '—' },
    { label: 'Trustee', value: raw.trustee || '—' },
  ]

  return (
    <div className="detail-panel">
      {/* Score breakdown */}
      {Object.keys(scores).length > 0 && (
        <div className="score-breakdown">
          <span className="label">Score Breakdown</span>
          <div className="score-bars">
            {Object.entries(scores).map(([key, s]) => (
              <div className="score-bar-row" key={key} title={s.detail}>
                <div className="score-bar-top">
                  <span className="score-bar-label">{SCORE_LABELS[key] || key}</span>
                  <span className="score-bar-value" style={{ color: scoreColor(s.value) }}>
                    {s.value.toFixed(0)}
                  </span>
                </div>
                <div className="score-bar-track">
                  <div
                    className="score-bar-fill"
                    style={{ width: `${s.value}%`, background: scoreColor(s.value) }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Equity + Property Info row */}
      {valuation && (valuation.estimated_market_value || valuation.remaining_balance) && (
        <div className="equity-prop-row">
          <div className="equity-section">
            <span className="label">Equity Estimate</span>
            <div className="equity-fields">
              <div className="equity-main">
                <div className="equity-stat">
                  <span className="equity-stat-label">Est. Market Value</span>
                  <span className="equity-stat-value">{fmt(valuation.estimated_market_value)}</span>
                  <span className="equity-stat-sub">Assessed: {fmt(valuation.assessed_value)}</span>
                </div>
                <div className="equity-stat">
                  <span className="equity-stat-label">Est. Balance Owed</span>
                  <span className="equity-stat-value">{fmt(valuation.remaining_balance)}</span>
                  <span className="equity-stat-sub">{fmt(valuation.monthly_payment)}/mo at {valuation.rate_used}%</span>
                </div>
                {valuation.estimated_equity != null && (
                  <div className="equity-stat">
                    <span className="equity-stat-label">Est. Equity</span>
                    <span className="equity-stat-value" style={{
                      color: valuation.estimated_equity > 0 ? 'var(--green)' : 'var(--red)'
                    }}>
                      {fmt(valuation.estimated_equity)}
                    </span>
                    <span className="equity-stat-sub">{valuation.equity_percent?.toFixed(1) ?? '—'}% equity</span>
                  </div>
                )}
              </div>
              {(valuation.bldg_sqft || valuation.built_yr) && (
                <div className="equity-extra">
                  {valuation.bldg_sqft && <span>Sqft: {valuation.bldg_sqft.toLocaleString()}</span>}
                  {valuation.built_yr && <span>Built: {valuation.built_yr}</span>}
                </div>
              )}
            </div>
          </div>
          {(() => {
            const reinstate = estimateReinstatement(raw, valuation)
            return (
              <div className="prop-info-section">
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
                        <span className="equity-stat-value">{fmt(valuation.monthly_payment)}</span>
                        <span className="equity-stat-sub">at {valuation.rate_used}%</span>
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

      {/* Lead section */}
      <div className="lead-section">
        {lead ? (
          <>
            <div className="lead-header">
              <span className="label">Lead</span>
              <select
                className="lead-status-select"
                value={lead.status}
                onChange={handleStatusChange}
                onClick={e => e.stopPropagation()}
                style={{ color: STATUS_COLORS[lead.status] || 'var(--text)' }}
              >
                {LEAD_STATUSES.map(s => (
                  <option key={s} value={s}>{s.replace('_', ' ')}</option>
                ))}
              </select>
            </div>

            {/* Contact info */}
            {(lead.phone_1 || lead.email_1) && (
              <div className="lead-contact">
                {lead.phone_1 && <span className="lead-contact-item">{lead.phone_1}</span>}
                {lead.phone_2 && <span className="lead-contact-item">{lead.phone_2}</span>}
                {lead.phone_3 && <span className="lead-contact-item">{lead.phone_3}</span>}
                {lead.email_1 && <span className="lead-contact-item">{lead.email_1}</span>}
                {lead.email_2 && <span className="lead-contact-item">{lead.email_2}</span>}
              </div>
            )}

            {/* Notes */}
            <div className="lead-notes">
              <textarea
                className="lead-notes-input"
                placeholder="Add notes..."
                value={notes}
                onChange={e => setNotes(e.target.value)}
                onClick={e => e.stopPropagation()}
                rows={2}
              />
              {notes !== (lead.notes || '') && (
                <button className="btn-save-notes" onClick={handleSaveNotes} disabled={saving}>
                  {saving ? 'Saving...' : 'Save'}
                </button>
              )}
            </div>
          </>
        ) : (
          <div className="lead-create">
            <button className="btn-create-lead" onClick={handleCreateLead} disabled={loading}>
              {loading ? 'Creating...' : 'Create Lead'}
            </button>
            {error && <span className="contact-error">{error}</span>}
          </div>
        )}
      </div>

      {/* Property fields */}
      {fields.map(f => (
        <div className="field" key={f.label}>
          <span className="label">{f.label}</span>
          <span className="value">{f.value || '—'}</span>
        </div>
      ))}
    </div>
  )
}
