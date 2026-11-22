export const DRAFT_PRICE: Record<string, number> = {
  bronze: 30,
  silver: 50,
  gold: 80,
}

export const PHASES = ['powerplay', 'middle', 'death'] as const
export const PHASE_LABELS: Record<string, string> = {
  powerplay: 'Powerplay · 1–6',
  middle: 'Middle Overs · 7–15',
  death: 'Death Overs · 16–20',
}

export const BATTING_OPTIONS = [
  { value: 'aggressive', label: 'Aggressive', icon: '⚡' },
  { value: 'balanced', label: 'Balanced', icon: '⚖️' },
  { value: 'defensive', label: 'Defensive', icon: '🛡️' },
]
export const BOWLING_OPTIONS = [
  { value: 'pace', label: 'Pace', icon: '💨' },
  { value: 'spin', label: 'Spin', icon: '🌀' },
  { value: 'yorkers', label: 'Yorkers', icon: '🎯' },
  { value: 'defensive', label: 'Defensive', icon: '🧱' },
  { value: 'variation', label: 'Variation', icon: '🎭' },
]
export const FIELD_OPTIONS = [
  { value: 'attacking', label: 'Attacking', icon: '🔥' },
  { value: 'balanced', label: 'Balanced', icon: '⚖️' },
  { value: 'defensive', label: 'Defensive', icon: '🧤' },
]
