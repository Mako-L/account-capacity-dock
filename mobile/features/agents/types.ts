export type AgentStatus = 'working' | 'blocked' | 'done' | 'idle'

export type AgentSignal = 'yellow' | 'red' | 'green' | 'gray'

export type AgentStep = { title: string | null; status: string | null }

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
  subagents: { running: number; total: number }
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
}
