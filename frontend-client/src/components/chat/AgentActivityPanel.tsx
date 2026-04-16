// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { type AgentActivity, AGENT_COLORS } from '../../types'
import { AgentIcon } from '../AgentIcon'
import { ToolIcon } from '../ToolIcon'
import { ChevronDown, ChevronRight, CheckCheck, Lightbulb } from 'lucide-react'

interface Props {
  activity: AgentActivity
}

export function AgentActivityPanel({ activity }: Props) {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState(true)
  const colors = AGENT_COLORS[activity.agent]

  // The most recently started running tool (last in list with status 'running')
  const runningTool = [...activity.tools].reverse().find((tool) => tool.status === 'running')

  return (
    <div className="rounded-lg border border-white/8 overflow-hidden text-xs">
      {/* Header */}
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-white/3 hover:bg-white/5 transition-colors text-left cursor-pointer"
      >
        {collapsed ? (
          <ChevronRight size={12} className="text-white/40 shrink-0" />
        ) : (
          <ChevronDown size={12} className="text-white/40 shrink-0" />
        )}
        <AgentIcon agent={activity.agent} size={13} />
        <span className="font-medium text-white/80">{activity.agent}</span>
        <span
          className={`ml-1 px-1.5 py-0.5 rounded-full text-xs ${
            activity.streaming
              ? ''
              : 'border text-green-400 border-green-400'
          }`}
        >
          {activity.streaming ? (
            runningTool ? (
              <span className="inline-flex items-center gap-1">
                <span className="shimmer-icon">
                  <ToolIcon tool={runningTool.tool} size={10} />
                </span>
                <span className="thinking-indicator">
                  {t(`toolLabels.${runningTool.tool}`, runningTool.tool)}
                </span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1">
                <Lightbulb size={10} className="thinking-indicator" />
                <span className="thinking-indicator">{t('agentActivity.thinking')}</span>
              </span>
            )
          ) : (
            <span className="inline-flex items-center gap-1">
              <CheckCheck size={10} />
              {t('agentActivity.done')}
            </span>
          )}
        </span>
      </button>

      {/* Content */}
      {!collapsed && (
        <div className="px-3 pb-3 pt-2 bg-white/[0.02]">
          {/* Tool badges */}
          {activity.tools.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {activity.tools.map((tool, i) => (
                <span
                  key={i}
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] border ${
                    tool.status === 'running'
                      ? 'text-cyan-400 border-cyan-400'
                      : 'text-green-400 border-green-400'
                  }`}
                >
                  <span className={tool.status === 'running' ? 'shimmer-icon' : ''}>
                    <ToolIcon tool={tool.tool} size={9} />
                  </span>
                  <span className={tool.status === 'running' ? 'thinking-indicator' : ''}>
                    {t(`toolLabels.${tool.tool}`, tool.tool)}
                  </span>
                  <span className="size-1.5 rounded-full bg-current" />
                </span>
              ))}
            </div>
          )}

          {/* Reasoning text */}
          {activity.content && (
            <p
              className="text-white/50 leading-snug whitespace-pre-wrap break-words"
              style={colors ? { borderLeftColor: colors.border } : {}}
            >
              {activity.content}
              {activity.streaming && <span className="cursor-blink" />}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
