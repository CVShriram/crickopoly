import React from 'react'
import { useApp } from '../store'
import type { GameData, Tile, TycoonState } from '../types'
import { Button } from './UI'

function tileGridPosition(pos: number): { gridRow: number; gridColumn: number } {
  if (pos <= 13) return { gridRow: 14, gridColumn: pos + 1 }
  if (pos <= 25) return { gridRow: 14 - (pos - 13), gridColumn: 14 }
  if (pos <= 38) return { gridRow: 1, gridColumn: 14 - (pos - 26) }
  return { gridRow: 2 + (pos - 39), gridColumn: 1 }
}

export function BoardGrid({ state, gamedata }: {
  state: TycoonState | null
  gamedata?: GameData | null
}) {
  const { send } = useApp()
  const tiles: Tile[] = state?.board || gamedata?.board || []
  const you = state?.you
  const me = you && state ? state.franchises?.[you] : undefined
  const current = state?.current_player_id && state
    ? state.franchises?.[state.current_player_id]
    : undefined
  const blocked = Boolean(state?.pending || state?.auction || state?.finished)
  const canRoll = Boolean(state?.started && state.current_player_id === you && !blocked)

  return (
    <div className="board-wrap">
      <div className="board-grid" aria-label="Stadium Tycoon board">
        {tiles.map(tile => {
          const ownerId = state?.ownership?.[String(tile.position)]
          const owner = ownerId && state ? state.franchises?.[ownerId] : undefined
          const isMine = Boolean(ownerId && ownerId === you)
          const here = me?.pos === tile.position
          const active = current?.pos === tile.position
          return (
            <div
              key={tile.position}
              style={{ ...tileGridPosition(tile.position), '--tile-color': owner?.color || 'transparent' } as React.CSSProperties}
              className={`board-tile tile-${tile.kind} ${here ? 'here' : ''} ${active ? 'active' : ''} ${isMine ? 'mine' : ''}`}
              title={`${tile.position} · ${tile.name}${owner ? ` · ${owner.name}` : ''}`}
            >
              <span className="tile-pos">{tile.position}</span>
              <span className="tile-icon">{tile.icon}</span>
              <span className="tile-name">{tile.short || tile.name}</span>
              {owner && <span className="tile-owner" style={{ background: owner.color }} />}
            </div>
          )
        })}
        <div className="board-center">
          <span className="center-crest">🏏</span>
          <small>STADIUM TYCOON</small>
          <strong>ONE BOARD. ONE ACTION.</strong>
          <div className="dice-display single" aria-label="Dice">
            <span>{state?.dice?.[0] || '–'}</span>
          </div>
          <p>
            {current
              ? <><span style={{ color: current.color }}>{current.avatar} {current.name}</span> {current.id === you ? '— your turn' : 'is on the clock'}</>
              : 'Waiting for a room…'}
          </p>
          {canRoll && (
            <Button variant="gold" className="center-roll big" onClick={() => send('roll', {})}>
              🎲 ROLL
            </Button>
          )}
          {blocked && state?.pending && (
            <p className="board-hint">Next action is in the bar below ↓</p>
          )}
        </div>
      </div>
    </div>
  )
}
