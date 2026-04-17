// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useCallback, useRef, useState } from 'react'
import type { AgentActivity, AgentInfo, DatasetCandidate, DataVizPayload, HITLRequestEvent, Message, OgcLayer, ToolActivity } from '../types'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

export function usePangiaChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [selectedAgents, setSelectedAgents] = useState<string[]>([])
  const [hitlRequest, setHitlRequest] = useState<HITLRequestEvent | null>(null)
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
            } else if (type === 'routing_plan') {
              // V2 routing plan event
              const steps = event.steps as { agent_name: string; parallel_group: number }[]
              const reasoning = event.reasoning as string
              updateAssistant((m) => ({
                ...m,
                routingAgents: steps.map((s) => s.agent_name),
                routingPlan: { steps, reasoning },
              }))
            } else if (type === 'token') {
              updateAssistant((m) => ({
                ...m,
                content: m.content + (event.content as string),
              }))
            } else if (type === 'final_answer') {
              // V2 final answer — append to content
              const answer = event.answer as string
              if (answer) {
                updateAssistant((m) => ({
                  ...m,
                  content: m.content ? m.content + '\n\n' + answer : answer,
                }))
              }
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
                datasetChoice: event.candidates as DatasetCandidate[],
                datasetChoiceTotal: (event.total as number | null) ?? null,
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
    [isStreaming, sessionId, selectedAgents],
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
    hitlRequest,
    dismissHitl,
  }
}
