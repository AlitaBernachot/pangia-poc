// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { type AgentActivity, AGENT_COLORS, getAgentLabel, getToolPhase, type PhaseKey, SOURCE_AGENT_KEYS } from '../../types'
import { AgentIcon } from '../AgentIcon'
import {
  ChevronDown, ChevronRight, CheckCheck, Lightbulb, Clock,
  Database, Download, MapPin, Hash, Activity, BarChart2,
  type LucideIcon,
} from 'lucide-react'

interface Props {
  activity: AgentActivity
  isLast?: boolean
}

const PHASE_ICON: Record<PhaseKey, LucideIcon> = {
  querying:    Database,
  fetching:    Download,
  locating:    MapPin,
  computing:   Hash,
  processing:  Activity,
  visualizing: BarChart2,
}

type PhasedStep = {
  phase: PhaseKey
  status: 'running' | 'done'
  stepKey: string
}

function getPhasedSteps(tools: AgentActivity['tools']): PhasedStep[] {
  const steps: PhasedStep[] = []
  for (const tool of tools) {
    const phase = getToolPhase(tool.tool)
    const last = steps[steps.length - 1]
    if (last && last.phase === phase) {
      if (tool.status === 'running') last.status = 'running'
    } else {
      steps.push({ phase, status: tool.status, stepKey: `${phase}_${steps.length}` })
    }
  }
  return steps
}

export function AgentActivityPanel({ activity, isLast = false }: Props) {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState(true)
  const label = getAgentLabel(activity.agent)
  const colors = AGENT_COLORS[label]

  const runningTool = [...activity.tools].reverse().find((tool) => tool.status === 'running')
  const lastTool = runningTool ?? [...activity.tools].at(-1)
  const phasedSteps = getPhasedSteps(activity.tools)

  const currentPhaseKey: PhaseKey | null = lastTool
    ? getToolPhase(lastTool.tool)
    : SOURCE_AGENT_KEYS.has(activity.agent) ? 'querying' : null
  const CurrentPhaseIcon: LucideIcon = currentPhaseKey ? PHASE_ICON[currentPhaseKey] : Lightbulb

  const hasExpandableContent = phasedSteps.length > 0 || !!activity.content
  // Show expanded content when: user opened it OR stream is active and has content
  const showContent = (!collapsed && hasExpandableContent) || (activity.streaming && !!activity.content)

  const iconStyle = colors
    ? { borderColor: colors.border, background: colors.bg, color: colors.text }
    : { borderColor: 'rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.45)' }

  return (
    <div className="flex gap-2.5 text-xs">
      {/* ── Left column: icon bubble + vertical line ── */}
      <div className="flex flex-col items-center shrink-0" style={{ width: 22 }}>
        <div
          className="w-5.5 h-5.5 flex items-center justify-center shrink-0"
          style={iconStyle}
        >
          <AgentIcon agent={label} size={11} />
        </div>
        {!isLast && (
          <div className="w-px flex-1 mt-1" style={{ background: 'rgba(255,255,255,0.18)' }} />
        )}
      </div>

      {/* ── Right column: accordion ── */}
      <div className={`flex-1 min-w-0 ${!isLast ? 'pb-4' : ''}`}>
        {/* Header row */}
        <button
          type="button"
          onClick={() => hasExpandableContent && setCollapsed((c) => !c)}
          className={`w-full flex items-center gap-1.5 py-0.5 px-1 -mx-1 rounded text-left group transition-colors ${hasExpandableContent ? 'cursor-pointer' : 'cursor-default'}`}
          style={{ minHeight: 22 }}
          onMouseEnter={(e) => { if (hasExpandableContent) (e.currentTarget as HTMLElement).style.background = colors ? colors.bg : 'rgba(255,255,255,0.04)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = '' }}
        >
          <span className="font-medium text-white/80">{label}</span>

          {/* Status badge */}
          <span className="ml-0.5">
            {activity.waitingForChoice ? (
              <span className="inline-flex items-center gap-1 text-amber-400/80">
                <Clock size={10} />
                <span>{t('agentActivity.waitingForChoice')}</span>
              </span>
            ) : activity.streaming ? (
              <span className="inline-flex items-center gap-1 text-white/40">
                <span className="shimmer-icon">
                  <CurrentPhaseIcon size={10} />
                </span>
                <span className="thinking-indicator">
                  {currentPhaseKey
                    ? t(`agentActivity.phases.${currentPhaseKey}`)
                    : t('agentActivity.thinking')}
                </span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-green-400/70">
                <CheckCheck size={10} />
                <span>{t('agentActivity.done')}</span>
              </span>
            )}
          </span>

          {/* Chevron — right-aligned, hidden if nothing to expand */}
          {hasExpandableContent && (
            <span className="ml-auto shrink-0 text-white/20 group-hover:text-white/55 transition-colors">
              {collapsed ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
            </span>
          )}
        </button>

        {/* Expandable content */}
        {showContent && (
          <div className="mt-1.5 space-y-2">
            {/* Phase steps — only when expanded */}
            {!collapsed && phasedSteps.length > 0 && (
              <div className="flex flex-col gap-1">
                {phasedSteps.map((step) => {
                  const StepIcon = PHASE_ICON[step.phase]
                  const isRunning = step.status === 'running'
                  return (
                    <div
                      key={step.stepKey}
                      className={`flex items-center gap-1.5 ${isRunning ? 'text-white/65' : 'text-white/30'}`}
                    >
                      {isRunning ? (
                        <span className="shimmer-icon shrink-0"><StepIcon size={9} /></span>
                      ) : (
                        <CheckCheck size={9} className="shrink-0 text-green-400/50" />
                      )}
                      <span className={isRunning ? 'thinking-indicator' : ''}>
                        {t(`agentActivity.phases.${step.phase}`)}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}

            {/* Reasoning text */}
            {activity.content && (
              <p
                className="text-white/45 leading-snug whitespace-pre-wrap wrap-break-word pl-0.5"
                style={colors ? { borderLeftColor: `${colors.border}60` } : { borderLeftColor: 'rgba(255,255,255,0.1)' }}
              >
                {activity.content}
                {activity.streaming && <span className="cursor-blink" />}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
