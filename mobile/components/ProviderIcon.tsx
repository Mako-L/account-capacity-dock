import { Image, type ImageSourcePropType, type ImageStyle, type StyleProp } from 'react-native'
import type { Provider } from '../features/capacity/types'

const ICONS: Record<Provider, ImageSourcePropType> = {
  Claude: require('../assets/providers/claude.png'),
  Codex: require('../assets/providers/codex.png'),
}

export function ProviderIcon({ provider, size, style }: { provider: Provider; size: number; style?: StyleProp<ImageStyle> }) {
  return <Image source={ICONS[provider]} style={[{ width: size, height: size }, style]} resizeMode="contain" />
}
