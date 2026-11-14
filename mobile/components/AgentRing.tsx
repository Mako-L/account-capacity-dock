import { View } from 'react-native'
import type { AgentSignal } from '../features/agents/types'
import { palette } from './palette'
import { ProviderIcon } from './ProviderIcon'

// Android and web: a circle in the status colour once the agent has any progress, with the status dot.
export function AgentRing({
  ring,
  signal,
  provider,
  size,
}: {
  ring: number
  signal: AgentSignal
  working: boolean
  provider: 'Claude' | 'Codex'
  size: number
}) {
  const colour = palette.signal[signal]
  const dot = size * 0.26
  return (
    <View style={{ width: size, height: size }}>
      <View
        style={{
          width: size,
          height: size,
          borderRadius: size / 2,
          borderWidth: 4,
          borderColor: ring > 0 ? colour : palette.track,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <ProviderIcon provider={provider} size={size * 0.43} />
      </View>
      <View
        style={{
          position: 'absolute',
          right: -2,
          bottom: -2,
          width: dot,
          height: dot,
          borderRadius: dot / 2,
          backgroundColor: colour,
          borderWidth: 2,
          borderColor: palette.card,
        }}
      />
    </View>
  )
}
