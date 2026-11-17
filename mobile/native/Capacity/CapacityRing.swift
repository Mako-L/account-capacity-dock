import SwiftUI

// The dock's ring: rounded square, 0.30 corner, 4pt stroke, trimmed from the top. used < 0 means unknown.
public struct CapacityRing: View {
  let used: Double
  let signal: String
  let size: Double

  var color: Color {
    switch signal {
    case "red": return .red
    case "orange": return .orange
    case "yellow": return .yellow
    default: return .green
    }
  }

  // One's host only takes its height from Yoga, so the size comes in as a prop.
  public var body: some View {
    let shape = RoundedRectangle(cornerRadius: size * 0.30, style: .continuous)
    ZStack {
      shape.stroke(.white.opacity(0.12), lineWidth: 4)
      if used >= 0 {
        shape.trim(from: 0, to: min(1, used / 100))
          .stroke(color, style: StrokeStyle(lineWidth: 4, lineCap: .round))
          .rotationEffect(.degrees(-90))
      }
    }
    .padding(2)
    .frame(width: size, height: size)
  }
}
