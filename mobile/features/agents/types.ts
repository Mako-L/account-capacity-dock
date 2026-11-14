export type AgentStatus = 'working' | 'blocked' | 'done' | 'idle'

export type AgentSignal = 'yellow' | 'red' | 'green' | 'gray'

export type AgentStep = { title: string | null; status: string | null; took: number | null; since: number | null }

/** Tokens and API price of an agent's work (dock: AgentUsage). */
export type AgentUsage = {
  input: number | null
  output: number | null
  cacheRead: number | null
  cacheWrite: number | null
  cost: number | null
  weekPercent: number | null
}

export type AgentEvent = { at: number | null; text: string; kind: string | null }

/** A subagent as the dock's subagent list shows it. */
export type Subagent = {
  id: string
  name: string | null
  description: string | null
  model: string | null
  running: boolean
  idle: boolean
  step: string | null
  updated: number | null
  kind: string | null
  progress: number | null
  phase: string | null
  summary: string | null
  steps: AgentStep[]
  children: number
}

/** One agent as agents_server.py serves it: agents.json without prompts, transcripts or folders. */
export type Agent = {
  id: string
  agent: string
  name: string | null
  tabName: string | null
  project: string | null
  status: string
  title: string | null
  task: string | null
  now: string | null
  progress: number | null
  stepCount: [number, number] | null
  updated: number | null
  started: number | null
  steps: AgentStep[]
  subagents: Subagent[]
  activity: AgentEvent[]
  usage: AgentUsage | null
  totalUsage: AgentUsage | null
}

export type AgentsReply = { at: number | null; agents: Agent[] }

/** What the widget and the watch read for each agent. */
export type SharedAgent = {
  id: string
  provider: 'Claude' | 'Codex'
  name: string
  heading: string
  step: string
  progress: number | null
  ring: number
  status: string
  state: string
  signal: AgentSignal
  subagents: number
  runningSubagents: number
}
