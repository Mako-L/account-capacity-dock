import SwiftUI
import UIKit
import WidgetKit

// The phone app writes this snapshot to the App Group; see native/Capacity/SharedSnapshot.swift.
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

  static func load() -> CapacitySnapshot? {
    guard let text = UserDefaults(suiteName: "__APP_GROUP__")?.string(forKey: "capacity.snapshot") else { return nil }
    return try? JSONDecoder().decode(CapacitySnapshot.self, from: Data(text.utf8))
  }

  static let preview = CapacitySnapshot(updatedAt: Date().timeIntervalSince1970, accounts: [
    Account(id: "a", provider: "Claude", email: "work", used: 92, window: "Weekly", resetAt: Date().timeIntervalSince1970 + 7200, state: "Available", signal: "red"),
    Account(id: "b", provider: "Codex", email: "personal", used: 64, window: "5-hour", resetAt: Date().timeIntervalSince1970 + 3600, state: "Available", signal: "green"),
  ])
}

func signalColor(_ name: String) -> Color {
  switch name {
  case "red": return .red
  case "orange": return .orange
  case "yellow": return .yellow
  default: return .green
  }
}

private let providerIcons: [String: UIImage] = [
  "Claude": UIImage(data: Data(base64Encoded: "__CLAUDE_PNG__") ?? Data()),
  "Codex": UIImage(data: Data(base64Encoded: "__CODEX_PNG__") ?? Data()),
].compactMapValues { $0 }

struct ProviderMark: View {
  let provider: String
  var body: some View {
    if let image = providerIcons[provider] {
      Image(uiImage: image).resizable().renderingMode(.template).scaledToFit()
    } else {
      Image(systemName: "sparkle").resizable().scaledToFit()
    }
  }
}

// Same geometry as the dock's AccountRing in dock style: rounded square, 0.30 corner, 4pt stroke.
struct AccountRing: View {
  let account: CapacitySnapshot.Account
  let size: CGFloat
  var body: some View {
    let shape = RoundedRectangle(cornerRadius: size * 0.30, style: .continuous)
    ZStack {
      shape.stroke(.white.opacity(0.12), lineWidth: 4)
      if let used = account.used {
        shape.trim(from: 0, to: used / 100)
          .stroke(signalColor(account.signal), style: StrokeStyle(lineWidth: 4, lineCap: .round))
          .rotationEffect(.degrees(-90))
      }
      ProviderMark(provider: account.provider).frame(width: size * 0.43, height: size * 0.43).foregroundStyle(.white)
    }
    .frame(width: size, height: size)
  }
}

func percentText(_ used: Double?) -> String { used.map { "\(Int($0.rounded()))%" } ?? "—" }

struct CapacityEntry: TimelineEntry {
  let date: Date
  let snapshot: CapacitySnapshot?
}

struct CapacityProvider: TimelineProvider {
  func placeholder(in context: Context) -> CapacityEntry { CapacityEntry(date: .now, snapshot: .preview) }
  func getSnapshot(in context: Context, completion: @escaping (CapacityEntry) -> Void) {
    completion(CapacityEntry(date: .now, snapshot: context.isPreview ? .preview : CapacitySnapshot.load() ?? .preview))
  }
  func getTimeline(in context: Context, completion: @escaping (Timeline<CapacityEntry>) -> Void) {
    let entry = CapacityEntry(date: .now, snapshot: CapacitySnapshot.load())
    completion(Timeline(entries: [entry], policy: .after(.now.addingTimeInterval(15 * 60))))
  }
}

struct SmallView: View {
  let accounts: [CapacitySnapshot.Account]
  var body: some View {
    let columns = [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)]
    LazyVGrid(columns: columns, spacing: 8) {
      ForEach(accounts.prefix(4)) { account in
        VStack(spacing: 3) {
          AccountRing(account: account, size: 40)
          Text(percentText(account.used)).font(.system(size: 12, weight: .semibold)).monospacedDigit()
        }
      }
    }
  }
}

struct MediumView: View {
  let accounts: [CapacitySnapshot.Account]
  var body: some View {
    HStack(alignment: .top, spacing: 10) {
      ForEach(accounts.prefix(4)) { account in
        VStack(spacing: 4) {
          AccountRing(account: account, size: 46)
          Text(percentText(account.used)).font(.system(size: 15, weight: .semibold)).monospacedDigit()
          Text(account.window).font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
          if let resetAt = account.resetAt, resetAt > Date().timeIntervalSince1970 {
            Text(Date(timeIntervalSince1970: resetAt), style: .relative)
              .font(.system(size: 9)).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.7)
          }
        }
        .frame(maxWidth: .infinity)
      }
    }
  }
}

struct CapacityWidgetView: View {
  @Environment(\.widgetFamily) private var family
  let entry: CapacityEntry
  var body: some View {
    Group {
      if let accounts = entry.snapshot?.accounts, !accounts.isEmpty {
        if family == .systemMedium { MediumView(accounts: accounts) } else { SmallView(accounts: accounts) }
      } else {
        VStack(spacing: 6) {
          Image(systemName: "gauge.with.dots.needle.33percent").font(.title2)
          Text("Open Capacity to connect your proxy").font(.caption2).multilineTextAlignment(.center).foregroundStyle(.secondary)
        }
      }
    }
    .foregroundStyle(.white)
    .containerBackground(.black, for: .widget)
    .widgetURL(URL(string: "makocapacity://"))
  }
}

struct CapacityWidget: Widget {
  var body: some WidgetConfiguration {
    StaticConfiguration(kind: "MakoCapacity", provider: CapacityProvider()) { entry in
      CapacityWidgetView(entry: entry)
    }
    .configurationDisplayName("Capacity")
    .description("The most constrained accounts and how much of each quota is used.")
    .supportedFamilies([.systemSmall, .systemMedium])
  }
}

@main
struct CapacityWidgetBundle: WidgetBundle {
  var body: some Widget { CapacityWidget() }
}
