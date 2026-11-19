import type { Batsman, Selection } from '../types'

interface Props {
  person: Batsman | Selection | null | undefined
  size?: 'tiny' | 'small' | 'medium' | 'large'
  showNumber?: boolean
}

const HAIR_CLASS: Record<string, string> = {
  short: 'hair-short', spiky: 'hair-spiky', long: 'hair-long',
  curly: 'hair-curly', bald: 'hair-bald',
}

const FACE_MOUTH: Record<string, string> = {
  smile: '◡', grin: '😁', focused: '—', determined: '︿',
}

export function BatsmanAvatar({ person, size = 'medium', showNumber = true }: Props) {
  if (!person) return <div className={`batsman-avatar avatar-${size} avatar-empty`}>🏏</div>
  const skin = person.skin || '#f1c27d'
  const jersey = person.jersey_color || '#22c55e'
  const number = person.jersey_number ?? 18
  const hair = person.hair || 'short'
  const face = person.face || 'smile'
  return (
    <div className={`batsman-avatar avatar-${size}`} style={{ ['--jersey' as any]: jersey }}>
      <div className="avatar-body">
        {showNumber && <span className="avatar-number">{number}</span>}
        <span className="avatar-stripe" />
      </div>
      <div className="avatar-head" style={{ background: skin }}>
        <span className={`avatar-hair ${HAIR_CLASS[hair] || 'hair-short'}`}
          style={{ background: person.hair_color || '#2d1b0e' }} />
        <span className="avatar-eyes"><i /><i /></span>
        <span className="avatar-mouth">{FACE_MOUTH[face] || '◡'}</span>
      </div>
      <span className="avatar-bat">🏏</span>
    </div>
  )
}
