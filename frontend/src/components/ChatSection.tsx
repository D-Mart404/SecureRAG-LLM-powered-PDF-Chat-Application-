import React, { useEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { ThinkingPanel } from './ThinkingPanel'
import {
  askQuestion,
  getApiMessage,
  summarizeChat,
  type QueryHistoryMessage,
  type QueryLogs,
  type QueryResponse,
} from '../utils/api'
import { getCachedChatId, setCachedChatId } from '../utils/cache'

export interface Message {
  id: string
  type: 'user' | 'assistant'
  content: string
  citations?: Array<{
    page: number
    chunkId?: string
  }>
  retrievedChunks?: Array<{
    content: string
    page: number
    chunkId: string
    score: number
  }>
  logs?: QueryLogs
}

interface ChatSectionProps {
  fileName: string
  chatId?: string
  initialMessages?: Message[]
}

function toPageNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) return value
  if (typeof value === 'string') {
    const parsed = Number.parseInt(value, 10)
    if (Number.isFinite(parsed) && parsed > 0) return parsed
  }
  return null
}

function toHistoryPayload(conversation: Message[]): QueryHistoryMessage[] {
  return conversation.map(message => ({
    role: message.type,
    content: message.content,
  }))
}

function renderCitationHighlights(text: string) {
  const parts = text.split(/(\[p\d+(?::[^\]]+)?\])/g)
  
  return parts.map((part, index) => {
    if (/^\[p\d+(?::[^\]]+)?\]$/.test(part)) {
      return (
        <span key={`${part}-${index}`} className="mx-0.5 rounded bg-accent/20 px-1.5 py-0.5 text-[11px] font-bold text-accent">
          {part}
        </span>
      )
    }
    return <React.Fragment key={`${part}-${index}`}>{part}</React.Fragment>
  })
}

