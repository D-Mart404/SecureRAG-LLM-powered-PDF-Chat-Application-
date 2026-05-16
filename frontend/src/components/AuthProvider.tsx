import { createContext, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { User } from '../types'
import { clearSession, getStoredToken, getStoredUser, login, signup } from '../utils/auth'
import type { Credentials, Session } from '../utils/auth'

type AuthContextValue = {
  token: string | null
  user: User | null
  loginUser: (credentials: Credentials) => Promise<Session>
  signupUser: (credentials: Credentials) => Promise<Session>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getStoredToken())
  const [user, setUser] = useState<User | null>(() => getStoredUser())

  const loginUser = async (credentials: Credentials) => {
    const session = await login(credentials)
    setToken(session.token)
    setUser(session.user)
    return session
  }

  const signupUser = async (credentials: Credentials) => {
    const session = await signup(credentials)
    setToken(session.token)
    setUser(session.user)
    return session
  }

  const logout = () => {
    clearSession()
    setToken(null)
    setUser(null)
  }

  const value = useMemo<AuthContextValue>(
    () => ({ token, user, loginUser, signupUser, logout }),
    [token, user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)

  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }

  return context
}
