import { useState, useMemo, Fragment } from 'react'
import PropertyDetail from './PropertyDetail'

function docTypeBadge(property) {
  const docType = property.raw?.doc_type || ''
  const source = property.source

  if (source === 'hud') return <span className="badge hud">HUD REO</span>

  if (docType.includes('TRUSTEE'))
    return <span className="badge nts">NTS</span>
  if (docType === 'NOTICE OF SALE')
    return <span className="badge nos">NOS</span>
  if (docType === 'NOTICE OF DEFAULT')
    return <span className="badge nod">NOD</span>
  if (docType === 'LIS PENDENS')
    return <span className="badge lp">LP</span>

  return <span className="badge">{docType || source}</span>
}

function formatPrice(price) {
  if (!price || price === 0) return '—'
  return '$' + Number(price).toLocaleString(undefined, { maximumFractionDigits: 0 })
}

function loanAge(origRecDate) {
  if (!origRecDate) return '—'
  const [month, day, year] = origRecDate.split('/')
  const orig = new Date(+year, +month - 1, +day)
  const now = new Date()
  const years = ((now - orig) / (365.25 * 24 * 60 * 60 * 1000))
  if (years < 1) return `${Math.round(years * 12)}mo`
  return `${years.toFixed(1)}yr`
}

function foreAge(foreEffective) {
  if (!foreEffective) return '—'
  const [month, day, year] = foreEffective.split('/')
  const d = new Date(+year, +month - 1, +day)
  const now = new Date()
  const days = Math.floor((now - d) / (24 * 60 * 60 * 1000))
  if (days < 0) return 'future'
  if (days < 30) return `${days}d`
  if (days < 365) return `${Math.floor(days / 30)}mo`
  return `${(days / 365).toFixed(1)}yr`
}

function scoreColor(score) {
  if (score >= 70) return 'var(--green)'
  if (score >= 55) return 'var(--yellow)'
  if (score >= 40) return 'var(--orange)'
  return 'var(--red)'
}

function SortArrow({ column, sortConfig }) {
  if (sortConfig.key !== column) return <span className="sort-arrow">↕</span>
  return (
    <span className="sort-arrow active">
      {sortConfig.dir === 'asc' ? '↑' : '↓'}
    </span>
  )
}

export default function PropertyTable({ properties, loading, onPropertyUpdate }) {
  const [expandedId, setExpandedId] = useState(null)
  const [sortConfig, setSortConfig] = useState({ key: 'score', dir: 'desc' })

  const handleSort = (key) => {
    setSortConfig(prev => ({
      key,
      dir: prev.key === key && prev.dir === 'desc' ? 'asc' : 'desc',
    }))
  }

  const sorted = useMemo(() => {
    const arr = [...properties]
    const { key, dir } = sortConfig
    arr.sort((a, b) => {
      let va, vb
      switch (key) {
        case 'score':
          va = a._score || 0; vb = b._score || 0
          break
        case 'address':
          va = a.address || ''; vb = b.address || ''
          break
        case 'city':
          va = a.city || ''; vb = b.city || ''
          break
        case 'county':
          va = a.raw?.county || ''; vb = b.raw?.county || ''
          break
        case 'owner_name':
          va = a.raw?.owner_name || ''; vb = b.raw?.owner_name || ''
          break
        case 'contact':
          va = a._contact ? 1 : 0; vb = b._contact ? 1 : 0
          break
        case 'price':
          va = a.price || 0; vb = b.price || 0
          break
        case 'equity':
          va = a._valuation?.estimated_equity || 0; vb = b._valuation?.estimated_equity || 0
          break
        case 'loan_age':
          va = a.raw?.orig_rec_date || '99/99/9999'; vb = b.raw?.orig_rec_date || '99/99/9999'
          va = va.slice(6) + va.slice(0,2) + va.slice(3,5)
          vb = vb.slice(6) + vb.slice(0,2) + vb.slice(3,5)
          break
        case 'doc_type':
          va = a.raw?.doc_type || ''; vb = b.raw?.doc_type || ''
          break
        case 'fore_effective':
          va = a.raw?.fore_effective || ''; vb = b.raw?.fore_effective || ''
          va = va.slice(6) + va.slice(0,2) + va.slice(3,5)
          vb = vb.slice(6) + vb.slice(0,2) + vb.slice(3,5)
          break
        default:
          return 0
      }
      if (va < vb) return dir === 'asc' ? -1 : 1
      if (va > vb) return dir === 'asc' ? 1 : -1
      return 0
    })
    return arr
  }, [properties, sortConfig])

  if (loading) {
    return <p style={{ color: 'var(--text-dim)', padding: '20px' }}>Loading...</p>
  }

  if (properties.length === 0) {
    return <p style={{ color: 'var(--text-dim)', padding: '20px' }}>No properties found.</p>
  }

  const columns = [
    { key: 'score', label: 'Score' },
    { key: 'price', label: 'Orig Mortgage' },
    { key: 'equity', label: 'Est. Equity' },
    { key: 'loan_age', label: 'Loan Age' },
    { key: 'doc_type', label: 'Type' },
    { key: 'fore_effective', label: 'Effective' },
    { key: 'fore_age', label: 'Age' },
  ]

  return (
    <table className="property-table">
      <thead>
        <tr>
          {columns.map(col => (
            <th key={col.key} onClick={() => handleSort(col.key)}>
              {col.label}
              <SortArrow column={col.key} sortConfig={sortConfig} />
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map(prop => {
          const id = prop._id
          const isExpanded = expandedId === id
          return (
            <Fragment key={id}>
              <tr
                className="clickable"
                onClick={() => setExpandedId(isExpanded ? null : id)}
              >
                <td>
                  <span className="score-pill" style={{ color: scoreColor(prop._score) }}>
                    {prop._score?.toFixed(1) || '—'}
                  </span>
                </td>
                <td className="price">{formatPrice(prop.price)}</td>
                <td className="price" style={{
                  color: prop._valuation?.estimated_equity > 0 ? 'var(--green)'
                       : prop._valuation?.estimated_equity < 0 ? 'var(--red)' : 'var(--text-dim)'
                }}>
                  {prop._valuation?.estimated_equity != null
                    ? formatPrice(prop._valuation.estimated_equity)
                    : '—'}
                </td>
                <td>{loanAge(prop.raw?.orig_rec_date)}</td>
                <td>{docTypeBadge(prop)}</td>
                <td>{prop.raw?.fore_effective || '—'}</td>
                <td>{foreAge(prop.raw?.fore_effective)}</td>
              </tr>
              {isExpanded && (
                <tr className="detail-row">
                  <td colSpan={columns.length}>
                    <PropertyDetail
                      property={prop}
                      onPropertyUpdate={onPropertyUpdate}
                    />
                  </td>
                </tr>
              )}
            </Fragment>
          )
        })}
      </tbody>
    </table>
  )
}
