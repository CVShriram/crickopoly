import { useEffect } from 'react'
import { useApp } from '../store'

export function Toasts() {
  const { app, dispatch } = useApp()
  useEffect(() => {
    if (!app.toasts.length) return
    const timers = app.toasts.map(t => window.setTimeout(() => dispatch({ type: 'DISMISS', id: t.id }), 3200))
    return () => timers.forEach(clearTimeout)
  }, [app.toasts, dispatch])

  return (
    <div className="toast-stack">
      {app.toasts.map(toast => (
        <div key={toast.id} className={`toast toast-${toast.tone}`}>
          <span className="toast-icon">{toast.icon}</span>
          <div>
            <strong>{toast.title}</strong>
            {toast.text && <p>{toast.text}</p>}
          </div>
        </div>
      ))}
    </div>
  )
}
