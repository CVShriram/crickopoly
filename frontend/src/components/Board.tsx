import React from 'react'
import type { GameState, Player, Space } from '../types'

export function gridPos(index: number): { row: number; col: number } {
  if (index <= 7) return { row: 9, col: 9 - index }
  if (index === 8) return { row: 9, col: 1 }
  if (index <= 15) return { row: 17 - index, col: 1 }
  if (index === 16) return { row: 1, col: 1 }
  if (index <= 23) return { row: 1, col: index - 15 }
  if (index === 24) return { row: 1, col: 9 }
  return { row: index - 23, col: 9 }
}

export function tokenStyle(index: number, offset = 0): React.CSSProperties {
  const { row, col } = gridPos(index)
  return {
    left: `${((col - 0.5) / 9) * 100}%`,
    top: `${((row - 0.5) / 9) * 100}%`,
    transform: `translate(-50%, -50%) translate(${offset}px, ${offset}px)`,
  }
}

const TYPE_ICON: Record<string, string> = {
  start: '🏁', property: '🎯', event: '🎴', run_1: '1️⃣', run_2: '2️⃣',
  run_4: '4️⃣', run_6: '🚀', free_hit: '🛡️', rest: '☕', auction: '🔨',
  injury: '🩹', no_ball: '🚫', recruit: '🛒', challenge: '🎯', out: '❌',
  stadium: '🏟️',
}

const KIND_ICON: Record<string, string> = {
  bowler: '🎯', keeper: '🧤', fielder: '🥎', stadium: '🏟️', batsman: '🏏',
}

function shortName(name: string) {
  return name
    .replace('Club ', 'Club ')
    .replace('County ', 'County ')
    .replace('International ', 'Intl ')
    .replace('World Class ', 'WC ')
    .replace('Wicketkeeper', 'Keeper')
}

interface Props {
  board: Space[]
  state: GameState | null
  currentPlayerId: string | null
  onSelect: (space: Space) => void
  children?: React.ReactNode
}

export function Board({ board, state, currentPlayerId, onSelect, children }: Props) {
  const owners = new Map<number, Player>()
  for (const player of state?.players || []) {
    for (const asset of player.assets) {
      if (asset.space_id !== null) owners.set(asset.space_id, player)
    }
  }

  return (
    <div className="board-shell">
      <div className="board-grid">
        {board.map(space => {
          const { row, col } = gridPos(space.id)
          const owner = owners.get(space.id)
          const asset = owner?.assets.find(a => a.space_id === space.id)
          const isCorner = [0, 8, 16, 24].includes(space.id)
          return (
            <button
              key={space.id}
              className={`space space-${space.type} ${isCorner ? 'space-corner' : ''} ${currentPlayerId && owner?.id === currentPlayerId ? 'owned-by-current' : ''}`}
              style={{ gridRow: row, gridColumn: col, ['--owner' as any]: owner?.color || 'transparent' }}
              onClick={() => onSelect(space)}
              title={`${space.name} — ${space.description}`}
            >
              <span className="space-icon">{space.kind ? KIND_ICON[space.kind] || '🏏' : TYPE_ICON[space.type] || '🏏'}</span>
              <span className="space-name">{shortName(space.name)}</span>
              {space.price > 0 && <span className="space-price">{space.price}</span>}
              {asset && asset.space_id !== null && (
                <span className="space-fee">{asset.effective_fee ?? 0} · L{asset.level + 1}</span>
              )}
              {owner && <span className="owner-dot" style={{ background: owner.color }} />}
            </button>
          )
        })}
        <div className="board-center">{children}</div>
        <div className="token-layer">
          {(state?.players || []).map((player, idx) => (
            <div
              key={player.id}
              className={`token ${player.id === currentPlayerId ? 'token-active' : ''} ${player.eliminated ? 'token-out' : ''}`}
              style={{ ...tokenStyle(player.position, (idx % 2 === 0 ? 1 : -1) * (6 + Math.floor(idx / 2) * 10)), background: player.color }}
              title={player.name}
            >
              {player.avatar}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
