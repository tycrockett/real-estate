export default function StatsBar({ stats, filters, onFilter }) {
  if (!stats) return null

  const nodCount = stats.by_doc_type.find(d => d.doc_type === 'NOTICE OF DEFAULT')?.count || 0
  const ntsCount = stats.by_doc_type
    .filter(d => d.doc_type?.includes('TRUSTEE') || d.doc_type === 'NOTICE OF SALE')
    .reduce((sum, d) => sum + d.count, 0)
  const lpCount = stats.by_doc_type.find(d => d.doc_type === 'LIS PENDENS')?.count || 0

  const isActive = (key, value) => {
    if (!value) return !filters[key]
    return filters[key] === value
  }

  const toggle = (key, value) => {
    if (filters[key] === value) {
      const next = { ...filters }
      delete next[key]
      onFilter(next)
    } else {
      onFilter({ ...filters, [key]: value })
    }
  }

  return (
    <div className="stats-bar">
      <div
        className={`stat-card clickable ${isActive('doc_type', undefined) && !filters.source ? 'active' : ''}`}
        onClick={() => onFilter({})}
      >
        <div className="label">Total Active</div>
        <div className="value">{stats.total.toLocaleString()}</div>
      </div>
      <div
        className={`stat-card clickable ${filters.doc_type === 'NOTICE OF DEFAULT' ? 'active' : ''}`}
        onClick={() => toggle('doc_type', 'NOTICE OF DEFAULT')}
      >
        <div className="label">Notice of Default</div>
        <div className="value nod">{nodCount}</div>
      </div>
      <div
        className={`stat-card clickable ${filters.doc_type === 'TRUSTEE' ? 'active' : ''}`}
        onClick={() => toggle('doc_type', 'TRUSTEE')}
      >
        <div className="label">Trustee Sale / NOS</div>
        <div className="value nts">{ntsCount}</div>
      </div>
      <div
        className={`stat-card clickable ${filters.doc_type === 'LIS PENDENS' ? 'active' : ''}`}
        onClick={() => toggle('doc_type', 'LIS PENDENS')}
      >
        <div className="label">Lis Pendens</div>
        <div className="value lp">{lpCount}</div>
      </div>
      <div className="prop-type-filter">
        <select
          className="prop-type-select"
          value={filters.property_type_raw || ''}
          onChange={e => {
            const val = e.target.value
            if (val) {
              onFilter({ ...filters, property_type_raw: val })
            } else {
              const next = { ...filters }
              delete next.property_type_raw
              onFilter(next)
            }
          }}
        >
          <option value="">Property Type</option>
          <option value="SFR">SFR</option>
          <option value="PUD">PUD</option>
          <option value="CONDOMINIUM">Condo</option>
          <option value="RESIDENTIAL (NEC)">Residential</option>
          <option value="MOBILE HOME">Mobile Home</option>
          <option value="MANUFACTURED HOME">Manufactured</option>
        </select>
      </div>
      <div className="county-chips">
        {stats.by_county.map(c => (
          <button
            className={`county-chip ${filters.county === c.county ? 'active' : ''}`}
            key={c.county}
            onClick={() => toggle('county', c.county)}
          >
            {c.county} <span className="county-chip-count">{c.count}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
