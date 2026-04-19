import { useState, useEffect, useRef } from 'react'
import { fetchNotifications, fetchUnreadCount, markNotificationRead } from '../api'

function timeAgo(iso) {
  if (!iso) return ''
  const then = new Date(iso)
  const diff = (Date.now() - then.getTime()) / 1000
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export default function NotificationsBell({ onOpenLead }) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [unread, setUnread] = useState(0)
  const panelRef = useRef(null)

  const load = async () => {
    const [list, count] = await Promise.all([
      fetchNotifications(false),
      fetchUnreadCount(),
    ])
    setItems(Array.isArray(list) ? list : [])
    setUnread(count?.count ?? 0)
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const handleClick = async (n) => {
    if (!n.read) {
      await markNotificationRead(n.id)
      setItems(prev => prev.map(x => x.id === n.id ? { ...x, read: 1 } : x))
      setUnread(c => Math.max(0, c - 1))
    }
    if (n.lead_id && onOpenLead) {
      onOpenLead(n.lead_id)
      setOpen(false)
    }
  }

  const markAllRead = async () => {
    const unreadItems = items.filter(n => !n.read)
    await Promise.all(unreadItems.map(n => markNotificationRead(n.id)))
    setItems(prev => prev.map(x => ({ ...x, read: 1 })))
    setUnread(0)
  }

  return (
    <div className="notif-wrap" ref={panelRef}>
      <button
        className="notif-bell"
        onClick={() => { setOpen(o => !o); if (!open) load() }}
        title="Notifications"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
        </svg>
        {unread > 0 && <span className="notif-badge">{unread > 99 ? '99+' : unread}</span>}
      </button>

      {open && (
        <div className="notif-panel">
          <div className="notif-panel-header">
            <span>Notifications</span>
            {unread > 0 && (
              <button className="notif-mark-all" onClick={markAllRead}>Mark all read</button>
            )}
          </div>
          <div className="notif-panel-list">
            {items.length === 0 && (
              <div className="notif-empty">No notifications yet</div>
            )}
            {items.map(n => (
              <div
                key={n.id}
                className={`notif-item ${n.read ? '' : 'unread'}`}
                onClick={() => handleClick(n)}
              >
                <div className="notif-item-top">
                  <span className="notif-title">{n.title}</span>
                  <span className="notif-time">{timeAgo(n.created_at)}</span>
                </div>
                {n.body && <div className="notif-body">{n.body}</div>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
