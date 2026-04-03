import { useState, useEffect, useCallback } from 'react'
import { fetchProperties, fetchStats } from './api'
import StatsBar from './components/StatsBar'
import PropertyTable from './components/PropertyTable'
import LeadsPage from './components/LeadsPage'
import MessagesPage from './components/MessagesPage'
import AuthGate from './components/AuthGate'

function Dashboard() {
  const [properties, setProperties] = useState([])
  const [stats, setStats] = useState(null)
  const [filters, setFilters] = useState({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchStats().then(setStats)
  }, [])

  useEffect(() => {
    setLoading(true)
    fetchProperties(filters).then((data) => {
      setProperties(data)
      setLoading(false)
    })
  }, [filters])

  const handlePropertyUpdate = useCallback((propertyId, updates) => {
    setProperties(prev =>
      prev.map(p => p._id === propertyId ? { ...p, ...updates } : p)
    )
  }, [])

  return (
    <>
      <StatsBar stats={stats} filters={filters} onFilter={setFilters} />
      <div className="results-count">
        {loading ? 'Loading...' : `${properties.length} properties`}
      </div>
      <PropertyTable properties={properties} loading={loading} onPropertyUpdate={handlePropertyUpdate} />
    </>
  )
}

function AppContent() {
  const [tab, setTab] = useState('dashboard')

  return (
    <>
      <header>
        <nav className="tabs">
          <button className={`tab ${tab === 'dashboard' ? 'active' : ''}`} onClick={() => setTab('dashboard')}>
            Dashboard
          </button>
          <button className={`tab ${tab === 'leads' ? 'active' : ''}`} onClick={() => setTab('leads')}>
            Leads
          </button>
          <button className={`tab ${tab === 'messages' ? 'active' : ''}`} onClick={() => setTab('messages')}>
            Messages
          </button>
        </nav>
      </header>

      {tab === 'dashboard' && <Dashboard />}
      {tab === 'leads' && <LeadsPage />}
      {tab === 'messages' && <MessagesPage />}
    </>
  )
}

export default function App({ authEnabled }) {
  return (
    <AuthGate enabled={authEnabled}>
      <AppContent />
    </AuthGate>
  )
}
