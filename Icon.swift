import AppKit

let directory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
for size in [16, 32, 64, 128, 256, 512, 1024] {
    let image = NSImage(size: NSSize(width: size, height: size))
    image.lockFocus()
    let scale = CGFloat(size) / 512
    NSColor(calibratedWhite: 0.07, alpha: 1).setFill()
    NSBezierPath(roundedRect: NSRect(x: 0, y: 0, width: size, height: size), xRadius: 112 * scale, yRadius: 112 * scale).fill()
    for (index, color) in [NSColor.systemOrange, .systemMint, .systemPurple].enumerated() {
        let y = CGFloat(360 - index * 104) * scale
        let track = NSBezierPath(roundedRect: NSRect(x: 104 * scale, y: y - 22 * scale, width: 304 * scale, height: 44 * scale), xRadius: 22 * scale, yRadius: 22 * scale)
        NSColor.white.withAlphaComponent(0.10).setFill()
        track.fill()
        color.setFill()
        NSBezierPath(roundedRect: NSRect(x: 104 * scale, y: y - 22 * scale, width: CGFloat(250 - index * 50) * scale, height: 44 * scale), xRadius: 22 * scale, yRadius: 22 * scale).fill()
    }
    image.unlockFocus()
    let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
    try bitmap.representation(using: .png, properties: [:])!.write(to: directory.appendingPathComponent("\(size).png"))
}
