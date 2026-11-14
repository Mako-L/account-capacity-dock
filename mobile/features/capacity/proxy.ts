import { HttpError, executeRequest } from '../../lib/request'
import { claudeWindows, codexWindows, planName } from './rules'
import type { CapacityAccount, CapacityWindow, ProxyConfig, Provider, Status } from './types'

type Json = Record<string, unknown>

type AuthFile = {
  auth_index?: string
  type?: string
  email?: string
  label?: string
  status?: string
  disabled?: boolean
  unavailable?: boolean
  id_token?: Json | null
}

type ApiCallResult = { status_code?: number; body?: unknown }

const USAGE: Record<Provider, { url: string; headers: Record<string, string> }> = {
  Claude: {
    url: 'https://api.anthropic.com/api/oauth/usage',
    headers: { Authorization: 'Bearer $TOKEN$', 'anthropic-beta': 'oauth-2025-04-20', Accept: 'application/json' },
  },
  Codex: {
    url: 'https://chatgpt.com/backend-api/wham/usage',
    headers: { Authorization: 'Bearer $TOKEN$', Accept: 'application/json' },
  },
}

const PROVIDERS: Record<string, Provider> = { claude: 'Claude', codex: 'Codex' }
const LOOPBACK = new Set(['127.0.0.1', 'localhost', '[::1]', '::1'])

// Same rule as scripts/capacity.py: http(s)://host[:port], plain http only on loopback.
export function normaliseUrl(input: string): string {
  const text = input.trim().replace(/\/+$/, '').replace(/\/management\.html$/, '')
  let parsed: URL
  try {
    parsed = new URL(text)
  } catch {
    throw new Error('Proxy URL must look like https://host:8317')
  }
  if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname) {
    throw new Error('Proxy URL must look like https://host:8317')
  }
  if (parsed.protocol === 'http:' && !LOOPBACK.has(parsed.hostname)) {
    throw new Error('Use https for a remote proxy; plain http is only allowed on this device.')
  }
  return `${parsed.protocol}//${parsed.host}`
}

async function management<T>(config: ProxyConfig, path: string, body?: unknown): Promise<T> {
  try {
    return await executeRequest<T>(`${config.baseUrl}/v0/management/${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { Authorization: `Bearer ${config.key}` },
      body,
      timeoutMs: 20000,
    })
  } catch (error) {
    if (error instanceof HttpError) {
      throw new Error(`Proxy refused ${path} (HTTP ${error.status}); check the management key.`)
    }
    throw new Error(`Proxy at ${config.baseUrl} is not reachable.`)
  }
}

function baseAccount(file: AuthFile, provider: Provider): CapacityAccount {
  const token = file.id_token ?? {}
  return {
    id: `${provider.toLowerCase()}-${file.auth_index ?? file.email ?? 'unknown'}`,
    provider,
    email: file.email || file.label || 'Unknown account',
    plan: planName(token.plan_type ?? token.chatgpt_plan_type),
    proxyStatus: file.disabled ? 'disabled' : (file.status ?? 'unknown'),
    status: 'unknown',
    message: '',
    windows: [],
    fetchedAt: null,
  }
}

function parseBody(body: unknown): Json {
  if (typeof body === 'string') {
    try {
      return JSON.parse(body) as Json
    } catch {
      return {}
    }
  }
  return (body ?? {}) as Json
}

// Port of collector.fetch's status rules, with the proxy's api-call carrying the provider token.
async function readUsage(config: ProxyConfig, file: AuthFile, entry: CapacityAccount, previous?: CapacityAccount) {
  const now = Date.now() / 1000
  const usage = USAGE[entry.provider]
  const headers = { ...usage.headers }
  const accountId = file.id_token?.chatgpt_account_id
  if (entry.provider === 'Codex' && typeof accountId === 'string') headers['ChatGPT-Account-Id'] = accountId
  const keep = (status: Status, message: string): CapacityAccount => {
    const windows: CapacityWindow[] = previous?.windows ?? []
    const fallback = status === 'stale' && !windows.length ? 'unavailable' : status
    return { ...entry, status: fallback, message, windows, fetchedAt: previous?.fetchedAt ?? null }
  }
  let result: ApiCallResult
  try {
    result = await management<ApiCallResult>(config, 'api-call', {
      auth_index: file.auth_index,
      method: 'GET',
      url: usage.url,
      header: headers,
    })
  } catch {
    return keep('stale', 'Usage check unavailable; retrying later.')
  }
  const code = result.status_code ?? 0
  if (code === 401 || code === 403) {
    return { ...entry, status: 'loginRequired' as Status, message: 'Sign in again in the provider app or proxy.' }
  }
  if (code === 429) return keep('rateLimited', 'Usage check throttled; retrying later.')
  if (code < 200 || code >= 300) return keep('stale', `Provider unavailable (HTTP ${code}).`)
  const data = parseBody(result.body)
  const windows = entry.provider === 'Claude' ? claudeWindows(data) : codexWindows(data)
  const plan = entry.provider === 'Codex' ? planName(data.plan_type) || entry.plan : entry.plan
  return {
    ...entry,
    plan,
    windows,
    status: (windows.length ? 'live' : 'unknown') as Status,
    message: windows.length ? '' : 'The provider did not return a measurable quota.',
    fetchedAt: now,
  }
}

export async function fetchAccounts(config: ProxyConfig, previous: CapacityAccount[]): Promise<CapacityAccount[]> {
  const { files = [] } = await management<{ files?: AuthFile[] }>(config, 'auth-files')
  const known = new Map(previous.map((account) => [account.id, account]))
  const jobs = files.flatMap((file) => {
    const provider = PROVIDERS[file.type ?? '']
    if (!provider) return []
    const entry = baseAccount(file, provider)
    if (file.disabled) {
      return [Promise.resolve({ ...entry, status: 'disabled' as Status, message: 'Disabled in the proxy.' })]
    }
    return [readUsage(config, file, entry, known.get(entry.id))]
  })
  return Promise.all(jobs)
}

export async function checkConnection(config: ProxyConfig): Promise<number> {
  const { files = [] } = await management<{ files?: AuthFile[] }>(config, 'auth-files')
  return files.filter((file) => PROVIDERS[file.type ?? '']).length
}
