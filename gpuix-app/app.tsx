// Mako Capacity on GPUIX: the dock, All accounts and Settings in one React tree.
// The same tree runs in a native window (`bun app.tsx`) or inside the terminal
// (`GPUIX_TERMINAL=1 bun app.tsx`, Ghostty or kitty, also over SSH).
// Data and actions go through collector.py and scripts/capacity.py, like the other renderers.
import { useEffect, useState } from 'react'
import { Button, render, isTerminal, useWindowSize } from '@gpuix/react'
import { spawn } from 'node:child_process'
import { existsSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import path from 'node:path'

const ROOT = path.resolve(import.meta.dir, '..')
const HOME = process.env.MAKO_CAPACITY_HOME ?? path.join(homedir(), '.mako-capacity')
const CACHE = process.platform === 'darwin'
  ? path.join(homedir(), 'Library/Application Support/Mako Capacity')
  : process.platform === 'win32'
    ? path.join(process.env.LOCALAPPDATA ?? path.join(homedir(), 'AppData/Local'), 'mako-capacity')
    : path.join(process.env.XDG_CACHE_HOME ?? path.join(homedir(), '.cache'), 'mako-capacity')
const SNAPSHOT = process.env.MAKO_CAPACITY_SNAPSHOT ?? path.join(CACHE, 'snapshot.json')
const PYTHON = process.platform === 'win32' ? 'python' : 'python3'
// Present while account names are hidden; the Herdr text widget reads and sets the same file.
const NAMES_FLAG = path.join(HOME, 'hide-names')
// Set only in a Herdr plugin pane, which open.py can pin to every tab.
const PIN_STATE = process.env.HERDR_PLUGIN_STATE_DIR ? path.join(process.env.HERDR_PLUGIN_STATE_DIR, 'pinned-side') : null

const C = {
  bg: '#111111', dock: '#050505', card: '#1c1c1c', line: '#2c2c2e', text: '#f2f2f4', muted: '#9a9aa2',
  green: '#30d158', yellow: '#ffd60a', orange: '#ff9f0a', red: '#ff453a', blue: '#0a84ff',
}
const PROVIDER: Record<string, string> = { Claude: '#e69860', Codex: '#5cd6b3', Cursor: '#b384f2' }
const ICON: Record<string, string> = {
  Claude: path.join(ROOT, 'docs/images/claude.png'),
  Codex: path.join(ROOT, 'docs/images/codex.png'),
}
// GPUI paints an <svg> as one colour mask tinted by style.color, so two-tone art is two layers.
const CUBE = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M12 .13 1.89 5.68 1.47 6.4v11.19l.42.72 9.61 5.55h1l9.61-5.55.42-.72V6.4l-.42-.72L12.5.13Z"/></svg>'
const CUBE_FACET = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M2.66 6.34h18.55l.3.51-9.28 16.07-.23-.06V12.34l-.3-.51-9.11-5.26Z"/></svg>'
const TRACK = '<svg viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg"><circle cx="23" cy="23" r="19" fill="none" stroke="#000" stroke-width="4.5"/></svg>'

type Window = { label: string; used: number; resetAt?: number | null; detail?: string | null }
type Usage = { tokens?: number | null; inputTokens?: number | null; outputTokens?: number | null; costUsd?: number | null; status?: string }
type Account = {
  id: string; provider: string; title: string; email: string; plan: string; status: string; message: string
  source: string; windows: Window[]; fetchedAt?: number | null; localUsage?: Usage | null; proxyRef?: string | null
}
type Snapshot = { accounts: Account[]; hidden?: Record<string, string>; warning?: string | null }

// Same rules as the dock: Cursor shows Cursor Models, the others their tightest window.
const used = (a: Account) => a.provider === 'Cursor'
  ? a.windows.find(w => w.label === 'Cursor Models')?.used ?? null
  : a.windows.length ? Math.max(...a.windows.map(w => w.used)) : null
const signal = (a: Account) => {
  const u = used(a) ?? 0
  return a.status === 'loginRequired' ? C.orange : u >= 100 ? C.red : u >= 85 ? C.orange : u >= 70 ? C.yellow : C.green
}
const STATES: Record<string, string> = { loginRequired: 'Reconnect', rateLimited: 'Throttled', stale: 'Cached', unavailable: 'Unavailable' }
const stateLabel = (a: Account) => a.status === 'live' ? ((used(a) ?? 0) >= 100 ? 'At limit' : 'Available') : STATES[a.status] ?? 'Unknown'
const pct = (a: Account) => used(a) == null ? '—' : `${Math.round(used(a)!)}%`
const count = (v?: number | null) => v == null ? '—' : v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : `${Math.round(v)}`
function resetIn(at?: number | null) {
  if (!at) return 'Reset unknown'
  const m = Math.max(0, Math.round((at * 1000 - Date.now()) / 60000))
  return m < 60 ? `Resets in ${m}m` : m < 1440 ? `Resets in ${Math.floor(m / 60)}h ${m % 60}m` : `Resets in ${Math.floor(m / 1440)}d ${Math.floor((m % 1440) / 60)}h`
}

// A circular ring that starts at the top and runs clockwise, drawn as an SVG arc.
function arcSvg(value: number | null) {
  const r = 19, c = 23, f = Math.min(Math.max(value ?? 0, 0), 99.99) / 100
  if (f <= 0) return null
  const a = f * 2 * Math.PI, x = c + r * Math.sin(a), y = c - r * Math.cos(a)
  return `<svg viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg"><path d="M${c} ${c - r} A${r} ${r} 0 ${f > 0.5 ? 1 : 0} 1 ${x.toFixed(2)} ${y.toFixed(2)}" fill="none" stroke="#000" stroke-width="4.5" stroke-linecap="round"/></svg>`
}

function Ring({ account, size }: { account: Account; size: number }) {
  const icon = Math.round(size * 0.44)
  return (
    <div style={{ width: size, height: size, flexShrink: 0, position: 'relative', alignItems: 'center', justifyContent: 'center', display: 'flex' }}>
      <svg source={TRACK} style={{ position: 'absolute', top: 0, left: 0, width: size, height: size, color: C.line }} />
      {arcSvg(used(account)) && <svg source={arcSvg(used(account))!} style={{ position: 'absolute', top: 0, left: 0, width: size, height: size, color: signal(account) }} />}
      {account.provider === 'Cursor'
        ? <div style={{ width: icon, height: icon, position: 'relative' }}>
            <svg source={CUBE} style={{ position: 'absolute', top: 0, left: 0, width: icon, height: icon, color: '#ffffff' }} />
            <svg source={CUBE_FACET} style={{ position: 'absolute', top: 0, left: 0, width: icon, height: icon, color: C.bg }} />
          </div>
        : <img src={ICON[account.provider]} style={{ width: icon, height: icon }} />}
    </div>
  )
}

function Text({ children, size = 13, color = C.text, weight, style }: {
  children: React.ReactNode; size?: number; color?: string; weight?: number; style?: Record<string, unknown>
}) {
  return <text style={{ fontSize: size, color, fontWeight: weight, ...style }}>{children}</text>
}

function run(args: string[], env: Record<string, string> = {}): Promise<{ ok: boolean; out: string }> {
  return new Promise(resolve => {
    const child = spawn(PYTHON, args, { cwd: ROOT, env: { ...process.env, ...env } })
    let out = ''
    child.stdout.on('data', d => { out += d })
    child.stderr.on('data', d => { out += d })
    child.on('close', code => resolve({ ok: code === 0, out: out.trim() }))
    child.on('error', error => resolve({ ok: false, out: String(error) }))
  })
}
const lastLine = (out: string) => out.split('\n').filter(l => l.trim() && !l.startsWith('{')).pop()?.replace(/^mako-capacity: /, '') ?? ''

function readSnapshot(): Snapshot {
  try { return JSON.parse(readFileSync(SNAPSHOT, 'utf8')) } catch { return { accounts: [] } }
}
function readSettings(): Record<string, string> {
  try { return JSON.parse(readFileSync(path.join(HOME, 'settings.json'), 'utf8')) } catch { return {} }
}

// No names or emails, for screen sharing: every view then leaves the name out.
const masked = (accounts: Account[]): Account[] => accounts.map(a => ({ ...a, title: '', email: '' }))

// Long names and emails end in an ellipsis instead of widening the card.
const ONE_LINE = { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }

// ---- Dock ------------------------------------------------------------------

function DockCell({ account, active, onHover, onOpen }: { account: Account; active: boolean; onHover?: () => void; onOpen?: () => void }) {
  return (
    <div onMouseEnter={onHover} onClick={onOpen ?? onHover}
      style={{ width: 56, paddingTop: 5, paddingBottom: 4, borderRadius: 12, alignItems: 'center', display: 'flex', flexDirection: 'column', gap: 2, cursor: 'pointer',
               backgroundColor: active ? '#ffffff12' : undefined, hover: { backgroundColor: '#ffffff12' } }}>
      <Ring account={account} size={36} />
      {account.provider === 'Cursor'
        ? account.windows.slice(0, 3).map(w => (
            <div key={w.label} style={{ display: 'flex', width: 56, justifyContent: 'space-between', gap: 3 }}>
              <Text size={9} color={C.muted}>{w.label.split(' ')[0].replace('Cursor', 'Models')}</Text>
              <Text size={9} color={w.used >= 70 ? C.yellow : C.green} weight={600}>{`${Math.round(w.used)}%`}</Text>
            </div>))
        : <>
            <Text size={12} weight={600} color={signal(account)}>{pct(account)}</Text>
            {account.title ? <Text size={9.5} color={C.muted} style={{ maxWidth: 54, whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{account.title}</Text> : null}
          </>}
    </div>
  )
}

function Bar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ height: 5, borderRadius: 3, backgroundColor: '#ffffff17', overflow: 'hidden', width: '100%' }}>
      <div style={{ height: 5, borderRadius: 3, width: `${Math.min(100, Math.max(0, value))}%`, backgroundColor: color }} />
    </div>
  )
}

