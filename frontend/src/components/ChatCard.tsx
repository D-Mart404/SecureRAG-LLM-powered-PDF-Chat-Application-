import type { ChatCard as ChatCardType } from '../types'

type ChatCardProps = ChatCardType & {
  onClick?: () => void
}

export function ChatCard({ title, preview, updatedAt, messageCount, category, onClick }: ChatCardProps) {
  return (
    <article
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={event => {
        if (!onClick) return
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onClick()
        }
      }}
      className={`group rounded-3xl border border-white/5 bg-[#222222] p-5 text-white shadow-md transition duration-200 hover:-translate-y-1 hover:border-[#FA8112]/70 hover:shadow-[0_20px_50px_rgba(34,34,34,0.25)] ${onClick ? 'cursor-pointer focus:outline-none focus:ring-4 focus:ring-[#FA8112]/20' : ''}`}
    >
      <div className="flex items-start justify-between gap-4">
        <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-medium uppercase tracking-[0.2em] text-white/60">
          {category}
        </span>
        <div className="text-right">
          <div className="text-xs text-white/45">{updatedAt}</div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.18em] text-white/40">{messageCount} messages</div>
        </div>
      </div>

      <h3 className="mt-4 text-lg font-semibold leading-7 tracking-tight text-white">{title}</h3>
      <p className="mt-3 line-clamp-3 text-sm leading-6 text-white/68">{preview}</p>
    </article>
  )
}
