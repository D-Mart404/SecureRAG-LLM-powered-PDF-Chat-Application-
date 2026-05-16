import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

type AuthCardProps = {
  title: string
  subtitle: string
  children: ReactNode
  footerText: string
  footerLink: {
    label: string
    to: string
  }
}

export function AuthCard({ title, subtitle, children, footerText, footerLink }: AuthCardProps) {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-7xl items-center justify-center px-4 py-8">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-[2rem] border border-[#222222]/10 bg-white shadow-[0_24px_80px_rgba(17,17,17,0.10)] lg:grid-cols-[1.1fr_0.9fr]">
        <div className="hidden flex-col justify-between bg-[#222222] p-10 text-white lg:flex">
          <div>
            <span className="inline-flex rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.25em] text-white/70">
              SecureRAG
            </span>
            <h1 className="mt-6 max-w-md text-4xl font-semibold tracking-tight">
              Secure retrieval workflows with a calm, minimal interface.
            </h1>
            <p className="mt-4 max-w-md text-sm leading-6 text-white/70">
              Sign in to review conversations, inspect secure answers, and keep tokenized access under control.
            </p>
          </div>

          <div className="grid gap-4 text-sm text-white/70">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              Accent-driven controls and soft surfaces keep the hierarchy clear.
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              Protected routes, JWT storage, and API-aware state management are ready out of the box.
            </div>
          </div>
        </div>

        <div className="p-6 sm:p-8 lg:p-10">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.24em] text-[#FA8112]">{subtitle}</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-[#222222]">{title}</h2>
          </div>

          <div className="mt-8">{children}</div>

          <p className="mt-8 text-sm text-[#666666]">
            {footerText}{' '}
            <Link className="font-semibold text-[#FA8112] transition hover:text-[#d86f0d]" to={footerLink.to}>
              {footerLink.label}
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
