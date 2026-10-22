// Drive the app with demo data and write one PNG per view: bun screenshot.ts [snapshot.json]
import { mkdirSync } from 'node:fs'
import { launch } from '@gpuix/react/automation'

const snapshot = process.argv[2] ?? '/tmp/demo/snapshot.json'
mkdirSync('screenshots', { recursive: true })
const size = process.argv[4] ?? ''
for (const view of (process.argv[3] ?? 'dock,accounts,settings').split(',')) {
  const app = await launch({
    command: 'bun', args: ['app.tsx', `--view=${view}`, ...(size ? [`--size=${size}`] : [])],
    env: { GPUIX_BACKGROUND: '1', MAKO_CAPACITY_SNAPSHOT: snapshot, MAKO_CAPACITY_HOME: '/tmp/demo/home/.mako-capacity' },
  })
  await app.getByText(size ? '%' : 'All accounts').waitFor({ timeoutMs: 60_000 }).catch(() => {})
  await new Promise(r => setTimeout(r, 1500))
  if (view === 'dock' && !size) await app.getByText('81%').hover()
  await new Promise(r => setTimeout(r, 400))
  await app.clock.pause()
  await app.screenshot({ path: `screenshots/${view}${size ? '-' + size : ''}.png` })
  await app.close()
  console.log('wrote', view)
}
