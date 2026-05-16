import axios from 'axios'

import type { ChatSession } from '../types'

const tokenKey = 'securerag_token'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? ''
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(tokenKey)

  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }

  return config
})

export function getApiMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const responseData = error.response?.data as { message?: string; detail?: string } | undefined

    return (
      responseData?.message ??
      responseData?.detail ??
      error.message ??
      fallback
    )
  }

  return fallback
}

export type UploadResponse = {
  chunks_added?: number
  filename?: string
  user?: string
  parser?: string
}

export type QueryHistoryMessage = {
  role: 'user' | 'assistant'
  content: string
}

export type QueryLogs = {
  retrieved_chunks?: Array<{
    text: string
    page?: number | string
    score?: number | null
  }>
  embedding_model?: string
  vision_processing?: 'enabled' | 'disabled'
  processing_time_ms?: number
  thinking_steps?: string[]
}

export type QueryResponse = {
  answer?: string
  chat_id?: string
  citations?: Array<{ doc?: string; page?: number | string }>
  logs?: QueryLogs
  sources?: Array<{
    page?: number | string
    chunk?: number | string
    source?: string
    snippet?: string
    score?: number | null
  }>
  visual_sources?: Array<Record<string, unknown>>
  source_pages?: Array<{ doc?: string; page?: number | string }>
  user?: string
}

export type ChatSummaryResponse = {
  summary?: string
  chat_id?: string
  user?: string
}

export type ChatHistorySession = ChatSession & {
  title?: string
  preview?: string
  updatedAt?: string
  category?: string
}

export async function uploadDocument(file: File, onProgress?: (percent: number) => void) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await api.post<UploadResponse>('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (event) => {
      if (!onProgress) {
        return
      }

      if (event.total) {
        const percent = Math.round((event.loaded / event.total) * 100)
        onProgress(percent)
      }
    },
  })

  return response.data
}

export async function askQuestion(
  question: string,
  chatId?: string,
  chatHistory: QueryHistoryMessage[] = [],
) {
  const response = await api.post<QueryResponse>('/query', {
    question,
    chat_id: chatId,
    chat_history: chatHistory,
  })

  return response.data
}

export async function summarizeChat(chatId: string) {
  const response = await api.post<ChatSummaryResponse>('/summarize', { chat_id: chatId })
  return response.data
}

export async function fetchHistory() {
  const response = await api.get<ChatHistorySession[]>('/history')
  return response.data
}
