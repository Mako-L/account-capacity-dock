// Shared pieces of the GPUIX app: paths, colours, text, buttons and the ring arc.
import { Button } from '@gpuix/react'
import { useEffect, useState, type ReactNode } from 'react'
import { spawn } from 'node:child_process'
import { homedir } from 'node:os'
import path from 'node:path'

export const ROOT = path.resolve(import.meta.dir, '..')
export const HOME = process.env.MAKO_CAPACITY_HOME ?? path.join(homedir(), '.mako-capacity')
export const CACHE = process.platform === 'darwin'
  ? path.join(homedir(), 'Library/Application Support/Mako Capacity')
  : process.platform === 'win32'
    ? path.join(process.env.LOCALAPPDATA ?? path.join(homedir(), 'AppData/Local'), 'mako-capacity')
    : path.join(process.env.XDG_CACHE_HOME ?? path.join(homedir(), '.cache'), 'mako-capacity')
export const SNAPSHOT = process.env.MAKO_CAPACITY_SNAPSHOT ?? path.join(CACHE, 'snapshot.json')
export const PYTHON = process.platform === 'win32' ? 'python' : 'python3'

export const C = {
  bg: '#111111', dock: '#050505', card: '#1c1c1c', line: '#2c2c2e', text: '#f2f2f4', muted: '#9a9aa2',
  green: '#30d158', yellow: '#ffd60a', orange: '#ff9f0a', red: '#ff453a', blue: '#0a84ff',
}

export const TRACK = '<svg viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg"><circle cx="23" cy="23" r="19" fill="none" stroke="#000" stroke-width="4.5"/></svg>'

// A circular ring that starts at the top and runs clockwise, drawn as an SVG arc.
export function arcSvg(value: number | null) {
  const r = 19, c = 23, f = Math.min(Math.max(value ?? 0, 0), 99.99) / 100
  if (f <= 0) return null
  const a = f * 2 * Math.PI, x = c + r * Math.sin(a), y = c - r * Math.cos(a)
  return `<svg viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg"><path d="M${c} ${c - r} A${r} ${r} 0 ${f > 0.5 ? 1 : 0} 1 ${x.toFixed(2)} ${y.toFixed(2)}" fill="none" stroke="#000" stroke-width="4.5" stroke-linecap="round"/></svg>`
}

export function Text({ children, size = 13, color = C.text, weight, style }: {
  children: React.ReactNode; size?: number; color?: string; weight?: number; style?: Record<string, unknown>
}) {
  return <text style={{ fontSize: size, color, fontWeight: weight, ...style }}>{children}</text>
}

export function run(args: string[], env: Record<string, string> = {}): Promise<{ ok: boolean; out: string }> {
  return new Promise(resolve => {
    const child = spawn(PYTHON, args, { cwd: ROOT, env: { ...process.env, ...env } })
    let out = ''
    child.stdout.on('data', d => { out += d })
    child.stderr.on('data', d => { out += d })
    child.on('close', code => resolve({ ok: code === 0, out: out.trim() }))
    child.on('error', error => resolve({ ok: false, out: String(error) }))
  })
}
export const lastLine = (out: string) => out.split('\n').filter(l => l.trim() && !l.startsWith('{')).pop()?.replace(/^mako-capacity: /, '') ?? ''

// Long names and emails end in an ellipsis instead of widening the card.
export const ONE_LINE = { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }

export function Bar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ height: 5, borderRadius: 3, backgroundColor: '#ffffff17', overflow: 'hidden', width: '100%' }}>
      <div style={{ height: 5, borderRadius: 3, width: `${Math.min(100, Math.max(0, value))}%`, backgroundColor: color }} />
    </div>
  )
}

