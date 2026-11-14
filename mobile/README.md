# Capacity for iPhone, widgets and Apple Watch

The phone version of the Mako Capacity dock. It reads the same CLIProxyAPI management API the desktop collector reads and shows each account's quota ring, percent used and reset countdown.

Built with [One](https://onestack.dev/) 2.17 (React Native + web). One's own `one prebuild` generates the iOS project and the WidgetKit extension, so no Expo is involved; One has no watchOS targets, so `scripts/add-watch-target.rb` adds the watch app to the generated project after prebuild.

## What it shows

- **Accounts list:** one row per proxy login, with the dock's rounded-square quota ring, the provider icon, percent used of the most constrained window, the reset countdown and a connected / reconnect state. Pull to refresh.
- **Account detail:** every quota window with its own ring, percent, reset time and plan.
- **Settings:** the proxy address and management key.
- **Widget (small and medium):** the most constrained accounts' rings and percent.
- **Watch app:** the same rings and percents, pushed from the phone.

The rules match the dock (`collector.py`, `App.swift`): percent used is the highest window, the limiting window is the one with the highest use, the reset is that window's reset, and the ring colour follows the same green / yellow / orange / red thresholds.

### What the phone cannot show

These come from the desktop collector, not from the proxy, so the phone leaves them out rather than guess:

- **CodeBurn spend and local token counts** (`codeburn_usage`, the per-window token and cost lines). They are read from the Mac's local session logs.
- **Cursor.** The dock reads Cursor from the Mac's Cursor app database; the proxy holds no Cursor login.
- **Local logins the proxy does not hold** (for example a Claude login only in the Mac keychain).

## Data source and secrets

The settings screen takes the proxy address, for example `http://127.0.0.1:8317` or `https://server:8317` (the panel is at `<address>/management.html`), and the management key.

- The key is stored only in the iOS Keychain through `One.SecureStore`, never in plain storage, logs or the snapshot shared with the widget and watch.
- Plain `http` is accepted only for a loopback address, the same rule as `scripts/capacity.py`.
- The app calls `GET /v0/management/auth-files` for the logins and `POST /v0/management/api-call` to read each provider's usage endpoint with the proxy's stored token, like `collector.py`. Provider tokens never reach the phone.
- The widget and watch receive a snapshot with provider, label, percent, window, reset time and state only.

## Setup

Requirements: macOS with Xcode 27 (iOS 17+ simulator; a watchOS simulator runtime for the watch app), Bun 1.3+, Node 24, CocoaPods and the `xcodeproj` Ruby gem (installed with CocoaPods).

```bash
cd mobile
bun install
bun run prebuild:ios      # one prebuild --platform ios, then adds the watch target
```

`ios/` is generated. Change `vite.config.ts`, `native/` or `targets/` and run `bun run prebuild:ios` again.

## Run

```bash
bun run dev               # One dev server (JS bundle for Debug builds)
bun run ios               # build and launch on the default iPhone simulator
```

Or with Xcode tools directly:

```bash
cd ios
xcodebuild -workspace MakoCapacity.xcworkspace -scheme MakoCapacity -configuration Debug \
  -destination 'platform=iOS Simulator,name=iPhone 18 Pro' -derivedDataPath build/dd build
xcrun simctl install booted build/dd/Build/Products/Debug-iphonesimulator/MakoCapacity.app
xcrun simctl launch booted dev.mako.capacity
```

Watch app: pair a watch simulator with the iPhone simulator (`xcrun simctl pair <watch> <phone>`), build the `CapacityWatch` scheme for `platform=watchOS Simulator`, install it on the watch, then refresh on the phone. The phone sends each refresh over WatchConnectivity.

Widget: long-press the home screen, tap Edit, Add Widget, then pick Capacity.

## Layout

```
app/                  screens (list, account/[id], settings)
components/           Ring (native SwiftUI on iOS, react-native-svg elsewhere), rows, icons
features/capacity/    proxy client, dock rules, store, Keychain config, widget/watch publishing
native/Capacity/      Swift: App Group + WatchConnectivity bridge, the SwiftUI ring
targets/widget/       SwiftUI WidgetKit extension (replaces One's generated widget body)
targets/watch/        SwiftUI watchOS app
scripts/              add-watch-target.rb
```

## Not done

- Android widget: not built. The Android app builds from the same code; the widget would need a Glance target that One's prebuild does not generate yet.
- Watch complication: not built.
