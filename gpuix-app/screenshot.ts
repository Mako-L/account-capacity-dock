// Drive the app with demo data and write one PNG per view: bun screenshot.ts [snapshot.json]
import { mkdirSync } from 'node:fs'
import { launch } from '@gpuix/react/automation'

const snapshot = process.argv[2] ?? '/tmp/demo/snapshot.json'
mkdirSync('screenshots', { recursive: true })
for (const view of (process.argv[3] ?? 'dock,accounts,settings').split(',')) {
  const app = await launch({
    command: 'bun', args: ['app.tsx', `--view=${view}`],
    env: { GPUIX_BACKGROUND: '1', MAKO_CAPACITY_SNAPSHOT: snapshot, MAKO_CAPACITY_HOME: '/tmp/demo/home/.mako-capacity' },
  })
  await app.getByText('All accounts').waitFor({ timeoutMs: 60_000 })
  if (view === 'dock') await app.getByText('81%').hover()
  await new Promise(r => setTimeout(r, 400))
  await app.clock.pause()
  await app.screenshot({ path: `screenshots/${view}.png` })
  await app.close()
  console.log('wrote', view)
}
