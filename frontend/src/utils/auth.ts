import type { User } from '../types'
import { api, getApiMessage } from './api'
import { clearCachedChatId } from './cache'

const tokenKey = 'securerag_token'
const userKey = 'securerag_user'

type AuthResponse = {
  token?: string
  accessToken?: string
  user?: User
  username?: string
}

export type Credentials = {
  username: string
  password: string
}

export type Session = {
  token: string
  user: User
}

export function getStoredToken() {
  return localStorage.getItem(tokenKey)
}

export function getStoredUser() {
  const rawUser = localStorage.getItem(userKey)

  if (!rawUser) {
    return null
  }

  try {
    return JSON.parse(rawUser) as User
  } catch {
    return null
  }
}

export function saveSession(session: Session) {
  localStorage.setItem(tokenKey, session.token)
  localStorage.setItem(userKey, JSON.stringify(session.user))
}

export function clearSession() {
  localStorage.removeItem(tokenKey)
  localStorage.removeItem(userKey)
  clearCachedChatId()
}

async function authenticate(path: '/login' | '/register', credentials: Credentials) {
  const response = await api.post<AuthResponse>(path, credentials)
  const token = response.data.token ?? response.data.accessToken
  const username = response.data.user?.username ?? response.data.username ?? credentials.username

  if (!token) {
    throw new Error('Authentication response did not include a token.')
  }

  return {
    token,
    user: response.data.user ?? { username },
  }
}

export async function login(credentials: Credentials) {
  try {
    const session = await authenticate('/login', credentials)
    saveSession(session)
    return session
  } catch (error) {
    throw new Error(getApiMessage(error, 'Unable to sign in.'), { cause: error })
  }
}

export async function signup(credentials: Credentials) {
  try {
    const session = await authenticate('/register', credentials)
    saveSession(session)
    return session
  } catch (error) {
    throw new Error(getApiMessage(error, 'Unable to sign up.'), { cause: error })
  }
}
