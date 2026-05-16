import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from './AuthProvider'

function ProfileIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5 fill-none stroke-current">
      <circle cx="12" cy="8" r="3.25" strokeWidth="1.8" />
      <path d="M5.5 19c1.5-3.4 4-5.25 6.5-5.25S16.5 15.6 18.5 19" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export function AppShell({ children }: { children?: ReactNode }) {
  const { user, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const navigate = useNavigate()

  const initials = useMemo(() => {
    const username = user?.username ?? 'S'
    return username.slice(0, 2).toUpperCase()
  }, [user])

  return (
    <div className="min-h-screen bg-[linear-gradient(180deg,#fafafa_0%,#f5f5f5_100%)] text-[#222222]">
      <header className="sticky top-0 z-40 border-b border-black/5 bg-[#222222]/95 text-white shadow-[0_10px_30px_rgba(17,17,17,0.22)] backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <NavLink to="/home" className="flex items-center gap-3 text-lg font-semibold tracking-tight">
            <span className="grid h-9 w-9 place-items-center rounded-2xl bg-[#FA8112] text-lg shadow-lg shadow-orange-500/20">
              🔐
            </span>
            <span>SecureRAG</span>
          </NavLink>

          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuOpen((value) => !value)}
              className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white transition hover:border-[#FA8112]/50 hover:bg-white/10"
            >
              <span className="grid h-9 w-9 place-items-center rounded-full bg-[#FA8112] font-semibold text-white">
                {initials}
              </span>
              <span className="hidden text-left sm:block">
                <span className="block text-xs text-white/60">Profile</span>
                <span className="block max-w-[10rem] truncate font-medium">{user?.username ?? 'User'}</span>
              </span>
              <ProfileIcon />
            </button>

            {menuOpen ? (
              <div className="absolute right-0 mt-3 w-56 overflow-hidden rounded-2xl border border-white/10 bg-[#222222] p-2 shadow-2xl shadow-black/25">
                <div className="rounded-xl bg-white/5 px-4 py-3 text-sm text-white/90">
                  <p className="text-xs uppercase tracking-[0.2em] text-white/40">Signed in as</p>
                  <p className="mt-1 font-medium">{user?.username ?? 'User'}</p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    logout()
                    navigate('/login')
                  }}
                  className="mt-2 w-full rounded-xl px-4 py-3 text-left text-sm text-white transition hover:bg-white/10 hover:text-[#FA8112]"
                >
                  Logout
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {children ?? <Outlet />}
      </main>
    </div>
  )
}
