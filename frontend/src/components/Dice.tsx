const PIPS: Record<number, number[]> = {
  1: [4], 2: [0, 8], 3: [0, 4, 8], 4: [0, 2, 6, 8],
  5: [0, 2, 4, 6, 8], 6: [0, 2, 3, 5, 6, 8],
}

function Die({ value, rolling }: { value: number; rolling: boolean }) {
  const pips = PIPS[value] || PIPS[1]
  return (
    <div className={`die ${rolling ? 'die-rolling' : ''}`}>
      {Array.from({ length: 9 }, (_, i) => (
        <span key={i} className={pips.includes(i) ? 'pip' : ''} />
      ))}
    </div>
  )
}

export function Dice({ dice, rolling }: { dice: number[]; rolling: boolean }) {
  return (
    <div className="dice-row">
      <Die value={dice[0] || 1} rolling={rolling} />
      <Die value={dice[1] || 1} rolling={rolling} />
    </div>
  )
}
