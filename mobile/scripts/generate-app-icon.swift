import AppKit

// The dock's icon (../Icon.swift) drawn full-bleed at 1024: iOS, watchOS and Android mask the corners themselves.
let output = URL(fileURLWithPath: CommandLine.arguments[1])
let size = 1024
let scale = CGFloat(size) / 512
// App icons must be opaque, so draw into an RGB context with no alpha channel.
let context = CGContext(data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: false)
NSColor(calibratedWhite: 0.07, alpha: 1).setFill()
NSRect(x: 0, y: 0, width: size, height: size).fill()
for (index, color) in [NSColor.systemOrange, .systemMint, .systemPurple].enumerated() {
    let y = CGFloat(360 - index * 104) * scale
    NSColor.white.withAlphaComponent(0.10).setFill()
    NSBezierPath(roundedRect: NSRect(x: 104 * scale, y: y - 22 * scale, width: 304 * scale, height: 44 * scale), xRadius: 22 * scale, yRadius: 22 * scale).fill()
    color.setFill()
    NSBezierPath(roundedRect: NSRect(x: 104 * scale, y: y - 22 * scale, width: CGFloat(250 - index * 50) * scale, height: 44 * scale), xRadius: 22 * scale, yRadius: 22 * scale).fill()
}
NSGraphicsContext.restoreGraphicsState()
try NSBitmapImageRep(cgImage: context.makeImage()!).representation(using: .png, properties: [:])!.write(to: output)
