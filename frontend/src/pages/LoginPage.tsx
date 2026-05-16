import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'react-hot-toast'
import { AuthCard } from '../components/AuthCard'
import { useAuth } from '../components/AuthProvider'

type LoginPageProps = {
  mode: 'login' | 'signup'
}

export function LoginPage({ mode }: LoginPageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { loginUser, signupUser } = useAuth()
  const navigate = useNavigate()

  const isSignup = mode === 'signup'
  const heading = isSignup ? 'Create your SecureRAG account' : 'Welcome back to SecureRAG'
  const buttonLabel = isSignup ? 'Create account' : 'Sign in'
  const footerText = isSignup ? 'Already have an account?' : 'Need an account?'
  const footerLink = isSignup
    ? { label: 'Go to login', to: '/login' }
    : { label: 'Create one', to: '/signup' }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoading(true)

    try {
      if (isSignup) {
        await signupUser({ username, password })
      } else {
        await loginUser({ username, password })
      }

      navigate('/home', { replace: true })
    } catch (submissionError) {
      const message = submissionError instanceof Error ? submissionError.message : 'Unable to complete authentication.'
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthCard title={heading} subtitle={isSignup ? 'Sign up' : 'Login'} footerText={footerText} footerLink={footerLink}>
      <form className="space-y-5" onSubmit={handleSubmit}>
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-[#444444]">Username</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className="w-full rounded-2xl border border-[#D9D9D9] bg-[#fafafa] px-4 py-3 text-[#222222] outline-none transition placeholder:text-[#9A9A9A] focus:border-[#FA8112] focus:ring-4 focus:ring-[#FA8112]/15"
            placeholder="Enter your username"
            autoComplete="username"
            required
          />
        </label>

        <label className="block">
          <span className="mb-2 block text-sm font-medium text-[#444444]">Password</span>
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            className="w-full rounded-2xl border border-[#D9D9D9] bg-[#fafafa] px-4 py-3 text-[#222222] outline-none transition placeholder:text-[#9A9A9A] focus:border-[#FA8112] focus:ring-4 focus:ring-[#FA8112]/15"
            placeholder="Enter your password"
            autoComplete={isSignup ? 'new-password' : 'current-password'}
            required
          />
        </label>

        <button
          type="submit"
          disabled={loading}
          className="flex w-full items-center justify-center rounded-2xl bg-[#FA8112] px-4 py-3 font-semibold text-white shadow-lg shadow-orange-500/20 transition hover:bg-[#e6750c] hover:shadow-orange-500/25 disabled:cursor-not-allowed disabled:opacity-70"
        >
          {loading ? 'Working...' : buttonLabel}
        </button>
      </form>
    </AuthCard>
  )
}