// The card from the dock's hover bubble and the All accounts grid.
function Card({ account, all, onAction, confirm }: {
  account: Account; all: boolean; confirm?: boolean
  onAction?: (action: 'hide' | 'delete' | 'confirm' | 'cancel') => void
}) {
  const usage = account.localUsage ?? undefined
  const windows = all || account.provider === 'Cursor' ? account.windows : account.windows.slice(0, 2)
  return (
    <div style={{ backgroundColor: C.card, borderRadius: 18, borderWidth: 1, borderColor: '#ffffff12', padding: 16, display: 'flex', flexDirection: 'column', gap: 10,
                  minWidth: 0, flexShrink: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text size={10} weight={600} color={PROVIDER[account.provider]}>{account.provider.toUpperCase()}</Text>
        {onAction && !confirm && (
          <div style={{ display: 'flex', gap: 6 }}>
            <SmallButton label="Hide" onClick={() => onAction('hide')} />
            {account.proxyRef && <SmallButton label="Delete…" onClick={() => onAction('confirm')} />}
          </div>)}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Ring account={account} size={40} />
        <Text size={15} weight={600} style={{ ...ONE_LINE, flexGrow: 1, flexShrink: 1, minWidth: 0 }}>{account.title}</Text>
        <Text size={25} weight={600} color={signal(account)} style={{ flexShrink: 0 }}>{pct(account)}</Text>
      </div>
      {account.email ? <Text size={11} color={C.muted} style={ONE_LINE}>{account.email}</Text> : null}
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Text size={12}>{account.provider === 'Claude' || !account.plan ? account.provider : account.plan}</Text>
        <Text size={12} color={signal(account)}>{stateLabel(account)}</Text>
      </div>
      {windows.length === 0 && <Text size={12} color={C.muted}>{account.message || 'Capacity unknown'}</Text>}
      {windows.map(w => (
        <div key={w.label} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <Text size={12} style={{ ...ONE_LINE, flexShrink: 1, minWidth: 0 }}>{w.label}</Text>
            <Text size={12} style={{ flexShrink: 0 }}>{`${Math.round(w.used)}% used`}</Text>
          </div>
          <Bar value={w.used} color={w.used >= 100 ? C.red : PROVIDER[account.provider]} />
          <Text size={10} color={C.muted}>{w.detail ?? resetIn(w.resetAt)}</Text>
        </div>))}
      <div style={{ height: 1, backgroundColor: '#ffffff14' }} />
      <Text size={11} weight={600}>{`Today · local ${account.provider === 'Cursor' ? 'Cursor CLI' : account.provider} usage`}</Text>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}><Text size={12}>Tokens</Text><Text size={12}>{count(usage?.tokens)}</Text></div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <Text size={12} style={{ ...ONE_LINE, flexShrink: 1, minWidth: 0 }}>API-equivalent cost</Text><Text size={12} style={{ flexShrink: 0 }}>{usage?.costUsd == null ? '—' : `$${usage.costUsd.toFixed(2)}`}</Text>
      </div>
      <Text size={10} color={C.muted}>CodeBurn · all local accounts · not your bill</Text>
      {confirm && onAction && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 4 }}>
          <Text size={12} color={C.red}>{`Delete ${account.email || account.title || 'this account'} from the ${account.provider} proxy? You cannot undo this.`}</Text>
          <div style={{ display: 'flex', gap: 8 }}>
            <SmallButton label="Delete" danger onClick={() => onAction('delete')} />
            <SmallButton label="Cancel" onClick={() => onAction('cancel')} />
          </div>
        </div>)}
      <Text size={10} color={C.muted}>{account.source}</Text>
    </div>
  )
}

