type IconProps = {
  className?: string
}

export function PlusIcon({ className = 'h-6 w-6' }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className} fill="none" stroke="currentColor">
      <path d="M12 5v14M5 12h14" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  )
}

export function SearchIcon({ className = 'h-5 w-5' }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className} fill="none" stroke="currentColor">
      <circle cx="11" cy="11" r="6.5" strokeWidth="1.8" />
      <path d="M16 16l4 4" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export function SendIcon({ className = 'h-5 w-5' }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className} fill="none" stroke="currentColor">
      <path d="M5 11.5 19 5l-6.5 14-1.3-6.1L5 11.5Z" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  )
}
