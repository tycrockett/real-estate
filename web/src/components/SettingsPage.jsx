import { useState, useEffect } from 'react'
import { fetchSmsTemplates, createSmsTemplate, updateSmsTemplate, deleteSmsTemplate } from '../api'

export default function SettingsPage() {
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState(null)
  const [editLabel, setEditLabel] = useState('')
  const [editBody, setEditBody] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchSmsTemplates().then(data => {
      setTemplates(data)
      setLoading(false)
    })
  }, [])

  const startEdit = (t) => {
    setEditingId(t.id)
    setEditLabel(t.label)
    setEditBody(t.body)
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditLabel('')
    setEditBody('')
  }

  const handleSave = async () => {
    if (!editLabel.trim()) return
    setSaving(true)
    const result = await updateSmsTemplate(editingId, { label: editLabel, body: editBody })
    if (result.id) {
      setTemplates(prev => prev.map(t => t.id === editingId ? result : t))
    }
    setSaving(false)
    setEditingId(null)
  }

  const handleAdd = async () => {
    const result = await createSmsTemplate('New Template', '')
    if (result.id) {
      setTemplates(prev => [...prev, result])
      startEdit(result)
    }
  }

  const handleDelete = async (id) => {
    const result = await deleteSmsTemplate(id)
    if (result.success) {
      setTemplates(prev => prev.filter(t => t.id !== id))
      if (editingId === id) cancelEdit()
    }
  }

  if (loading) {
    return <div className="settings-page"><p style={{ color: 'var(--text-dim)' }}>Loading...</p></div>
  }

  return (
    <div className="settings-page">
      <div className="settings-section">
        <div className="settings-section-header">
          <h2>SMS Templates</h2>
          <button className="btn-add-template" onClick={handleAdd}>+ Add Template</button>
        </div>
        <p className="settings-hint">
          Use <code>{'{name}'}</code> and <code>{'{address}'}</code> as placeholders. They'll be replaced with the lead's info when composing a message.
        </p>
        <div className="templates-list">
          {templates.map(t => (
            <div key={t.id} className={`template-card ${editingId === t.id ? 'editing' : ''}`}>
              {editingId === t.id ? (
                <>
                  <input
                    className="template-label-input"
                    value={editLabel}
                    onChange={e => setEditLabel(e.target.value)}
                    placeholder="Template name"
                    autoFocus
                  />
                  <textarea
                    className="template-body-input"
                    value={editBody}
                    onChange={e => setEditBody(e.target.value)}
                    placeholder="Message body..."
                    rows={5}
                  />
                  <div className="template-card-actions">
                    <button className="btn-template-save" onClick={handleSave} disabled={saving}>
                      {saving ? 'Saving...' : 'Save'}
                    </button>
                    <button className="btn-template-cancel" onClick={cancelEdit}>Cancel</button>
                  </div>
                </>
              ) : (
                <>
                  <div className="template-card-header">
                    <span className="template-card-label">{t.label}</span>
                    <div className="template-card-actions">
                      <button className="btn-template-edit" onClick={() => startEdit(t)}>Edit</button>
                      <button className="btn-template-delete" onClick={() => handleDelete(t.id)}>Delete</button>
                    </div>
                  </div>
                  <p className="template-card-body">{t.body || '(empty)'}</p>
                </>
              )}
            </div>
          ))}
          {templates.length === 0 && (
            <p className="settings-hint">No templates yet. Add one to get started.</p>
          )}
        </div>
      </div>
    </div>
  )
}
