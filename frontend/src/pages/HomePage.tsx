import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ChatCard } from '../components/ChatCard'
import { PlusIcon, SearchIcon } from '../components/Icons'
import { getApiMessage, fetchHistory } from '../utils/api'
import { setCachedChatId } from '../utils/cache'
import type { ChatSession } from '../types'

type LocationState = {
  refresh?: boolean
} | null

type ChatLaunchState = {
  chatSession?: ChatSession
} | null

function isHistoryArray(value: unknown): value is ChatSession[] {
  return Array.isArray(value)
}

function extractHistoryItems(payload: unknown): ChatSession[] {
  if (isHistoryArray(payload)) {
    return payload
  }

  if (typeof payload === 'object' && payload !== null) {
    const record = payload as { history?: unknown; data?: unknown }

    if (isHistoryArray(record.history)) {
      return record.history
    }

    if (isHistoryArray(record.data)) {
      return record.data
    }
  }

  return []
}

export function HomePage() {
  const location = useLocation()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [historyCards, setHistoryCards] = useState<ChatSession[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const fetchChatsFromAPI = async () => {
    try {
      const payload = await fetchHistory()
      const items = extractHistoryItems(payload)
      // Enforce chat_no sorting on the frontend
      items.sort((a, b) => (b.chat_no || 0) - (a.chat_no || 0))
      setHistoryCards(items)
      setError('')
      setNotice('')
    } catch (loadError) {
      setError(getApiMessage(loadError, 'Unable to load chat history.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setLoading(true)
    void fetchChatsFromAPI()
  }, [])

  useEffect(() => {
    const state = location.state as LocationState

    if (state?.refresh) {
      void fetchChatsFromAPI()
      navigate('/home', { replace: true, state: null })
    }
  }, [location.state])

  const filteredCards = useMemo(() => {
    const search = query.trim().toLowerCase()

    if (!search) {
      return historyCards
    }

    return historyCards.filter((card) => {
      const title = card.first_question ?? card.messages[0]?.question ?? 'Untitled chat'
      const lastMessage = card.messages[card.messages.length - 1]
      const preview = lastMessage?.answer ?? lastMessage?.question ?? 'No answer preview available.'
      return [title, preview, card.chat_id].some((value) => value.toLowerCase().includes(search))
    })
  }, [historyCards, query])

  const startNewChat = () => {
    const chatId = crypto.randomUUID()
    setCachedChatId(chatId)
    navigate('/chat', {
      state: {
        chatSession: {
          chat_id: chatId,
          messages: [],
          first_question: 'New chat',
          message_count: 0,
          last_updated: new Date().toISOString(),
        },
      } as ChatLaunchState,
    })
  }

  return (
    <div className="space-y-6 pb-24">
      <section className="rounded-[2rem] border border-[#222222]/10 bg-white p-6 shadow-[0_20px_70px_rgba(34,34,34,0.07)] sm:p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <p className="text-sm font-medium uppercase tracking-[0.24em] text-[#FA8112]">Knowledge overview</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[#222222] sm:text-4xl">
              Secure chat history with strong visual hierarchy.
            </h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-[#666666]">
              Search recent conversations, inspect answers, and launch new chats from a calm, minimal workspace.
            </p>
          </div>

          <Link
            to="/chat"
            onClick={(event) => {
              event.preventDefault()
              startNewChat()
            }}
            className="inline-flex items-center gap-3 self-start rounded-2xl bg-[#FA8112] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#e07000] shadow-lg shadow-orange-500/20"
          >
            Start secure chat
          </Link>
        </div>

        <div className="mt-6 flex items-center gap-3 rounded-2xl border border-[#D9D9D9] bg-[#fafafa] px-4 py-3 focus-within:border-[#FA8112] focus-within:ring-4 focus-within:ring-[#FA8112]/10">
          <SearchIcon className="h-5 w-5 text-[#777777]" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search chats, topics, or policies"
            className="w-full border-0 bg-transparent text-sm text-[#222222] outline-none placeholder:text-[#9A9A9A]"
          />
        </div>

        {notice ? <p className="mt-3 text-sm text-[#666666]">{notice}</p> : null}
      </section>

      {loading ? (
        <section className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              key={index}
              className="h-[174px] animate-pulse rounded-3xl border border-white/5 bg-[#222222] p-5 shadow-md"
            >
              <div className="h-6 w-20 rounded-full bg-white/10" />
              <div className="mt-6 h-5 w-3/4 rounded-full bg-white/10" />
              <div className="mt-3 h-4 w-full rounded-full bg-white/10" />
              <div className="mt-2 h-4 w-5/6 rounded-full bg-white/10" />
            </div>
          ))}
        </section>
      ) : error ? (
        <section className="grid place-items-center rounded-[2rem] border border-dashed border-[#D0D0D0] bg-white/70 px-6 py-20 text-center text-[#666666] shadow-sm">
          <div className="max-w-md">
            <p className="text-lg font-semibold text-[#222222]">Unable to load history</p>
            <p className="mt-2 text-sm leading-6">{error}</p>
          </div>
        </section>
      ) : filteredCards.length ? (
        <section className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {filteredCards.map((item, index) => {
            const baseTitle = item.first_question ?? item.messages[0]?.question ?? 'Untitled chat'
            const title = item.chat_no ? `Chat ${item.chat_no}: ${baseTitle}` : baseTitle
            const lastMessage = item.messages[item.messages.length - 1]
            const preview = lastMessage?.answer ?? lastMessage?.question ?? 'No answer preview available.'
            const rawTimestamp = item.last_updated ?? item.updated_at ?? lastMessage?.timestamp ?? 'Recently'
            const updatedAt = typeof rawTimestamp === 'number' ? new Date(rawTimestamp).toLocaleString() : rawTimestamp
            const messageCount = item.message_count ?? item.messages.length

            return (
              <ChatCard
                key={item.chat_id}
                id={index + 1}
                title={title}
                preview={preview}
                updatedAt={updatedAt}
                messageCount={messageCount}
                category="Session"
                onClick={() => {
                  setCachedChatId(item.chat_id)
                  navigate('/chat', { state: { chatSession: item } as ChatLaunchState })
                }}
              />
            )
          })}
        </section>
      ) : (
        <section className="grid place-items-center rounded-[2rem] border border-dashed border-[#D0D0D0] bg-white/70 px-6 py-20 text-center text-[#666666] shadow-sm">
          <div className="max-w-md">
            <p className="text-lg font-semibold text-[#222222]">No chats yet</p>
            <p className="mt-2 text-sm leading-6">
              Try a different search term or start a new secure conversation with the floating action button.
            </p>
          </div>
        </section>
      )}

      <Link
        to="/chat"
        className="fixed bottom-6 right-6 z-30 grid h-16 w-16 place-items-center rounded-full bg-[#FA8112] text-white shadow-[0_18px_40px_rgba(250,129,18,0.35)] transition hover:scale-110 hover:bg-[#e6750c]"
        aria-label="Start a new chat"
      >
        <PlusIcon className="h-7 w-7" />
      </Link>
    </div>
  )
}