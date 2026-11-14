import SwiftUI

// The agents dock's ring (AgentRing in AgentDock.swift): a circle filled to the progress, with a status dot that pulses while the agent works.
public struct AgentRing: View {
  let ring: Double
  let signal: String
  let working: Bool
  let size: Double

  var color: Color {
    switch signal {
    case "red": return .red
    case "yellow": return .yellow
    case "green": return .green
    default: return .gray
    }
  }

  var dot: some View {
    Circle().fill(color).overlay(Circle().stroke(Color(white: 0.065), lineWidth: 2))
  }

  // One's host only takes its height from Yoga, so the size comes in as a prop.
  public var body: some View {
    ZStack {
      Circle().stroke(.white.opacity(0.12), lineWidth: 4)
      Circle().trim(from: 0, to: min(ring, 100) / 100)
        .stroke(color, style: StrokeStyle(lineWidth: 4, lineCap: .round))
        .rotationEffect(.degrees(-90))
    }
    .padding(2)
    .frame(width: size, height: size)
    .overlay(alignment: .bottomTrailing) {
      Group {
        if working {
          TimelineView(.animation(minimumInterval: 1.0 / 30)) { context in
            let phase = context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.2) / 1.2
            ZStack {
              Circle().stroke(color, lineWidth: 1.5).scaleEffect(1 + 1.4 * phase).opacity(0.9 * (1 - phase))
              dot.scaleEffect(1 + 0.3 * sin(phase * .pi))
            }
          }
        } else {
          dot
        }
      }
      .frame(width: size * 0.26, height: size * 0.26)
      .offset(x: 2, y: 2)
    }
  }
}
