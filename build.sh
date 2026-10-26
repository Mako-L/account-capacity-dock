#!/bin/sh
set -eu
capacity_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
capacity_app="$capacity_root/build/Mako Capacity.app"
mkdir -p "$capacity_app/Contents/MacOS" "$capacity_app/Contents/Resources"
capacity_swift() {
  swiftc -swift-version 5 -parse-as-library -O -framework AppKit -framework SwiftUI -framework Combine \
    "$@" "$capacity_root/App.swift" "$capacity_root/AgentDock.swift"
}
if [ "${MAKO_UNIVERSAL:-0}" = 1 ]; then
  # Release builds run on Apple Silicon and Intel Macs.
  for capacity_arch in arm64 x86_64; do
    capacity_swift -target "$capacity_arch-apple-macos14.0" -o "$capacity_root/build/MakoCapacity-$capacity_arch"
  done
  lipo -create -output "$capacity_app/Contents/MacOS/MakoCapacity" \
    "$capacity_root/build/MakoCapacity-arm64" "$capacity_root/build/MakoCapacity-x86_64"
else
  capacity_swift -o "$capacity_app/Contents/MacOS/MakoCapacity"
fi
cp "$capacity_root/collector.py" "$capacity_app/Contents/Resources/collector.py"
cp "$capacity_root/agents.py" "$capacity_app/Contents/Resources/agents.py"
cp "$capacity_root/codeburn_usage.py" "$capacity_app/Contents/Resources/codeburn_usage.py"
cp "$capacity_root/platform_paths.py" "$capacity_app/Contents/Resources/platform_paths.py"
cp "$capacity_root/Resources/"* "$capacity_app/Contents/Resources/"
cp "$capacity_root/LICENSE" "$capacity_app/Contents/Resources/LICENSE.txt"
cp "$capacity_root/Info.plist" "$capacity_app/Contents/Info.plist"
swiftc "$capacity_root/Icon.swift" -o "$capacity_root/build/generate-icon"
"$capacity_root/build/generate-icon" "$capacity_root/build/icon-png"
capacity_iconset="$capacity_root/build/Capacity.iconset"
mkdir -p "$capacity_iconset"
for capacity_size in 16 32 128 256 512; do
  cp "$capacity_root/build/icon-png/$capacity_size.png" "$capacity_iconset/icon_${capacity_size}x${capacity_size}.png"
  capacity_double=$((capacity_size * 2))
  cp "$capacity_root/build/icon-png/$capacity_double.png" "$capacity_iconset/icon_${capacity_size}x${capacity_size}@2x.png"
done
iconutil -c icns "$capacity_iconset" -o "$capacity_app/Contents/Resources/Capacity.icns"
codesign --force --deep --sign - "$capacity_app"
printf '%s\n' "$capacity_app"
