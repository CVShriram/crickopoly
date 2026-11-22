import React from 'react'
import { initials, tierClass } from '../utils'
import type { PlayerData, Franchise } from '../types'

export function Panel({ title, subtitle, icon, action, children, className = '' }: {
  title?: string; subtitle?: string; icon?: string; action?: React.ReactNode
  children: React.ReactNode; className?: string
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || action) && (
        <header className="panel-head">
          <div className="panel-title-wrap">
            {icon && <span className="panel-icon">{icon}</span>}
            <div>
              {title && <h2>{title}</h2>}
              {subtitle && <p>{subtitle}</p>}
            </div>
          </div>
          {action && <div className="panel-action">{action}</div>}
        </header>
      )}
      <div className="panel-body">{children}</div>
    </section>
  )
}

export function Stat({ label, value, sub, tone = 'default', icon }: {
  label: string; value: React.ReactNode; sub?: string
  tone?: 'default' | 'gold' | 'green' | 'danger' | 'blue'; icon?: string
}) {
  return (
    <div className={`stat stat-${tone}`}>
      {icon && <span className="stat-icon">{icon}</span>}
      <div>
        <span className="stat-label">{label}</span>
        <strong className="stat-value">{value}</strong>
        {sub && <small className="stat-sub">{sub}</small>}
      </div>
    </div>
  )
}

export function Badge({ children, tone = 'default', icon }: {
  children: React.ReactNode; tone?: string; icon?: string
}) {
  return <span className={`badge badge-${tone}`}>{icon && <span>{icon} </span>}{children}</span>
}

export function Meter({ value, max = 100, tone = 'green', label }: {
  value: number; max?: number; tone?: string; label?: string
}) {
  const p = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div className="meter-wrap" title={label}>
      <div className="meter"><div className={`meter-fill meter-${tone}`} style={{ width: `${p}%` }} /></div>
      {label && <span className="meter-label">{label}</span>}
    </div>
  )
}

export function Avatar({ franchise, size = 'md' }: { franchise?: Franchise; size?: 'sm' | 'md' | 'lg' }) {
  return (
    <span className={`avatar avatar-${size}`} style={{ '--avatar': franchise?.color || '#c8a24b' } as React.CSSProperties}>
      {franchise?.avatar || '🏏'}
    </span>
  )
}

export function PlayerPortrait({ player, size = 'md', injured = false }: {
  player?: PlayerData; size?: 'sm' | 'md' | 'lg'; injured?: boolean
}) {
  if (!player) return <span className={`portrait portrait-${size} portrait-empty`}>?</span>
  return (
    <span
      className={`portrait portrait-${size} ${tierClass(player.tier)} ${injured ? 'portrait-injured' : ''}`}
      style={{ '--hue': player.portrait_hue || 40 } as React.CSSProperties}
      title={player.name}
    >
      {initials(player.name)}
    </span>
  )
}

export function Button({ children, onClick, variant = 'primary', disabled, title, small, block }: {
  children: React.ReactNode; onClick?: () => void; variant?: 'primary' | 'ghost' | 'gold' | 'danger' | 'success' | 'subtle'
  disabled?: boolean; title?: string; small?: boolean; block?: boolean
}) {
  return (
    <button
      type="button" className={`btn btn-${variant} ${small ? 'btn-sm' : ''} ${block ? 'btn-block' : ''}`}
      onClick={onClick} disabled={disabled} title={title}
    >{children}</button>
  )
}

export function Segmented<T extends string>({ value, options, onChange }: {
  value: T; options: Array<{ value: T; label: string }>; onChange: (value: T) => void
}) {
  return (
    <div className="segmented">
      {options.map(option => (
        <button key={option.value} type="button"
          className={value === option.value ? 'active' : ''}
          onClick={() => onChange(option.value)}>{option.label}</button>
      ))}
    </div>
  )
}

export function Modal({ title, subtitle, onClose, children, width = '640px' }: {
  title: string; subtitle?: string; onClose: () => void; children: React.ReactNode; width?: string
}) {
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal" style={{ maxWidth: width }} onMouseDown={e => e.stopPropagation()}>
        <header>
          <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">×</button>
        </header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}

export function Empty({ icon = '◇', title, text }: { icon?: string; title: string; text?: string }) {
  return (
    <div className="empty"><span>{icon}</span><strong>{title}</strong>{text && <p>{text}</p>}</div>
  )
}

export function Tabs({ tabs, active, onChange }: {
  tabs: Array<{ id: string; label: string; icon?: string; count?: number }>
  active: string; onChange: (id: string) => void
}) {
  return (
    <div className="tabs">
      {tabs.map(tab => (
        <button key={tab.id} type="button" className={active === tab.id ? 'active' : ''}
          onClick={() => onChange(tab.id)}>
          {tab.icon && <span>{tab.icon} </span>}{tab.label}
          {tab.count !== undefined && <em>{tab.count}</em>}
        </button>
      ))}
    </div>
  )
}
