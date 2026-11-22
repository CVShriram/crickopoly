import { useEffect } from 'react'
import { useApp } from '../store'

export function Toasts() {
  const { app, dispatch } = useApp()
  useEffect(() => {
    if (!app.toasts.length) return
    const timer = window.setTimeout(() => {
      dispatch({ type: 'DISMISS', id: app.toasts[0].id })
    }, 3800)
    return () => window.clearTimeout(timer)
  }, [app.toasts, dispatch])

  return (
    <div className="toast-stack">
      {app.toasts.map(toast => (
        <button type="button" key={toast.id} className={`toast toast-${toast.tone}`}
          onClick={() => dispatch({ type: 'DISMISS', id: toast.id })}>
          <span className="toast-icon">{toast.icon}</span>
          <span><strong>{toast.title}</strong><small>{toast.text}</small></span>
        </button>
      ))}
    </div>
  )
}
