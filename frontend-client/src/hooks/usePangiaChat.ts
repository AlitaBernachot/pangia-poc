import { useCallback, useRef, useState } from 'react'
import type { AgentActivity, AgentInfo, DataVizPayload, Message, ToolActivity } from '../types'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

export function usePangiaChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [selectedAgents, setSelectedAgents] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)

  // Empty dependency array: fetchAgents only calls the backend and sets local state;
  // it doesn't capture any reactive values that would change over time.
  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/agents`)
      if (!res.ok) return
      const data = await res.json()
      const list: AgentInfo[] = data.agents ?? []
      setAgents(list)
      setSelectedAgents(list.map((a) => a.key))
    } catch {
      // backend not available yet — no-op
    }
  }, [])

  const sendMessage = useCallback(
    async (text: string) => {
      if (isStreaming || !text.trim()) return

      // Add user message immediately
      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text.trim(),
      }

      // Placeholder for assistant response
      const assistantId = crypto.randomUUID()
      const assistantMsg: Message = {
        id: assistantId,
        role: 'assistant',
        content: '',
        streaming: true,
        agentActivity: [],
      }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsStreaming(true)

      const ctrl = new AbortController()
      abortRef.current = ctrl

      try {
        const res = await fetch(`${API_BASE}/api/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: text.trim(),
            session_id: sessionId,
            selected_agents: selectedAgents.length > 0 ? selectedAgents : undefined,
          }),
          signal: ctrl.signal,
        })

        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        const updateAssistant = (updater: (msg: Message) => Message) => {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? updater(m) : m)),
          )
        }

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6).trim()
            if (!raw) continue
            let event: Record<string, unknown>
            try {
              event = JSON.parse(raw)
            } catch {
              continue
            }

            const type = event.type as string

            if (type === 'session') {
              setSessionId(event.session_id as string)
            } else if (type === 'routing') {
              const agents = event.agents as string[]
              updateAssistant((m) => ({ ...m, routingAgents: agents }))
            } else if (type === 'token') {
              updateAssistant((m) => ({
                ...m,
                content: m.content + (event.content as string),
              }))
            } else if (type === 'agent_token') {
              const agent = event.agent as string
              const token = event.content as string
              updateAssistant((m) => {
                const activities = [...(m.agentActivity ?? [])]
                const idx = activities.findIndex((a) => a.agent === agent)
                if (idx >= 0) {
                  activities[idx] = {
                    ...activities[idx],
                    content: activities[idx].content + token,
                    streaming: true,
                  }
                } else {
                  activities.push({ agent, content: token, streaming: true, tools: [] })
                }
                return { ...m, agentActivity: activities }
              })
            } else if (type === 'tool_start') {
              const agent = event.agent as string
              const tool = event.tool as string
              updateAssistant((m) => {
                const activities = [...(m.agentActivity ?? [])]
                const idx = activities.findIndex((a) => a.agent === agent)
                const newTool: ToolActivity = { tool, status: 'running' }
                if (idx >= 0) {
                  activities[idx] = {
                    ...activities[idx],
                    tools: [...activities[idx].tools, newTool],
                  }
                } else {
                  activities.push({ agent, content: '', streaming: true, tools: [newTool] })
                }
                return { ...m, agentActivity: activities }
              })
            } else if (type === 'tool_end') {
              const agent = event.agent as string
              const tool = event.tool as string
              updateAssistant((m) => {
                const activities = [...(m.agentActivity ?? [])]
                const idx = activities.findIndex((a) => a.agent === agent)
                if (idx >= 0) {
                  const tools = activities[idx].tools.map((t): ToolActivity =>
                    t.tool === tool && t.status === 'running' ? { ...t, status: 'done' } : t,
                  )
                  activities[idx] = { ...activities[idx], tools }
                }
                return { ...m, agentActivity: activities }
              })
            } else if (type === 'geojson') {
              updateAssistant((m) => ({
                ...m,
                geojson: event.data as Record<string, unknown>,
              }))
            } else if (type === 'dataviz') {
              updateAssistant((m) => ({
                ...m,
                dataviz: event.data as DataVizPayload,
              }))
            } else if (type === 'done') {
              updateAssistant((m) => {
                const activities = (m.agentActivity ?? []).map(
                  (a): AgentActivity => ({ ...a, streaming: false }),
                )
                return { ...m, streaming: false, agentActivity: activities }
              })
            } else if (type === 'error') {
              updateAssistant((m) => ({
                ...m,
                streaming: false,
                content: m.content || `Error: ${event.content as string}`,
              }))
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') return
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, streaming: false, content: m.content || 'An error occurred.' }
              : m,
          ),
        )
      } finally {
        setIsStreaming(false)
        abortRef.current = null
      }
    },
    [isStreaming, sessionId, selectedAgents],
  )

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
    setIsStreaming(false)
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    setSessionId(null)
  }, [])

  return {
    messages,
    isStreaming,
    sessionId,
    agents,
    selectedAgents,
    setSelectedAgents,
    sendMessage,
    stopStreaming,
    clearMessages,
    fetchAgents,
  }
}
