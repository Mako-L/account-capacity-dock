#!/bin/sh
set -eu
capacity_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
capacity_app="$capacity_root/build/Mako Capacity.app"
mkdir -p "$capacity_app/Contents/MacOS" "$capacity_app/Contents/Resources"
swiftc -swift-version 5 -parse-as-library -O -framework AppKit -framework SwiftUI -framework Combine \
  "$capacity_root/App.swift" -o "$capacity_app/Contents/MacOS/MakoCapacity"
cp "$capacity_root/collector.py" "$capacity_app/Contents/Resources/collector.py"
cp "$capacity_root/codeburn_usage.py" "$capacity_app/Contents/Resources/codeburn_usage.py"
cp "$capacity_root/platform_paths.py" "$capacity_app/Contents/Resources/platform_paths.py"
cp "$capacity_root/Resources/"* "$capacity_app/Contents/Resources/"
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
