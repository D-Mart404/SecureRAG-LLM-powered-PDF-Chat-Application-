import type { ChatCard, ChatMessage } from '../types'

export const homeCards: ChatCard[] = [
  {
    id: 1,
    title: 'How do I keep sensitive docs out of the prompt?',
    preview:
      'Use a retrieval layer with document filters, keep secrets in a private index, and expose only policy-approved context.',
    updatedAt: '2m ago',
    messageCount: 4,
    category: 'Governance',
  },
  {
    id: 2,
    title: 'What controls reduce hallucinations in enterprise RAG?',
    preview:
      'Add reranking, citations, low-temperature answers, and a verification pass before final delivery.',
    updatedAt: '14m ago',
    messageCount: 6,
    category: 'Quality',
  },
  {
    id: 3,
    title: 'How should I separate public and private knowledge?',
    preview:
      'Partition embeddings, gate retrieval by user claims, and record the source class with every answer.',
    updatedAt: '1h ago',
    messageCount: 3,
    category: 'Access',
  },
  {
    id: 4,
    title: 'Can I audit which chunks were used in the response?',
    preview:
      'Store source ids, retrieval scores, and the final citation set so compliance can trace each answer.',
    updatedAt: '3h ago',
    messageCount: 5,
    category: 'Audit',
  },
  {
    id: 5,
    title: 'How do I handle stale policy documents?',
    preview:
      'Version the corpus, tag effective dates, and prioritize the newest approved revision during retrieval.',
    updatedAt: 'Yesterday',
    messageCount: 4,
    category: 'Lifecycle',
  },
  {
    id: 6,
    title: 'What is the safest way to expose chat memory?',
    preview:
      'Persist only user-approved preferences, sanitize everything, and never keep raw secrets or credentials.',
    updatedAt: 'Yesterday',
    messageCount: 2,
    category: 'Safety',
  },
]

export const initialMessages: ChatMessage[] = [
  {
    id: 1,
    role: 'assistant',
    text: 'SecureRAG keeps retrieval scoped, cited, and auditable so your team can answer confidently without exposing the full corpus.',
    timestamp: '09:12',
  },
  {
    id: 2,
    role: 'user',
    text: 'Show me the safest way to separate internal and external documents.',
    timestamp: '09:13',
  },
  {
    id: 3,
    role: 'assistant',
    text: 'Use distinct indexes, user-aware filters, and a policy layer that only passes approved context into generation.',
    timestamp: '09:13',
  },
]
