import { View } from 'react-native'
import { CapacityRing } from '../native/Capacity/CapacityRing.swift'
import type { Provider, Signal } from '../features/capacity/types'
import { ProviderIcon } from './ProviderIcon'

// The dock's ring, drawn by SwiftUI so the phone matches the Mac exactly.
export function Ring({ used, signal, provider, size }: { used: number | null; signal: Signal; provider?: Provider; size: number }) {
  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <CapacityRing used={used ?? -1} signal={signal} style={{ position: 'absolute', width: size, height: size }} />
      {provider ? <ProviderIcon provider={provider} size={size * 0.43} /> : null}
    </View>
  )
}