function SmallButton({ label, onClick, danger, primary }: { label: string; onClick: () => void; danger?: boolean; primary?: boolean }) {
  return (
    // Button: a Tab stop that Enter and Space press, so it also works where mouse input does not reach.
    <Button onClick={onClick} style={{
      paddingTop: 4, paddingBottom: 4, paddingLeft: 10, paddingRight: 10, borderRadius: 7, cursor: 'pointer',
      backgroundColor: danger ? '#ff453a' : primary ? C.blue : '#ffffff14', hover: { backgroundColor: danger ? '#ff6359' : primary ? '#3a9bff' : '#ffffff24' },
      focusVisible: { outlineWidth: 2, outlineColor: '#64a8ff', outlineOffset: 2 },
    }}>
      <Text size={12} weight={600} color={danger || primary ? '#ffffff' : C.text}>{label}</Text>
    </Button>
  )
}

// ---- Compact layout: the widget fills a narrow window or terminal pane --------

// Material icons (Apache-2.0), as one-colour masks.
const ICONS = {
  grid: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M3 3h8v8H3zm10 0h8v8h-8zM3 13h8v8H3zm10 0h8v8h-8z"/></svg>',
  gear: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.48.48 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6a3.6 3.6 0 1 1 0-7.2 3.6 3.6 0 0 1 0 7.2z"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M17.65 6.35A7.96 7.96 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>',
  pin: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z"/></svg>',
  eye: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>',
  eyeOff: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46A11.8 11.8 0 0 0 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78 3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/></svg>',
  back: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z"/></svg>',
}

