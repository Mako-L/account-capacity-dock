import SwiftUI

// The phone pushes the same snapshot it writes for the widget; see native/Capacity/SharedSnapshot.swift.
struct CapacitySnapshot: Codable {
  struct Account: Codable, Identifiable {
    let id: String
    let provider: String
    let email: String
    let used: Double?
    let window: String
    let resetAt: Double?
    let state: String
    let signal: String
  }
  let updatedAt: Double
  let accounts: [Account]

  static func decode(_ text: String?) -> CapacitySnapshot? {
    guard let text else { return nil }
    return try? JSONDecoder().decode(CapacitySnapshot.self, from: Data(text.utf8))
  }
}

// The watch app and its complication share the last snapshot through this App Group.
enum WatchShelf {
  static let defaults = UserDefaults(suiteName: "group.dev.mako.capacity") ?? .standard
  static let key = "capacity.snapshot"
  static func load() -> CapacitySnapshot? { CapacitySnapshot.decode(defaults.string(forKey: key)) }
  static func save(_ text: String) { defaults.set(text, forKey: key) }
}

func signalColor(_ name: String) -> Color {
  switch name {
  case "red": return .red
  case "orange": return .orange
  case "yellow": return .yellow
  default: return .green
  }
}

struct ProviderMark: View {
  let provider: String
  var body: some View {
    Image(provider.lowercased()).resizable().renderingMode(.template).scaledToFit()
  }
}

// Same geometry as the dock's AccountRing in dock style: rounded square, 0.30 corner, 4pt stroke.
struct AccountRing: View {
  let account: CapacitySnapshot.Account
  let size: CGFloat
  var lineWidth: CGFloat = 4
  var body: some View {
    let shape = RoundedRectangle(cornerRadius: size * 0.30, style: .continuous)
    ZStack {
      shape.stroke(.white.opacity(0.12), lineWidth: lineWidth)
      if let used = account.used {
        shape.trim(from: 0, to: used / 100)
          .stroke(signalColor(account.signal), style: StrokeStyle(lineWidth: lineWidth, lineCap: .round))
          .rotationEffect(.degrees(-90))
      }
      ProviderMark(provider: account.provider).frame(width: size * 0.43, height: size * 0.43).foregroundStyle(.white)
    }
    .frame(width: size, height: size)
  }
}
