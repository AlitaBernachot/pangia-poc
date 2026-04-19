// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useCallback, useRef, useState } from 'react'
import type { AgentActivity, AgentInfo, ChoiceRequestEvent, DatasetCandidate, DataVizPayload, HITLRequestEvent, Message, OgcLayer, ToolActivity } from '../types'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

export function usePangiaChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [selectedSources, setSelectedSources] = useState<string[]>([])
  const [hitlRequest, setHitlRequest] = useState<HITLRequestEvent | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  // Always-current ref used by callbacks that need synchronous access to the
  // latest messages without capturing a stale closure value.
  const messagesRef = useRef<Message[]>(messages)
  messagesRef.current = messages

  // Empty dependency array: fetchAgents only calls the backend and sets local state;
  // it doesn't capture any reactive values that would change over time.
  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/sources`)
      if (!res.ok) return
      const data = await res.json()
      const list: AgentInfo[] = (data.sources ?? []).map((s: { id: string; label: string }) => ({
        key: s.id,
        label: s.label,
      }))
      setAgents(list)
      setSelectedSources(list.map((a) => a.key))
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
            selected_sources: selectedSources.length > 0 ? selectedSources : undefined,
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
            } else if (type === 'routing_plan') {
              // V2 routing plan — backend emits `agents` (flat array) + `reasoning`
              const agents = (event.agents as string[] | undefined) ?? []
              const reasoning = (event.reasoning as string | undefined) ?? ''
              updateAssistant((m) => ({
                ...m,
                routingAgents: agents,
                routingPlan: { steps: agents.map((a, i) => ({ agent_name: a, parallel_group: i })), reasoning },
              }))
            } else if (type === 'token') {
              updateAssistant((m) => ({
                ...m,
                content: m.content + (event.content as string),
              }))
            } else if (type === 'final_answer') {
              // Replace content — synthesis_node may emit a second final_answer
              // that supersedes the raw merge_node answer.
              const answer = event.answer as string
              if (answer) {
                updateAssistant((m) => ({ ...m, content: answer }))
              }
            } else if (type === 'agent_start') {
              const agent = event.agent as string
              updateAssistant((m) => {
                const activities = [...(m.agentActivity ?? [])]
                const idx = activities.findIndex((a) => a.agent === agent)
                if (idx < 0) {
                  activities.push({ agent, content: '', streaming: true, tools: [] })
                } else {
                  // resumed after a choice — mark streaming again
                  activities[idx] = { ...activities[idx], streaming: true }
                }
                return { ...m, agentActivity: activities }
              })
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
            } else if (type === 'agent_end') {
              // V2 agent_end — update activity panel
              const agent = event.agent as string
              const answer = (event.answer as string | undefined) ?? ''
              updateAssistant((m) => {
                const activities = [...(m.agentActivity ?? [])]
                const idx = activities.findIndex((a) => a.agent === agent)
                if (idx >= 0) {
                  activities[idx] = { ...activities[idx], content: answer ?? activities[idx].content, streaming: false }
                } else {
                  activities.push({ agent, content: answer, streaming: false, tools: [] })
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
            } else if (type === 'ogc_layer') {
              updateAssistant((m) => ({
                ...m,
                ogcLayers: event.layers as OgcLayer[],
              }))
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
            } else if (type === 'dataset_choice') {
              updateAssistant((m) => ({
                ...m,
                choiceRequest: {
                  request_id: event.request_id as string,
                  agent: event.agent as string,
                  items: event.candidates as ChoiceRequestEvent['items'],
                  total: (event.total as number | null) ?? null,
                  original_query: event.original_query as string,
                },
              }))
            } else if (type === 'choice_request') {
              updateAssistant((m) => ({
                ...m,
                choiceRequest: event as unknown as ChoiceRequestEvent,
              }))
            } else if (type === 'hitl_request') {
              // V2 HITL — show modal to the user
              setHitlRequest({
                request_id: event.request_id as string,
                questions: event.questions as string[],
                original_query: event.original_query as string,
              })
            } else if (type === 'hitl_resolved' || type === 'hitl_timeout') {
              setHitlRequest(null)
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
    [isStreaming, sessionId, selectedSources],
  )

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
    setIsStreaming(false)
    // Mark the in-progress assistant message as no longer streaming so
    // "Thinking…" indicators disappear immediately in the UI.
    setMessages((prev) =>
      prev.map((m) => {
        if (m.role !== 'assistant' || !m.streaming) return m
        const activities = (m.agentActivity ?? []).map(
          (a): AgentActivity => ({ ...a, streaming: false }),
        )
        return { ...m, streaming: false, agentActivity: activities }
      }),
    )
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    setSessionId(null)
  }, [])

  const dismissHitl = useCallback(() => setHitlRequest(null), [])

  const submitHitlResponse = useCallback(
    async (question: string) => {
      if (!hitlRequest) return
      const requestId = hitlRequest.request_id
      // Clear the modal immediately so the UI stops waiting
      setHitlRequest(null)
      try {
        await fetch(`${API_BASE}/api/hitl/respond`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ request_id: requestId, clarified_query: question }),
        })
      } catch {
        // Non-fatal — the backend will timeout gracefully
      }
    },
    [hitlRequest],
  )

  const submitChoiceResponse = useCallback(
    async (messageId: string, chosenId: string, chosenQuery: string, candidate?: DatasetCandidate) => {
      // Read requestId synchronously from the ref — React 18 state updaters
      // run asynchronously, so reading via setMessages(fn) side-effect would
      // leave requestId as '' when checked immediately after.
      const choiceMsg = messagesRef.current.find((m) => m.id === messageId)
      const requestId = choiceMsg?.choiceRequest?.request_id
      const agentName = choiceMsg?.choiceRequest?.agent
      if (!requestId) return
      // Clear the choice panel, store the chosen dataset for display, and
      // mark the agent as streaming again so the activity panel shows
      // "Thinking…" while the resumed run executes.
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== messageId) return m
          const agentActivity = agentName
            ? (m.agentActivity ?? []).map((a) =>
                a.agent === agentName ? { ...a, streaming: true, tools: [] } : a,
              )
            : m.agentActivity
          return { ...m, choiceRequest: null, chosenDataset: candidate ?? null, streaming: true, agentActivity }
        }),
      )
      try {
        await fetch(`${API_BASE}/api/choice/respond`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ request_id: requestId, chosen_id: chosenId, chosen_query: chosenQuery }),
        })
      } catch {
        // Non-fatal
      }
    },
    [],
  )

  return {
    messages,
    isStreaming,
    sessionId,
    agents,
    selectedSources,
    setSelectedSources,
    sendMessage,
    stopStreaming,
    clearMessages,
    fetchAgents,
    hitlRequest,
    dismissHitl,
    submitHitlResponse,
    submitChoiceResponse,
  }
}
