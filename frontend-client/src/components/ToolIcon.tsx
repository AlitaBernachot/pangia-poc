// SPDX-FileCopyrightText: 2026 AlitaBernachot
//
// SPDX-License-Identifier: MIT

import { getToolMeta } from '../types'

interface Props {
  tool: string
  size?: number
}

export function ToolIcon({ tool, size = 11 }: Props) {
  const Icon = getToolMeta(tool).icon
  return <Icon size={size} />
}
