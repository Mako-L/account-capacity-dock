// The Agents view: every running coding agent, what it works on now, its steps and its subagents.
// Data comes from agents.py, which reads Herdr, Claude Code and Codex state, and an optional observer.
import { useEffect, useRef, useState } from 'react'
import { Button } from '@gpuix/react'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { Bar, C, CACHE, ONE_LINE, ROOT, Scroll, SmallButton, Text, TRACK, arcSvg, run } from './ui'

export type Step = { title: string; status: 'done' | 'active' | 'pending' }
export type Subagent = { id: string; name: string; description?: string | null; model?: string; running: boolean; step?: string | null; updated: number }
export type Agent = {
  id: string; pane: string | null; agent: string; name: string; status: string; title?: string | null; cwd: string; project: string
  task?: string | null; prompt?: string | null; now?: string | null; said?: string | null; steps: Step[]
  activity: { at: number | null; text: string; kind: 'say' | 'tool' }[]; updated?: number | null; source: string
  progress: number | null; stepCount?: [number, number]; subagents: Subagent[]
}
type Snapshot = { at?: number; agents: Agent[]; observer?: boolean }

const FILE = process.env.MAKO_AGENTS_SNAPSHOT ?? path.join(CACHE, 'agents.json')
// Three colours: yellow while an agent works, red when it needs you, green when it finished.
const LIVE = C.yellow
export const STATUS: Record<string, { label: string; color: string }> = {
  working: { label: 'Working', color: LIVE }, blocked: { label: 'Needs you', color: C.red },
  done: { label: 'Finished', color: C.green }, idle: { label: 'Idle', color: C.muted },
}
const status = (a: Agent) => STATUS[a.status] ?? STATUS.idle
const live = (a: Agent) => a.status === 'working' || a.status === 'blocked'
const KIND: Record<string, { color: string; icon?: string }> = {
  claude: { color: '#e69860', icon: path.join(ROOT, 'docs/images/claude.png') },
  codex: { color: '#5cd6b3', icon: path.join(ROOT, 'docs/images/codex.png') },
}
const CHECK = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>'
const SOURCE: Record<string, string> = {
  tasks: 'Steps from the agent’s own task list', report: 'Reported by the agent',
  observer: 'Steps named by the observer model', activity: 'Live tool calls; no steps yet',
}

