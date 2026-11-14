export class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

type RequestOptions = { method?: 'GET' | 'POST'; headers?: Record<string, string>; body?: unknown; timeoutMs?: number }

// The one place the app touches the network.
export async function executeRequest<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 20000)
  try {
    const response = await fetch(url, {
      method: options.method ?? 'GET',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...options.headers },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    })
    if (!response.ok) throw new HttpError(response.status, `HTTP ${response.status}`)
    return (await response.json()) as T
  } catch (error) {
    if (error instanceof HttpError) throw error
    throw new HttpError(0, controller.signal.aborted ? 'timed out' : 'not reachable')
  } finally {
    clearTimeout(timer)
  }
}