function IconButton({ icon, label, onClick, active, small }: { icon: keyof typeof ICONS; label: string; onClick: () => void; active?: boolean; small?: boolean }) {
  return (
    <Button onClick={onClick} aria-label={label} style={{
      padding: small ? 6 : 8, borderRadius: 10, cursor: 'pointer', backgroundColor: active ? '#ffffff1f' : undefined,
      hover: { backgroundColor: '#ffffff14' }, focusVisible: { outlineWidth: 2, outlineColor: '#64a8ff', outlineOffset: 2 },
    }}>
      <svg source={ICONS[icon]} style={{ width: 18, height: 18, color: C.text }} />
    </Button>
  )
}

// One account per row, like the Herdr widget's middle layout. A tap opens its card.
function WidgetRow({ account, onOpen }: { account: Account; onOpen: () => void }) {
  return (
    <Button onClick={onOpen} style={{
      display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0, paddingTop: 6, paddingBottom: 6, paddingLeft: 8, paddingRight: 10,
      borderRadius: 12, cursor: 'pointer', hover: { backgroundColor: '#ffffff12' }, focusVisible: { outlineWidth: 2, outlineColor: '#64a8ff' },
    }}>
      <Ring account={account} size={36} />
      <div style={{ display: 'flex', flexDirection: 'column', flexGrow: 1, flexShrink: 1, minWidth: 0 }}>
        {account.title ? <Text size={13} weight={600} style={ONE_LINE}>{account.title}</Text> : null}
        <Text size={11} color={C.muted} style={ONE_LINE}>{`${account.provider} · ${stateLabel(account)}`}</Text>
      </div>
      <Text size={15} weight={600} color={signal(account)} style={{ flexShrink: 0 }}>{pct(account)}</Text>
    </Button>
  )
}

