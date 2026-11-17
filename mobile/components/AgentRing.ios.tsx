import { View } from 'react-native'
import { AgentRing as NativeRing } from '../native/Capacity/AgentRing.swift'
import type { AgentSignal } from '../features/agents/types'
import { ProviderIcon } from './ProviderIcon'

// The agents dock's circle ring, drawn by SwiftUI so it pulses like the Mac.
export function AgentRing({
  ring,
  signal,
  working,
  provider,
  size,
}: {
  ring: number
  signal: AgentSignal
  working: boolean
  provider: 'Claude' | 'Codex'
  size: number
}) {
  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <NativeRing
        ring={ring}
        signal={signal}
        working={working}
        size={size}
        style={{ position: 'absolute', width: size, height: size }}
      />
      <ProviderIcon provider={provider} size={size * 0.43} />
    </View>
  )
}
