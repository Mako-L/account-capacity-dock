// Mako Capacity on GPUIX: the dock, All accounts and Settings in one React tree.
// The same tree runs in a native window (`bun app.tsx`) or inside the terminal
// (`GPUIX_TERMINAL=1 bun app.tsx`, Ghostty or kitty, also over SSH).
// Data and actions go through collector.py and scripts/capacity.py, like the other renderers.
import { useEffect, useState } from 'react'
import { render, isTerminal, useWindowSize } from '@gpuix/react'
import { spawn } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
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

function run(args: string[]): Promise<{ ok: boolean; out: string }> {
  return new Promise(resolve => {
    const child = spawn(PYTHON, args, { cwd: ROOT, env: process.env })
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

// ---- Dock ------------------------------------------------------------------

function DockCell({ account, active, onHover }: { account: Account; active: boolean; onHover: () => void }) {
  return (
    <div onMouseEnter={onHover} onClick={onHover}
      style={{ width: 56, paddingTop: 5, paddingBottom: 4, borderRadius: 12, alignItems: 'center', display: 'flex', flexDirection: 'column', gap: 2, cursor: 'pointer',
               backgroundColor: active ? '#ffffff12' : undefined, hover: { backgroundColor: '#ffffff12' } }}>
      <Ring account={account} size={36} />
      {account.provider === 'Cursor'
        ? account.windows.slice(0, 3).map(w => (
            <div key={w.label} style={{ display: 'flex', width: 52, justifyContent: 'space-between' }}>
              <Text size={9} color={C.muted}>{w.label.split(' ')[0].replace('Cursor', 'Models')}</Text>
              <Text size={9} color={w.used >= 70 ? C.yellow : C.green} weight={600}>{`${Math.round(w.used)}%`}</Text>
            </div>))
        : <>
            <Text size={12} weight={600} color={signal(account)}>{pct(account)}</Text>
            <Text size={9.5} color={C.muted} style={{ maxWidth: 54, whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{account.title}</Text>
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
    <div style={{ backgroundColor: C.card, borderRadius: 18, borderWidth: 1, borderColor: '#ffffff12', padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
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
        <Text size={15} weight={600} style={{ flexGrow: 1 }}>{account.title}</Text>
        <Text size={25} weight={600} color={signal(account)}>{pct(account)}</Text>
      </div>
      <Text size={11} color={C.muted}>{account.email}</Text>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Text size={12}>{account.provider === 'Claude' || !account.plan ? account.provider : account.plan}</Text>
        <Text size={12} color={signal(account)}>{stateLabel(account)}</Text>
      </div>
      {windows.length === 0 && <Text size={12} color={C.muted}>{account.message || 'Capacity unknown'}</Text>}
      {windows.map(w => (
        <div key={w.label} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Text size={12}>{w.label}</Text><Text size={12}>{`${Math.round(w.used)}% used`}</Text>
          </div>
          <Bar value={w.used} color={w.used >= 100 ? C.red : PROVIDER[account.provider]} />
          <Text size={10} color={C.muted}>{w.detail ?? resetIn(w.resetAt)}</Text>
        </div>))}
      <div style={{ height: 1, backgroundColor: '#ffffff14' }} />
      <Text size={11} weight={600}>{`Today · local ${account.provider === 'Cursor' ? 'Cursor CLI' : account.provider} usage`}</Text>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}><Text size={12}>Tokens</Text><Text size={12}>{count(usage?.tokens)}</Text></div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <Text size={12}>API-equivalent cost</Text><Text size={12}>{usage?.costUsd == null ? '—' : `$${usage.costUsd.toFixed(2)}`}</Text>
      </div>
      <Text size={10} color={C.muted}>CodeBurn · all local accounts · not your bill</Text>
      {confirm && onAction && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 4 }}>
          <Text size={12} color={C.red}>{`Delete ${account.email} from the ${account.provider} proxy? You cannot undo this.`}</Text>
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
    <div onClick={onClick} style={{
      paddingTop: 4, paddingBottom: 4, paddingLeft: 10, paddingRight: 10, borderRadius: 7, cursor: 'pointer',
      backgroundColor: danger ? '#ff453a' : primary ? C.blue : '#ffffff14', hover: { backgroundColor: danger ? '#ff6359' : primary ? '#3a9bff' : '#ffffff24' },
    }}>
      <Text size={12} weight={600} color={danger || primary ? '#ffffff' : C.text}>{label}</Text>
    </div>
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
    const reload = setInterval(() => setSnapshot(readSnapshot()), 10_000)
    const poll = process.env.MAKO_CAPACITY_SNAPSHOT ? undefined : setInterval(() => collect(), 60_000)
    return () => { clearInterval(reload); if (poll) clearInterval(poll) }
  }, [])

  const accounts = snapshot.accounts.filter(a => !snapshot.hidden?.[a.id])
  const hidden = Object.entries(snapshot.hidden ?? {}).sort((a, b) => a[1].localeCompare(b[1]))
  const current = accounts[Math.min(hovered, accounts.length - 1)]

  async function act(account: Account, action: 'hide' | 'delete' | 'confirm' | 'cancel') {
    if (action === 'confirm') return setConfirm(account.id)
    setConfirm(null)
    if (action === 'cancel') return
    setMessage('')
    if (await collect([`--${action}`, account.id])) setMessage(action === 'hide' ? `Hid ${account.title}.` : `Deleted ${account.email} from the proxy.`)
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
    <div key={id} onClick={() => setView(id)} style={{
      paddingTop: 6, paddingBottom: 6, paddingLeft: 12, paddingRight: 12, borderRadius: 8, cursor: 'pointer',
      backgroundColor: view === id ? '#ffffff1f' : undefined, hover: { backgroundColor: '#ffffff14' },
    }}>
      <Text size={13} weight={view === id ? 600 : 400} color={view === id ? C.text : C.muted}>{label}</Text>
    </div>
  )

  return (
    <div style={{ width: '100%', height: '100%', backgroundColor: C.bg, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingTop: 10, paddingBottom: 10, paddingRight: 16,
                    paddingLeft: process.platform === 'darwin' && !isTerminal() ? 86 : 16 }}>
        {tab('dock', 'Dock')}{tab('accounts', 'All accounts')}{tab('settings', 'Settings')}
        <div style={{ flexGrow: 1 }} />
        {message ? <Text size={12} color={C.muted} style={{ maxWidth: 420, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{message}</Text> : null}
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

render(<App />, { title: 'Mako Capacity', width: 1120, height: 780, titlebarTransparent: true, trafficLightX: 16, trafficLightY: 17 })
