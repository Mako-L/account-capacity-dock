import { View } from 'react-native'
import type { Provider, Signal } from '../features/capacity/types'
import { palette, signalColor } from './palette'
import { ProviderIcon } from './ProviderIcon'

// Android and web: a plain rounded square, coloured once the account has a reading.
export function Ring({ used, signal, provider, size }: { used: number | null; signal: Signal; provider?: Provider; size: number }) {
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.3,
        borderWidth: 4,
        borderColor: used === null ? palette.track : signalColor(signal),
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {provider ? <ProviderIcon provider={provider} size={size * 0.43} /> : null}
    </View>
  )
}