export const ChatSection: React.FC<ChatSectionProps> = ({ fileName, chatId: initialChatId, initialMessages }) => {
  const [messages, setMessages] = useState<Message[]>(() => initialMessages ?? [])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [showThinking, setShowThinking] = useState(false)
  const [summary, setSummary] = useState('')
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState('')
  const [detailsOpenId, setDetailsOpenId] = useState<string | null>(null)
  
  // NEW: State to show a temporary "Copied!" checkmark
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const [activeChatId, setActiveChatId] = useState<string>(() => {
    if (initialChatId) return initialChatId
    const stored = getCachedChatId()
    return stored ?? ''
  })

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesWrapperRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const sendBtnRef = useRef<HTMLButtonElement | null>(null)
  const audioBtnRef = useRef<HTMLButtonElement | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  useEffect(() => {
    setMessages(initialMessages ?? [])
    setInput('')
    setIsLoading(false)
    setShowThinking(false)
    setSummary('')
    setSummaryError('')
    setDetailsOpenId(null)
  }, [initialMessages])

  useEffect(() => {
    if (initialChatId) {
      setActiveChatId(initialChatId)
      setCachedChatId(initialChatId)
    }
  }, [initialChatId])

  useEffect(() => {
    if (activeChatId) {
      setCachedChatId(activeChatId)
    }
  }, [activeChatId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, summary])

  useEffect(() => {
    const wrapper = messagesWrapperRef.current
    if (!wrapper) return
    const children = wrapper.querySelectorAll(':scope > div.message-item')
    const last = children[children.length - 1] as HTMLElement | undefined
    if (last) {
      gsap.fromTo(last, { y: 18, opacity: 0 }, { y: 0, opacity: 1, duration: 0.36, ease: 'power2.out' })
    }
  }, [messages])

  useEffect(() => {
    const sendEl = sendBtnRef.current
    const audioEl = audioBtnRef.current
    if (!sendEl || !audioEl) return
    if (input.trim()) {
      gsap.to(sendEl, { opacity: 1, scale: 1, pointerEvents: 'auto', duration: 0.18 })
      gsap.to(audioEl, { opacity: 0, scale: 0.95, pointerEvents: 'none', duration: 0.18 })
    } else {
      gsap.to(sendEl, { opacity: 0, scale: 0.95, pointerEvents: 'none', duration: 0.18 })
      gsap.to(audioEl, { opacity: 1, scale: 1, pointerEvents: 'auto', duration: 0.18 })
    }
  }, [input])

  const buildAssistantMessage = (data: QueryResponse): Message => {
    const citations: Array<{ page: number; chunkId?: string }> = []
    const referencePages = Array.isArray(data.source_pages)
      ? data.source_pages
      : Array.isArray(data.citations)
        ? data.citations
        : []
    for (const source of referencePages) {
      const page = toPageNumber(source.page)
      if (page) {
        citations.push({ page, chunkId: source.doc })
      }
    }
    const retrievedChunks = data.logs?.retrieved_chunks
      ?.map((chunk, index) => {
        const page = toPageNumber(chunk.page)
        if (!page || !chunk.text.trim()) {
          return null
        }
        return {
          content: chunk.text,
          page,
          chunkId: String(index + 1),
          score: typeof chunk.score === 'number' ? chunk.score : 0,
        }
      })
      .filter((chunk): chunk is { content: string; page: number; chunkId: string; score: number } => chunk !== null)
    return {
      id: `${Date.now()}-assistant`,
      type: 'assistant',
      content: data.answer?.trim() || 'I could not generate an answer for that question.',
      citations,
      retrievedChunks,
      logs: data.logs,
    }
  }

  const startRecording = async () => { /* Audio stub */ }
  const stopRecording = () => { /* Audio stub */ }
  const handleAudioSubmit = async (audioBlob: Blob) => { console.log('Audio submitted:', audioBlob) }

  const handleSendMessage = async () => {
    if (!input.trim() || isLoading) return
    const question = input.trim()
    const userMessage: Message = {
      id: `${Date.now()}-user`,
      type: 'user',
      content: question,
    }
    const nextConversation = [...messages, userMessage]
    setMessages(nextConversation)
    setInput('')
    setIsLoading(true)
    setShowThinking(true)
    try {
      const response = await askQuestion(question, activeChatId || undefined, toHistoryPayload(nextConversation))
      const nextChatId = response.chat_id ?? activeChatId
      if (nextChatId && nextChatId !== activeChatId) {
        setActiveChatId(nextChatId)
        setCachedChatId(nextChatId)
      }
      const assistantMessage = buildAssistantMessage(response)
      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      const errorMessage = getApiMessage(error, 'Failed to fetch answer from the backend.')
      setMessages(prev => [
        ...prev,
        {
          id: `${Date.now()}-assistant-error`,
          type: 'assistant',
          content: `Unable to answer right now: ${errorMessage}`,
        },
      ])
    } finally {
      setShowThinking(false)
      setIsLoading(false)
    }
  }

  const handleSummarizeChat = async () => {
    if (!activeChatId) {
      setSummaryError('Start or open a chat session before summarizing.')
      return
    }
    setSummaryLoading(true)
    setSummaryError('')
    try {
      const response = await summarizeChat(activeChatId)
      setSummary(response.summary?.trim() || 'No summary returned.')
    } catch (error) {
      setSummaryError(getApiMessage(error, 'Unable to summarize this chat right now.'))
    } finally {
      setSummaryLoading(false)
    }
  }

  // NEW FEATURE: Export Chat to Markdown
  const handleExportChat = () => {
    if (messages.length === 0) return;
    
    let content = `# SecureRAG Transcript\n**Document:** ${fileName}\n**Date:** ${new Date().toLocaleString()}\n\n---\n\n`;
    
    messages.forEach(m => {
      const role = m.type === 'user' ? '👤 YOU' : '🤖 AI ASSISTANT';
      content += `### ${role}\n${m.content}\n\n`;
      
      if (m.citations && m.citations.length > 0) {
        const cites = m.citations.map(c => `[Page ${c.page}]`).join(', ');
        content += `*Sources Cited: ${cites}*\n\n`;
      }
      content += `---\n\n`;
    });

    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${fileName.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_transcript.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  // NEW FEATURE: Copy Message to Clipboard
  const handleCopyMessage = (messageId: string, content: string) => {
    navigator.clipboard.writeText(content).then(() => {
      setCopiedId(messageId);
      setTimeout(() => setCopiedId(null), 2000);
    });
  }

  const formatCitations = (citations?: Message['citations']) => {
    if (!citations || citations.length === 0) return null
    return citations.map(c => (c.chunkId ? `[p${c.page}:${c.chunkId}]` : `[p${c.page}]`)).join(' ')
  }

  const hasInput = input.trim().length > 0
  const hasHistorySeed = Boolean(initialMessages && initialMessages.length > 0)

  return (
    <div ref={containerRef} className="rag-panel flex h-full min-h-0 w-full flex-col overflow-hidden bg-paper-soft">
      <div className="shrink-0 border-b border-border/80 bg-paper-soft px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="m-0 text-base font-semibold tracking-tight text-ink">{fileName}</h2>
            <p className="mt-1 text-xs text-ink-muted">
              {hasHistorySeed ? 'Viewing a saved conversation session' : 'Ready to start a new chat session'}
            </p>
          </div>
          
          <div className="flex items-center gap-2">
            {/* NEW: Export Button */}
            <button
              type="button"
              onClick={handleExportChat}
              disabled={messages.length === 0}
              className="rounded-xl border border-border bg-paper px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-ink transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
              title="Download chat as Markdown file"
            >
              Export
            </button>
            <button
              type="button"
              onClick={handleSummarizeChat}
              disabled={summaryLoading || !activeChatId}
              className="rounded-xl border border-border bg-paper px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-ink transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
            >
              {summaryLoading ? 'Summarizing...' : 'Summarize Chat'}
            </button>
          </div>

        </div>
        {(summary || summaryError) && (
          <div className="mt-4 rounded-2xl border border-border bg-paper px-4 py-4 text-sm text-ink-text">
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="m-0 text-xs font-semibold uppercase tracking-[0.18em] text-ink-muted">Chat summary</p>
              <button
                type="button"
                onClick={() => {
                  setSummary('')
                  setSummaryError('')
                }}
                className="text-xs text-ink-muted transition hover:text-ink"
              >
                Clear
              </button>
            </div>
            {summaryError ? <p className="m-0 text-sm text-red-600">{summaryError}</p> : <p className="m-0 leading-6">{summary}</p>}
          </div>
        )}
      </div>

      <div ref={messagesWrapperRef} className="flex-1 min-h-0 overflow-y-auto px-5 py-6">
        <div className="flex h-full min-h-0 flex-col gap-4">
          {messages.length === 0 && (
            <div className="flex flex-1 items-center justify-center px-4 py-8">
              <div className="rag-card w-full max-w-2xl rounded-[1.75rem] border border-border/80 bg-paper px-6 py-8 text-center shadow-sm sm:px-10 sm:py-10">
                <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full border border-accent/20 bg-accent/10 text-accent">
                  <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M7 8h10M7 12h6M20 12c0 3.866-3.582 7-8 7a9.6 9.6 0 0 1-2.4-.3L4 20l1.7-4.2A7.1 7.1 0 0 1 4 12c0-3.866 3.582-7 8-7s8 3.134 8 7Z" />
                  </svg>
                </div>
                <h3 className="m-0 text-2xl font-semibold tracking-tight text-ink">Start asking questions</h3>
                <p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-ink-muted sm:text-base">
                  Answers, citations, retrieval logs, and thinking steps will appear here once you ask about the document set.
                </p>
                <div className="mt-6 grid gap-3 sm:grid-cols-3">
                  {[
                    'Summarize the main argument',
                    'Find the key citations',
                    'Explain this section simply',
                  ].map(prompt => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => setInput(prompt)}
                      className="rounded-2xl border border-border bg-paper-soft px-4 py-3 text-left text-sm font-medium text-ink-muted transition-colors duration-200 hover:border-accent hover:text-ink"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
          {messages.map(message => {
            const detailsVisible = detailsOpenId === message.id
            const isCopied = copiedId === message.id

            return (
              <div
                key={message.id}
                className={`message-item rag-message-item flex items-end gap-3 ${message.type === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
              >
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${message.type === 'user' ? 'bg-accent' : 'bg-ink-soft'}`}>
                  <span className="text-sm font-semibold text-paper">{message.type === 'user' ? 'U' : 'A'}</span>
                </div>
                <div className="min-w-0 flex-1 max-w-full">
                  <div
                    className={`relative break-words rounded-2xl px-4 py-3 ${message.type === 'user' ? 'bg-accent text-paper' : 'border border-border bg-[#1f1f1f] text-white shadow-sm'}`}
                  >
                    {/* NEW: Copy to Clipboard Button for AI messages */}
                    {message.type === 'assistant' && (
                      <button
                        onClick={() => handleCopyMessage(message.id, message.content)}
                        className="absolute top-3 right-3 text-white/40 hover:text-white transition-colors"
                        title="Copy message"
                      >
                        {isCopied ? (
                          <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path></svg>
                        ) : (
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
                        )}
                      </button>
                    )}

                    <p className={`m-0 text-sm leading-6 whitespace-pre-wrap ${message.type === 'assistant' ? 'pr-6' : ''}`}>
                      {message.type === 'assistant' ? renderCitationHighlights(message.content) : message.content}
                    </p>

                    {message.citations && message.citations.length > 0 && (
                      <div className={`mt-3 border-t pt-3 ${message.type === 'user' ? 'border-white/20' : 'border-white/10'}`}>
                        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide opacity-70">Citations:</p>
                        <p className={`m-0 text-xs font-mono ${message.type === 'user' ? 'text-paper' : 'text-[#FA8112]'}`}>
                          {formatCitations(message.citations)}
                        </p>
                      </div>
                    )}
                    {message.type === 'assistant' && message.logs ? (
                      <div className="mt-4">
                        <button
                          type="button"
                          onClick={() => setDetailsOpenId(detailsVisible ? null : message.id)}
                          className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.16em] text-white/80 transition hover:border-[#FA8112]/40 hover:text-[#FA8112]"
                        >
                          {detailsVisible ? 'Hide Details' : 'Show Details'}
                        </button>
                        {detailsVisible ? (
                          <div className="mt-3 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-white/90">
                            <div className="grid gap-3 sm:grid-cols-2">
                              <div>
                                <p className="m-0 text-[11px] uppercase tracking-[0.18em] text-white/45">Embedding model</p>
                                <p className="mt-1 m-0 text-sm">{message.logs.embedding_model ?? 'Unknown'}</p>
                              </div>
                              <div>
                                <p className="m-0 text-[11px] uppercase tracking-[0.18em] text-white/45">Vision</p>
                                <p className="mt-1 m-0 text-sm">{message.logs.vision_processing ?? 'disabled'}</p>
                              </div>
                              <div>
                                <p className="m-0 text-[11px] uppercase tracking-[0.18em] text-white/45">Processing time</p>
                                <p className="mt-1 m-0 text-sm">{message.logs.processing_time_ms ?? 0} ms</p>
                              </div>
                              <div>
                                <p className="m-0 text-[11px] uppercase tracking-[0.18em] text-white/45">Thinking steps</p>
                                <p className="mt-1 m-0 text-sm">{message.logs.thinking_steps?.length ?? 0} steps</p>
                              </div>
                            </div>
                            {message.logs.thinking_steps?.length ? (
                              <div className="mt-4">
                                <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-white/45">Thinking log</p>
                                <ul className="m-0 list-none space-y-2 p-0">
                                  {message.logs.thinking_steps.map(step => (
                                    <li key={step} className="rounded-xl border border-white/10 bg-black/15 px-3 py-2 text-sm text-white/85">
                                      {step}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}
                            {message.retrievedChunks?.length ? (
                              <div className="mt-4">
                                <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-white/45">Retrieved chunks</p>
                                <div className="space-y-2">
                                  {message.retrievedChunks.map((chunk, idx) => (
                                    <div key={`${chunk.chunkId}-${chunk.page}-${idx}`} className="rounded-xl border border-white/10 bg-black/15 p-3">
                                      <div className="mb-1 flex items-center justify-between gap-2 text-[11px] uppercase tracking-[0.18em] text-white/50">
                                        <span>Page {chunk.page}</span>
                                        <span>{Math.round(chunk.score * 100)}%</span>
                                      </div>
                                      <p className="m-0 line-clamp-4 text-sm leading-6 text-white/85">{chunk.content}</p>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            )
          })}
          {isLoading ? <ThinkingPanel isVisible={showThinking} retrievedChunks={[]} /> : null}
          <div ref={messagesEndRef} />
        </div>
      </div>
      <div className="shrink-0 border-t border-border/80 bg-paper-soft px-5 py-4">
        <div className="flex items-end gap-3">
          <input
            type="text"
            value={input}
            onChange={event => setInput(event.target.value)}
            onKeyDown={event => event.key === 'Enter' && !event.shiftKey && handleSendMessage()}
            placeholder="Ask a question about your document..."
            className="min-w-0 flex-1 rounded-xl border border-border bg-paper px-4 py-3 text-sm text-ink-text shadow-sm outline-none transition placeholder:text-ink-muted focus:border-accent focus:ring-2 focus:ring-accent/20"
          />
          <div className="relative h-10 w-10 shrink-0">
            <button
              type="button"
              onClick={handleSendMessage}
              disabled={isLoading || !hasInput}
              ref={sendBtnRef}
              className={`absolute inset-0 flex items-center justify-center rounded-xl bg-accent text-paper transition-all duration-200 ${hasInput ? 'pointer-events-auto scale-100 opacity-100' : 'pointer-events-none scale-95 opacity-0'}`}
            >
              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5.951-1.488 5.738 1.488a1 1 0 001.187-1.41l-7-14z" />
              </svg>
            </button>
            <button
              type="button"
              onMouseDown={startRecording}
              onMouseUp={stopRecording}
              onMouseLeave={stopRecording}
              ref={audioBtnRef}
              className={`absolute inset-0 flex items-center justify-center rounded-xl text-paper transition-all duration-200 ${hasInput ? 'pointer-events-none scale-95 opacity-0' : 'pointer-events-auto scale-100 opacity-100'} ${isRecording ? 'bg-danger' : 'bg-ink-soft'}`}
            >
              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 005 8a1 1 0 00-2 0A7.001 7.001 0 006 14.93V17H9a1 1 0 100-2h-.5a1 1 0 00-1 1v3a1 1 0 001 1h5a1 1 0 001-1v-3a1 1 0 00-1-1H11v-2.07z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}