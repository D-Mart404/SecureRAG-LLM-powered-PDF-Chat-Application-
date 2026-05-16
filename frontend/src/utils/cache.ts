const CACHE_KEY = 'active_chat_id'

export function getCachedChatId() {
  return localStorage.getItem(CACHE_KEY)
}

export function setCachedChatId(chatId: string) {
  if (!chatId) {
    localStorage.removeItem(CACHE_KEY)
    return
  }

  localStorage.setItem(CACHE_KEY, chatId)
}

export function clearCachedChatId() {
  localStorage.removeItem(CACHE_KEY)
}