export function ago(at?: number | null) {
  if (!at) return ''
  const s = Math.max(0, Math.round(Date.now() / 1000 - at))
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)}m ago` : s < 86400 ? `${Math.floor(s / 3600)}h ago` : `${Math.floor(s / 86400)}d ago`
}

function read(): Snapshot {
  try {
    const data = JSON.parse(readFileSync(FILE, 'utf8'))
    return { at: data.at, agents: data.agents ?? [], observer: data.observer }
  } catch { return { agents: [] } }
}

// Runs agents.py while the view is open: the live parts every 5 s, the observer at most every 45 s.
// The tree re-renders only when something changed, because in a terminal every frame is a full image.
export function useAgents(active: boolean) {
  const [snapshot, setSnapshot] = useState<Snapshot>(read)
  const [, setTick] = useState(0)
  const last = useRef('')
  useEffect(() => {
    if (!active) return
    let stopped = false, busy = false, observed = 0
    const update = (next: Snapshot) => {
      const key = JSON.stringify(next.agents)
      if (key !== last.current) { last.current = key; setSnapshot(next) }
    }
    async function poll() {
      if (busy || stopped) return
      busy = true
      if (!process.env.MAKO_AGENTS_SNAPSHOT) {
        const observe = Date.now() - observed > 45_000
        if (observe) observed = Date.now()
        await run([path.join(ROOT, 'agents.py'), ...(observe ? ['--observe'] : [])])
      }
      if (!stopped) update(read())
      busy = false
    }
    poll()
    const timer = setInterval(poll, 5_000)
    const clock = setInterval(() => setTick(t => t + 1), 15_000)
    return () => { stopped = true; clearInterval(timer); clearInterval(clock) }
  }, [active])
  return snapshot
}

// A ring like the account rings: progress around the agent's icon, coloured by status.
export function AgentRing({ agent, size }: { agent: Agent; size: number }) {
  const icon = Math.round(size * 0.42), dot = Math.max(8, Math.round(size * 0.24))
  const kind = KIND[agent.agent]
  const value = agent.progress ?? (live(agent) ? 8 : 0)
  return (
    <div style={{ width: size, height: size, flexShrink: 0, position: 'relative', alignItems: 'center', justifyContent: 'center', display: 'flex' }}>
      <svg source={TRACK} style={{ position: 'absolute', top: 0, left: 0, width: size, height: size, color: C.line }} />
      {arcSvg(value) && <svg source={arcSvg(value)!} style={{ position: 'absolute', top: 0, left: 0, width: size, height: size, color: status(agent).color }} />}
      {kind?.icon
        ? <img src={kind.icon} style={{ width: icon, height: icon }} />
        : <Text size={Math.round(size * 0.34)} weight={700} color={C.text}>{agent.agent.slice(0, 1).toUpperCase()}</Text>}
      {/* The status light: a soft halo behind a solid dot, our version of a glow. */}
      <div style={{ position: 'absolute', right: -2, bottom: -2, width: dot + 6, height: dot + 6, borderRadius: dot, backgroundColor: live(agent) ? status(agent).color + '33' : '#00000000',
                    alignItems: 'center', justifyContent: 'center', display: 'flex' }}>
        <div style={{ width: dot, height: dot, borderRadius: dot, backgroundColor: status(agent).color, borderWidth: 2, borderColor: C.dock }} />
      </div>
    </div>
  )
}

function Pill({ label, color }: { label: string; color: string }) {
  return (
    <div style={{ paddingLeft: 7, paddingRight: 7, paddingTop: 2, paddingBottom: 2, borderRadius: 20, backgroundColor: color + '24', flexShrink: 0 }}>
      <Text size={10} weight={600} color={color}>{label}</Text>
    </div>
  )
}

function stepLabel(agent: Agent) {
  const n = agent.stepCount
  return n ? `${n[0]} of ${n[1]} steps` : agent.progress != null ? `${agent.progress}%` : ''
}

// One live agent in the list: what it is doing this minute, and how far along it is.
function AgentCard({ agent, active, onHover, onOpen }: { agent: Agent; active: boolean; onHover: () => void; onOpen: () => void }) {
  const running = agent.subagents.filter(s => s.running).length
  return (
    <Button onClick={onOpen} onMouseEnter={onHover} style={{
      backgroundColor: active ? '#232327' : C.card, borderRadius: 16, borderWidth: 1, borderColor: active ? status(agent).color + '66' : '#ffffff12',
      padding: 14, display: 'flex', flexDirection: 'column', gap: 9, flexShrink: 0, cursor: 'pointer',
      hover: { borderColor: status(agent).color + '66' }, focusVisible: { outlineWidth: 2, outlineColor: '#64a8ff' },
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <AgentRing agent={agent} size={40} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flexGrow: 1, flexShrink: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Text size={12} weight={600} color={C.muted} style={{ ...ONE_LINE, flexShrink: 1, minWidth: 0 }}>{agent.name}</Text>
            <Pill label={status(agent).label} color={status(agent).color} />
          </div>
          <Text size={14} weight={600} style={ONE_LINE}>{agent.task || agent.title || 'Untitled session'}</Text>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', flexShrink: 0 }}>
          {agent.progress != null ? <Text size={18} weight={600} color={status(agent).color}>{`${agent.progress}%`}</Text> : null}
          {agent.stepCount ? <Text size={10} color={C.muted}>{`${agent.stepCount[0]}/${agent.stepCount[1]} steps`}</Text> : null}
        </div>
      </div>
      {agent.now ? <Text size={12} color={C.text} style={ONE_LINE}>{`▸ ${agent.now}`}</Text> : null}
      {agent.progress != null ? <Bar value={agent.progress} color={status(agent).color} /> : null}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {running ? <Pill label={`${running} subagent${running === 1 ? '' : 's'} running`} color={LIVE} /> : null}
        <Text size={10} color={C.muted} style={{ ...ONE_LINE, flexShrink: 1, minWidth: 0 }}>{`${agent.project} · ${ago(agent.updated)}`}</Text>
      </div>
    </Button>
  )
}

// Idle and finished agents take one line each.
function AgentLine({ agent, active, onHover, onOpen }: { agent: Agent; active: boolean; onHover: () => void; onOpen: () => void }) {
  return (
    <Button onClick={onOpen} onMouseEnter={onHover} style={{
      display: 'flex', alignItems: 'center', gap: 10, paddingTop: 6, paddingBottom: 6, paddingLeft: 8, paddingRight: 10, borderRadius: 12, flexShrink: 0, cursor: 'pointer',
      backgroundColor: active ? '#ffffff12' : undefined, hover: { backgroundColor: '#ffffff12' }, focusVisible: { outlineWidth: 2, outlineColor: '#64a8ff' },
    }}>
      <AgentRing agent={agent} size={30} />
      <div style={{ display: 'flex', flexDirection: 'column', flexGrow: 1, flexShrink: 1, minWidth: 0 }}>
        <Text size={12} weight={600} style={ONE_LINE}>{agent.task || agent.title || agent.name}</Text>
        <Text size={10} color={C.muted} style={ONE_LINE}>{`${agent.name} · ${status(agent).label} · ${ago(agent.updated)}`}</Text>
      </div>
    </Button>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <Text size={10} weight={700} color={C.muted}>{title.toUpperCase()}</Text>
      {children}
    </div>
  )
}

// A vertical timeline: done steps carry a check, the active one a lit dot, the rest an empty ring.
function Timeline({ steps }: { steps: Step[] }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {steps.map((step, i) => {
        const color = step.status === 'done' ? C.green : step.status === 'active' ? LIVE : C.muted
        return (
          <div key={i} style={{ display: 'flex', gap: 10, flexShrink: 0 }}>
            <div style={{ width: 18, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              {step.status === 'done'
                ? <div style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: C.green + '2e', alignItems: 'center', justifyContent: 'center', display: 'flex' }}>
                    <svg source={CHECK} style={{ width: 12, height: 12, color: C.green }} />
                  </div>
                : step.status === 'active'
                  ? <div style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: LIVE + '33', alignItems: 'center', justifyContent: 'center', display: 'flex' }}>
                      <div style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: LIVE }} />
                    </div>
                  : <div style={{ width: 14, height: 14, borderRadius: 7, borderWidth: 2, borderColor: '#ffffff2e', marginTop: 1 }} />}
              {i < steps.length - 1 && <div style={{ width: 2, flexGrow: 1, minHeight: 8, backgroundColor: step.status === 'done' ? C.green + '55' : '#ffffff1a' }} />}
            </div>
            <Text size={12} color={step.status === 'pending' ? C.muted : C.text} weight={step.status === 'active' ? 600 : undefined}
                  style={{ paddingBottom: 10, flexGrow: 1, flexShrink: 1, minWidth: 0, color }}>{step.title}</Text>
          </div>
        )
      })}
    </div>
  )
}

// The card that opens on hover, like an account's card: steps, subagents and the latest activity.
export function AgentDetail({ agent, onFocus }: { agent: Agent; onFocus?: () => void }) {
  return (
    <div style={{ backgroundColor: C.card, borderRadius: 18, borderWidth: 1, borderColor: '#ffffff12', padding: 16, display: 'flex', flexDirection: 'column', gap: 14,
                  minWidth: 0, flexShrink: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <AgentRing agent={agent} size={46} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, flexGrow: 1, flexShrink: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Text size={11} weight={600} color={(KIND[agent.agent] ?? { color: C.muted }).color}>{agent.agent.toUpperCase()}</Text>
            <Pill label={status(agent).label} color={status(agent).color} />
          </div>
          <Text size={13} weight={600} style={ONE_LINE}>{agent.name}</Text>
        </div>
        {agent.pane && onFocus ? <SmallButton label="Go to pane" onClick={onFocus} /> : null}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <Text size={16} weight={600}>{agent.task || agent.title || 'Untitled session'}</Text>
        {agent.prompt ? <Text size={11} color={C.muted}>{`“${agent.prompt}”`}</Text> : null}
      </div>
      {agent.now ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 10, borderRadius: 10, backgroundColor: LIVE + '14', borderWidth: 1, borderColor: LIVE + '33' }}>
          <div style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: LIVE, flexShrink: 0 }} />
          <Text size={12} style={{ flexGrow: 1, flexShrink: 1, minWidth: 0 }}>{agent.now}</Text>
        </div>) : null}
      {agent.steps.length > 0 && (
        <Section title={`Steps${stepLabel(agent) ? ' · ' + stepLabel(agent) : ''}`}>
          <Timeline steps={agent.steps} />
        </Section>)}
      {agent.subagents.length > 0 && (
        <Section title="Subagents">
          {agent.subagents.map(s => (
            <div key={s.id} style={{ display: 'flex', gap: 10, flexShrink: 0 }}>
              <div style={{ width: 8, height: 8, borderRadius: 4, marginTop: 4, flexShrink: 0, backgroundColor: s.running ? LIVE : C.green + '88' }} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flexGrow: 1, flexShrink: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <Text size={12} weight={600} style={{ ...ONE_LINE, flexShrink: 1, minWidth: 0 }}>{s.description || s.name}</Text>
                  {s.model ? <Pill label={s.model} color={C.muted} /> : null}
                </div>
                <Text size={11} color={C.muted} style={ONE_LINE}>{`${s.running ? '▸ ' + (s.step || 'Working') : 'Done'} · ${ago(s.updated)}`}</Text>
              </div>
            </div>))}
        </Section>)}
      {agent.activity.length > 0 && (
        <Section title="Recent activity">
          {agent.activity.slice(-6).reverse().map((item, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, flexShrink: 0 }}>
              <Text size={10} color={C.muted} style={{ width: 48, flexShrink: 0 }}>{ago(item.at)}</Text>
              <Text size={11} color={item.kind === 'say' ? C.text : C.muted} style={{ ...ONE_LINE, flexGrow: 1, flexShrink: 1, minWidth: 0 }}>{item.text}</Text>
            </div>))}
        </Section>)}
      <Text size={10} color={C.muted}>{`${SOURCE[agent.source] ?? ''}${agent.pane ? ' · pane ' + agent.pane : ''}`}</Text>
    </div>
  )
}

function focusPane(agent: Agent) {
  if (agent.pane) run(['-c', 'import subprocess,sys; subprocess.run(["herdr", "agent", "focus", sys.argv[1]])', agent.pane])
}

const counts = (agents: Agent[]) => {
  const working = agents.filter(a => a.status === 'working').length
  const blocked = agents.filter(a => a.status === 'blocked').length
  const done = agents.filter(a => a.status === 'done').length
  const idle = agents.length - working - blocked - done
  const subs = agents.reduce((n, a) => n + a.subagents.filter(s => s.running).length, 0)
  return [working && `${working} working`, blocked && `${blocked} need you`, subs && `${subs} subagent${subs === 1 ? '' : 's'} running`,
          done && `${done} finished`, idle && `${idle} idle`].filter(Boolean).join(' · ')
}

// The wide view: live agents as cards, the rest as lines, and the hovered agent's card on the right.
export function AgentsWide({ snapshot }: { snapshot: Snapshot }) {
  const [selected, setSelected] = useState<string | null>(null)
  const agents = snapshot.agents
  const current = agents.find(a => a.id === selected) ?? agents.find(live) ?? agents[0]
  const working = agents.filter(live), rest = agents.filter(a => !live(a))
  return (
    <div style={{ display: 'flex', flexGrow: 1, overflow: 'hidden' }}>
      <Scroll style={{ flexGrow: 1, flexShrink: 1, minWidth: 0, overflowY: 'scroll', display: 'flex', flexDirection: 'column', gap: 14, paddingLeft: 16, paddingRight: 10, paddingBottom: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingTop: 6 }}>
          <Text size={26} weight={600}>Your agents. Live.</Text>
          <Text size={13} color={C.muted}>{agents.length ? counts(agents) : 'No agents found. Start Claude Code or Codex, in Herdr or any terminal.'}</Text>
        </div>
        {working.length > 0 && (
          <Section title="Working now">
            {working.map(a => <AgentCard key={a.id} agent={a} active={a.id === current?.id} onHover={() => setSelected(a.id)} onOpen={() => setSelected(a.id)} />)}
          </Section>)}
        {rest.length > 0 && (
          <Section title="Idle and finished">
            {rest.map(a => <AgentLine key={a.id} agent={a} active={a.id === current?.id} onHover={() => setSelected(a.id)} onOpen={() => setSelected(a.id)} />)}
          </Section>)}
      </Scroll>
      <Scroll style={{ width: 406, flexShrink: 0, overflowY: 'scroll', paddingLeft: 10, paddingRight: 16, paddingBottom: 16 }}>
        {current ? <AgentDetail agent={current} onFocus={() => focusPane(current)} /> : null}
      </Scroll>
    </div>
  )
}

// The narrow view: one line per agent, a tap opens its card. Under 200 px only the rings.
export function AgentsCompact({ snapshot, tiny, opened, onOpen }: { snapshot: Snapshot; tiny: boolean; opened: string | null; onOpen: (id: string | null) => void }) {
  const agent = snapshot.agents.find(a => a.id === opened)
  if (agent) {
    return (
      <Scroll style={{ flexGrow: 1, overflowY: 'scroll', paddingLeft: 10, paddingRight: 10, paddingBottom: 10 }}>
        <AgentDetail agent={agent} onFocus={() => focusPane(agent)} />
      </Scroll>
    )
  }
  return (
    <Scroll style={{ flexGrow: 1, overflowY: 'scroll', paddingTop: 8, paddingLeft: tiny ? 0 : 6, paddingRight: tiny ? 0 : 6,
                  display: 'flex', flexDirection: 'column', alignItems: tiny ? 'center' : 'stretch', gap: tiny ? 6 : 2 }}>
      {snapshot.agents.length === 0 && <Text size={12} color={C.muted} style={{ padding: 10 }}>No agents running.</Text>}
      {snapshot.agents.map(a => tiny
        ? <Button key={a.id} onClick={() => onOpen(a.id)} style={{ width: 56, paddingTop: 5, paddingBottom: 4, borderRadius: 12, alignItems: 'center', display: 'flex',
                                                                 flexDirection: 'column', gap: 3, cursor: 'pointer', hover: { backgroundColor: '#ffffff12' } }}>
            <AgentRing agent={a} size={36} />
            <Text size={9.5} color={live(a) ? status(a).color : C.muted} style={{ maxWidth: 54, ...ONE_LINE }}>{a.progress != null ? `${a.progress}%` : a.name}</Text>
          </Button>
        : live(a)
          ? <Button key={a.id} onClick={() => onOpen(a.id)} style={{ display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0, padding: 8, borderRadius: 12, cursor: 'pointer',
                                                                   hover: { backgroundColor: '#ffffff12' } }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <AgentRing agent={a} size={36} />
                <div style={{ display: 'flex', flexDirection: 'column', flexGrow: 1, flexShrink: 1, minWidth: 0 }}>
                  <Text size={13} weight={600} style={ONE_LINE}>{a.task || a.title || a.name}</Text>
                  <Text size={11} color={a.now ? C.text : C.muted} style={ONE_LINE}>{(a.now ? `▸ ${a.now}` : `${a.name} · ${status(a).label}`) + (a.subagents.some(x => x.running) ? ` · ${a.subagents.filter(x => x.running).length} sub` : '')}</Text>
                </div>
                {a.progress != null ? <Text size={14} weight={600} color={status(a).color} style={{ flexShrink: 0 }}>{`${a.progress}%`}</Text> : null}
              </div>
              {a.progress != null ? <Bar value={a.progress} color={status(a).color} /> : null}
            </Button>
          : <AgentLine key={a.id} agent={a} active={false} onHover={() => {}} onOpen={() => onOpen(a.id)} />)}
    </Scroll>
  )
}
