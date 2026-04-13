import { getAgentIcon } from '../types'

interface Props {
  agent: string
  size?: number
}

export function AgentIcon({ agent, size = 13 }: Props) {
  const Icon = getAgentIcon(agent)
  return <Icon size={size} />
}