// ---- App -------------------------------------------------------------------

type View = 'dock' | 'accounts' | 'settings'
const startView = (process.argv.find(a => a.startsWith('--view=')) ?? '').slice(7) as View

function App() {
  const [snapshot, setSnapshot] = useState<Snapshot>(readSnapshot)
  const [view, setView] = useState<View>(['dock', 'accounts', 'settings'].includes(startView) ? startView : 'dock')
  const [hovered, setHovered] = useState(0)
  const [confirm, setConfirm] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [proxyUrl, setProxyUrl] = useState(readSettings().PROXY_URL ?? '')
  // The saved key never goes back into a visible field: GPUIX inputs have no password mode.
  const [proxyKey, setProxyKey] = useState('')
  const [showNames, setShowNames] = useState(() => !existsSync(NAMES_FLAG))
  const [pinned, setPinned] = useState(() => !!PIN_STATE && existsSync(PIN_STATE))
  const { width } = useWindowSize()
  const columns = Math.max(1, Math.floor((width - 32 + 14) / 264))

  async function collect(extra: string[] = []) {
    setBusy(true)
    const result = await run([path.join(ROOT, 'collector.py'), '--skip-usage', ...extra])
    setSnapshot(readSnapshot())
    setBusy(false)
    if (!result.ok) setMessage(lastLine(result.out) || 'The collector failed; previous readings stay visible.')
    return result.ok
  }
  useEffect(() => {
    if (!process.env.MAKO_CAPACITY_SNAPSHOT) collect()
    const reload = setInterval(() => {
      setSnapshot(readSnapshot())
      setShowNames(!existsSync(NAMES_FLAG))
      setPinned(!!PIN_STATE && existsSync(PIN_STATE))
    }, 10_000)
    const poll = process.env.MAKO_CAPACITY_SNAPSHOT ? undefined : setInterval(() => collect(), 60_000)
    return () => { clearInterval(reload); if (poll) clearInterval(poll) }
  }, [])

  const listed = snapshot.accounts.filter(a => !snapshot.hidden?.[a.id])
  const accounts = showNames ? listed : masked(listed)
  const hidden = Object.entries(snapshot.hidden ?? {}).sort((a, b) => a[1].localeCompare(b[1]))
    .map(([id, label], i) => [id, showNames ? label : `Hidden account ${i + 1}`])

  function toggleNames() {
    try { if (showNames) writeFileSync(NAMES_FLAG, ''); else unlinkSync(NAMES_FLAG) } catch {}
    setShowNames(!existsSync(NAMES_FLAG))
  }
  async function togglePin() {
    // This pane is the focused one for open.py, so pinning keeps it and unpinning spares it.
    const result = await run([path.join(ROOT, 'herdr-plugin/open.py'), 'toggle', 'app'], { HERDR_PLUGIN_CONTEXT_JSON: '{}' })
    setPinned(!!PIN_STATE && existsSync(PIN_STATE))
    if (!result.ok) setMessage(lastLine(result.out) || 'Pinning failed.')
  }
  const namesButton = <SmallButton label={showNames ? 'Hide account names' : 'Show account names'} onClick={toggleNames} />
  const current = accounts[Math.min(hovered, accounts.length - 1)]

  async function act(account: Account, action: 'hide' | 'delete' | 'confirm' | 'cancel') {
    if (action === 'confirm') return setConfirm(account.id)
    setConfirm(null)
    if (action === 'cancel') return
    setMessage('')
    if (await collect([`--${action}`, account.id])) setMessage(action === 'hide' ? `Hid ${account.title || 'the account'}.` : `Deleted ${account.email || 'the account'} from the proxy.`)
  }

  async function saveProxy(local: boolean) {
    setBusy(true)
    const key = proxyKey.trim() || readSettings().PROXY_MANAGEMENT_KEY || ''
    const result = await run([path.join(ROOT, 'scripts/capacity.py'), 'proxy', local || !proxyUrl.trim() ? 'local' : proxyUrl.trim(), '--key', key])
    setBusy(false)
    if (local) { setProxyUrl(''); setProxyKey('') }
    setMessage(lastLine(result.out) || (result.ok ? 'Saved.' : 'Saving failed.'))
    if (result.ok) collect(['--refresh'])
  }

  const tab = (id: View, label: string) => (
    <Button key={id} onClick={() => setView(id)} style={{
      paddingTop: 6, paddingBottom: 6, paddingLeft: 12, paddingRight: 12, borderRadius: 8, cursor: 'pointer',
      backgroundColor: view === id ? '#ffffff1f' : undefined, hover: { backgroundColor: '#ffffff14' },
      focusVisible: { outlineWidth: 2, outlineColor: '#64a8ff', outlineOffset: 2 },
    }}>
      <Text size={13} weight={view === id ? 600 : 400} color={view === id ? C.text : C.muted}>{label}</Text>
    </Button>
  )

  // Narrow windows and terminal panes get the widget itself, full screen, like the Herdr widget:
  // under 200 px the dock column of rings, under 480 px a row per account. Icons reach the other views.
  const compact = width > 0 && width < 480
  const tiny = width > 0 && width < 200
  const [opened, setOpened] = useState<string | null>(null)
  const openedAccount = accounts.find(a => a.id === opened)
  if (compact) {
    const back = (title: string, onBack: () => void) => (
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, paddingTop: 6, paddingBottom: 6, paddingLeft: 6, paddingRight: 10 }}>
        <IconButton icon="back" label="Back" onClick={onBack} />
        <Text size={14} weight={600} style={ONE_LINE}>{title}</Text>
      </div>
    )
    let body
    if (view === 'dock' && openedAccount) {
      body = <>{back(openedAccount.title || openedAccount.provider, () => setOpened(null))}
        <div style={{ flexGrow: 1, overflowY: 'scroll', paddingLeft: 10, paddingRight: 10, paddingBottom: 10 }}>
          <Card account={openedAccount} all confirm={confirm === openedAccount.id} onAction={action => act(openedAccount, action)} />
        </div></>
    } else if (view === 'dock') {
      body = <div style={{ flexGrow: 1, overflowY: 'scroll', paddingTop: 8, paddingLeft: tiny ? 0 : 6, paddingRight: tiny ? 0 : 6,
                           display: 'flex', flexDirection: 'column', alignItems: tiny ? 'center' : 'stretch', gap: tiny ? 2 : 0 }}>
        {accounts.length === 0 && <Text size={12} color={C.muted} style={{ padding: 10 }}>Discovering your accounts…</Text>}
        {accounts.map((a, i) => tiny
          ? <DockCell key={a.id} account={a} active={false} onOpen={() => setOpened(a.id)} />
          : <WidgetRow key={a.id} account={a} onOpen={() => setOpened(a.id)} />)}
      </div>
    } else if (view === 'accounts') {
      body = <>{back('All accounts', () => setView('dock'))}
        <div style={{ flexGrow: 1, overflowY: 'scroll', paddingLeft: 10, paddingRight: 10, paddingBottom: 10, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {accounts.map(a => <Card key={a.id} account={a} all={false} confirm={confirm === a.id} onAction={action => act(a, action)} />)}
        </div></>
    } else {
      body = <>{back('Settings', () => setView('dock'))}
        <div style={{ flexGrow: 1, overflowY: 'scroll', paddingLeft: 12, paddingRight: 12, paddingBottom: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <Text size={12} color={C.muted}>Proxy address, empty for the local Docker proxy.</Text>
          <input value={proxyUrl} placeholder="https://server:8317" onChange={e => setProxyUrl(String(e.value ?? ''))}
            style={{ backgroundColor: '#0a0a0a', borderRadius: 8, padding: 8, color: C.text, fontSize: 13, borderWidth: 1, borderColor: '#ffffff1f' }} />
          <input value={proxyKey} placeholder={readSettings().PROXY_MANAGEMENT_KEY ? 'Key (saved; type to replace)' : 'Management key'}
            onChange={e => setProxyKey(String(e.value ?? ''))}
            style={{ backgroundColor: '#0a0a0a', borderRadius: 8, padding: 8, color: C.text, fontSize: 13, borderWidth: 1, borderColor: '#ffffff1f' }} />
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <SmallButton label="Save and test" primary onClick={() => !busy && saveProxy(false)} />
            <SmallButton label="Use local" onClick={() => !busy && saveProxy(true)} />
          </div>
          <div style={{ display: 'flex' }}>{namesButton}</div>
          {hidden.map(([id, label]) => (
            <div key={id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Text size={12} style={{ ...ONE_LINE, flexGrow: 1, flexShrink: 1, minWidth: 0 }}>{label}</Text>
              <SmallButton label="Restore" onClick={async () => { if (await collect(['--restore', id])) setMessage('Restored.') }} />
            </div>))}
        </div></>
    }
    return (
      // In a macOS window the traffic lights sit over the top edge, so the widget starts below them.
      <div style={{ width: '100%', height: '100%', backgroundColor: C.dock, display: 'flex', flexDirection: 'column',
                    paddingTop: process.platform === 'darwin' && !isTerminal() ? 34 : 0 }}>
        {snapshot.warning ? <Text size={11} color={C.red} style={{ padding: 8 }}>{snapshot.warning}</Text> : null}
        {message && view !== 'dock' ? <Text size={11} color={C.muted} style={{ paddingLeft: 12, paddingRight: 12 }}>{message}</Text> : null}
        {body}
        {/* The dock's own tool row: all accounts, settings, refresh. */}
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: tiny ? 0 : 6, paddingTop: 4, paddingBottom: 8, borderTopWidth: 1, borderColor: '#ffffff14' }}>
          <IconButton small={tiny} icon="grid" label="All accounts" active={view === 'accounts'} onClick={() => { setOpened(null); setView(view === 'accounts' ? 'dock' : 'accounts') }} />
          <IconButton small={tiny} icon="gear" label="Settings" active={view === 'settings'} onClick={() => { setOpened(null); setView(view === 'settings' ? 'dock' : 'settings') }} />
          {!tiny && <IconButton icon="refresh" label="Refresh" onClick={() => !busy && collect(['--refresh'])} />}
          <IconButton small={tiny} icon={showNames ? 'eye' : 'eyeOff'} label={showNames ? 'Hide account names' : 'Show account names'} onClick={toggleNames} />
          {PIN_STATE && <IconButton small={tiny} icon="pin" label={pinned ? 'Unpin' : 'Pin to every tab'} active={pinned} onClick={togglePin} />}
        </div>
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height: '100%', backgroundColor: C.bg, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingTop: 10, paddingBottom: 10, paddingRight: 16,
                    paddingLeft: process.platform === 'darwin' && !isTerminal() ? 86 : 16 }}>
        {tab('dock', 'Dock')}{tab('accounts', 'All accounts')}{tab('settings', 'Settings')}
        <div style={{ flexGrow: 1 }} />
        {message ? <Text size={12} color={C.muted} style={{ maxWidth: 420, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{message}</Text> : null}
        {PIN_STATE && <SmallButton label={pinned ? 'Unpin' : 'Pin to every tab'} onClick={togglePin} />}
        <SmallButton label={busy ? 'Refreshing…' : 'Refresh'} onClick={() => !busy && collect(['--refresh'])} />
      </div>
      {snapshot.warning ? <div style={{ paddingLeft: 16, paddingBottom: 8 }}><Text size={12} color={C.red}>{snapshot.warning}</Text></div> : null}

      {view === 'dock' && (
        <div style={{ display: 'flex', flexGrow: 1, gap: 20, padding: 16, justifyContent: 'flex-end', overflow: 'hidden' }}>
          {current
            ? <div style={{ width: 340, alignSelf: 'flex-start' }}><Card account={current} all={false} /></div>
            : <Text color={C.muted}>Discovering your accounts…</Text>}
          <div style={{ width: 68, backgroundColor: C.dock, borderRadius: 22, borderWidth: 1, borderColor: '#ffffff29', paddingTop: 14, paddingBottom: 14,
                        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, overflowY: 'scroll' }}>
            {accounts.map((a, i) => <DockCell key={a.id} account={a} active={i === hovered} onHover={() => setHovered(i)} />)}
          </div>
        </div>)}

      {view === 'accounts' && (
        <div style={{ flexGrow: 1, overflowY: 'scroll', paddingLeft: 16, paddingRight: 16, paddingBottom: 16 }}>
          <Text size={26} weight={600} style={{ paddingTop: 6 }}>Your accounts. One view.</Text>
          <Text size={13} color={C.muted} style={{ paddingTop: 4, paddingBottom: 14 }}>
            {`${accounts.length} accounts across Claude, Codex and Cursor · percentages show capacity used`}
          </Text>
          <div style={{ display: 'grid', gridTemplateColumns: columns, gap: 14 }}>
            {accounts.map(a => <Card key={a.id} account={a} all={false} confirm={confirm === a.id} onAction={action => act(a, action)} />)}
          </div>
        </div>)}

      {view === 'settings' && (
        <div style={{ flexGrow: 1, overflowY: 'scroll', padding: 16, display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 560 }}>
          <Text size={17} weight={600}>Proxy server</Text>
          <Text size={12} color={C.muted}>Leave the address empty to use the local Docker proxy. Saving checks that the server answers.</Text>
          <input value={proxyUrl} placeholder="https://server:8317" onChange={e => setProxyUrl(String(e.value ?? ''))}
            style={{ backgroundColor: '#0a0a0a', borderRadius: 8, padding: 8, color: C.text, fontSize: 13, borderWidth: 1, borderColor: '#ffffff1f' }} />
          <input value={proxyKey} placeholder={readSettings().PROXY_MANAGEMENT_KEY ? 'Management key (saved; type to replace)' : 'Management key'}
            onChange={e => setProxyKey(String(e.value ?? ''))}
            style={{ backgroundColor: '#0a0a0a', borderRadius: 8, padding: 8, color: C.text, fontSize: 13, borderWidth: 1, borderColor: '#ffffff1f' }} />
          <div style={{ display: 'flex', gap: 8 }}>
            <SmallButton label="Save and test" primary onClick={() => !busy && saveProxy(false)} />
            <SmallButton label="Use local proxy" onClick={() => !busy && saveProxy(true)} />
          </div>
          <div style={{ height: 1, backgroundColor: '#ffffff14', marginTop: 8, marginBottom: 8 }} />
          <Text size={17} weight={600}>Privacy</Text>
          <Text size={12} color={C.muted}>Hiding names removes account names and emails, here and in the Herdr widget.</Text>
          <div style={{ display: 'flex' }}>{namesButton}</div>
          <div style={{ height: 1, backgroundColor: '#ffffff14', marginTop: 8, marginBottom: 8 }} />
          <Text size={17} weight={600}>Hidden accounts</Text>
          {hidden.length === 0 && <Text size={12} color={C.muted}>No hidden accounts.</Text>}
          {hidden.map(([id, label]) => (
            <div key={id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Text size={13} style={{ flexGrow: 1 }}>{label}</Text>
              <SmallButton label="Restore" onClick={async () => { if (await collect(['--restore', id])) setMessage('Restored.') }} />
            </div>))}
          <Text size={11} color={C.muted} style={{ paddingTop: 12 }}>Dock size, edge and icon shape are set in the desktop dock.</Text>
        </div>)}
    </div>
  )
}

// --size=WxH opens a smaller window, for example a narrow widget column: --size=180x760
const [W, H] = ((process.argv.find(a => a.startsWith('--size=')) ?? '').slice(7).split('x').map(Number))
render(<App />, { title: 'Mako Capacity', width: W || 1120, height: H || 780, titlebarTransparent: true, trafficLightX: 16, trafficLightY: 17 })