export function SmallButton({ label, onClick, danger, primary }: { label: string; onClick: () => void; danger?: boolean; primary?: boolean }) {
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

// Material icons (Apache-2.0), as one-colour masks.
export const ICONS = {
  grid: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M3 3h8v8H3zm10 0h8v8h-8zM3 13h8v8H3zm10 0h8v8h-8z"/></svg>',
  gear: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.48.48 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6a3.6 3.6 0 1 1 0-7.2 3.6 3.6 0 0 1 0 7.2z"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M17.65 6.35A7.96 7.96 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>',
  pin: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z"/></svg>',
  eye: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>',
  eyeOff: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46A11.8 11.8 0 0 0 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78 3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/></svg>',
  agents: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M20 9V7c0-1.1-.9-2-2-2h-3c0-1.66-1.34-3-3-3S9 3.34 9 5H6c-1.1 0-2 .9-2 2v2c-1.66 0-3 1.34-3 3s1.34 3 3 3v4c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-4c1.66 0 3-1.34 3-3s-1.34-3-3-3zM7.5 11.5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5S9.83 13 9 13s-1.5-.67-1.5-1.5zM16 17H8v-2h8v2zm-1-4c-.83 0-1.5-.67-1.5-1.5S14.17 10 15 10s1.5.67 1.5 1.5S15.83 13 15 13z"/></svg>',
  back: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#000" d="M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z"/></svg>',
}

export function IconButton({ icon, label, onClick, active, small }: { icon: keyof typeof ICONS; label: string; onClick: () => void; active?: boolean; small?: boolean }) {
  return (
    <Button onClick={onClick} aria-label={label} style={{
      padding: small ? 6 : 8, borderRadius: 10, cursor: 'pointer', backgroundColor: active ? '#ffffff1f' : undefined,
      hover: { backgroundColor: '#ffffff14' }, focusVisible: { outlineWidth: 2, outlineColor: '#64a8ff', outlineOffset: 2 },
    }}>
      <svg source={ICONS[icon]} style={{ width: 18, height: 18, color: C.text }} />
    </Button>
  )
}

// Styles that lay out the scrolled content; the rest size the scroller itself.
const CONTENT_KEYS = ['display', 'flexDirection', 'gap', 'alignItems', 'justifyContent', 'padding', 'paddingTop', 'paddingBottom', 'paddingLeft', 'paddingRight']
const FADE = (angle: number) => ({ type: 'linear-gradient' as const, angle, stops: [{ color: '#000000a6', position: 0 }, { color: '#00000000', position: 1 }] as [any, any] })

// A vertical scroller that shades its top edge once content has moved up, and its bottom edge while more is below.
// shadeBottom={false} leaves the bottom edge to the caller, which reports it through onBelow and draws one shade across columns.
export function Scroll({ style, children, shadeBottom = true, onBelow }: { style: Record<string, any>; children: ReactNode; shadeBottom?: boolean; onBelow?: (below: boolean) => void }) {
  const [box, setBox] = useState(0)
  const [content, setContent] = useState(0)
  const [offset, setOffset] = useState(0)
  const outer: Record<string, any> = {}, inner: Record<string, any> = {}
  for (const [key, value] of Object.entries(style)) {
    if (key === 'overflowY') continue
    if (CONTENT_KEYS.includes(key)) inner[key] = value
    else outer[key] = value
  }
  const above = -offset > 1, below = content + offset - box > 1
  useEffect(() => onBelow?.(below), [below])
  const shade = (edge: 'top' | 'bottom') => (
    <div style={{ position: 'absolute', left: 0, right: 0, [edge]: 0, height: Math.min(28, box / 2), pointerEvents: 'none',
                  background: FADE(edge === 'top' ? 180 : 0) }} />)
  return (
    <div style={{ minHeight: 0, ...outer, position: 'relative', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flexGrow: 1, flexShrink: 1, minHeight: 0, overflowY: 'scroll' }}
           onLayout={e => setBox(e.height ?? 0)} onScrollChange={e => setOffset(e.scrollY ?? 0)}>
        <div style={{ ...inner, flexShrink: 0 }} onLayout={e => setContent(e.height ?? 0)}>{children}</div>
      </div>
      {above && shade('top')}
      {below && shadeBottom && shade('bottom')}
    </div>
  )
}

export function BottomShade() {
  return <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 28, pointerEvents: 'none', background: FADE(0) }} />
}
