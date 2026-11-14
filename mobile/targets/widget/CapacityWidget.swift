import AppIntents
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
    let available: Bool?
    var tokens: Double?
    var costUsd: Double?
    var hasRoom: Bool { available ?? ((used ?? 100) < 100 && state == "Available") }
  }
  struct Agent: Codable, Identifiable {
    let id: String
    let provider: String
    let name: String
    let heading: String
    let step: String
    let progress: Double?
    let ring: Double
    let status: String
    let state: String
    let signal: String
    var subagents: Int?
    var runningSubagents: Int?
    var subagentText: String? {
      guard let count = subagents, count > 0 else { return nil }
      let running = runningSubagents ?? 0
      return running > 0 ? "\(count) sub, \(running) running" : "\(count) sub"
    }
  }
  let updatedAt: Double
  let accounts: [Account]
  var agents: [Agent]?

  static func load() -> CapacitySnapshot? {
    guard let text = UserDefaults(suiteName: "__APP_GROUP__")?.string(forKey: "capacity.snapshot") else { return nil }
    return try? JSONDecoder().decode(CapacitySnapshot.self, from: Data(text.utf8))
  }

  static let preview = CapacitySnapshot(updatedAt: Date().timeIntervalSince1970, accounts: [
    Account(id: "a", provider: "Claude", email: "work", used: 92, window: "Weekly", resetAt: Date().timeIntervalSince1970 + 7200, state: "Available", signal: "red", available: true),
    Account(id: "b", provider: "Codex", email: "personal", used: 64, window: "5-hour", resetAt: Date().timeIntervalSince1970 + 3600, state: "Available", signal: "green", available: true),
  ])
}

func signalColor(_ name: String) -> Color {
  switch name {
  case "red": return .red
  case "orange": return .orange
  case "yellow": return .yellow
  case "gray": return .gray
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

// The dock's formatCount(): 1.2B, 3.4M, 5.6K.
func formatCount(_ value: Double) -> String {
  if value >= 1_000_000_000 { return String(format: "%.1fB", value / 1_000_000_000) }
  if value >= 1_000_000 { return String(format: "%.1fM", value / 1_000_000) }
  if value >= 1_000 { return String(format: "%.1fK", value / 1_000) }
  return String(Int(value))
}

struct CapacityEntry: TimelineEntry {
  let date: Date
  let snapshot: CapacitySnapshot?
}

struct CapacityProvider: TimelineProvider {
  func placeholder(in context: Context) -> CapacityEntry { CapacityEntry(date: .now, snapshot: .preview) }
  func getSnapshot(in context: Context, completion: @escaping (CapacityEntry) -> Void) {
    completion(CapacityEntry(date: .now, snapshot: context.isPreview ? .preview : CapacitySnapshot.load()))
  }
  func getTimeline(in context: Context, completion: @escaping (Timeline<CapacityEntry>) -> Void) {
    let entry = CapacityEntry(date: .now, snapshot: CapacitySnapshot.load())
    completion(Timeline(entries: [entry], policy: .after(.now.addingTimeInterval(15 * 60))))
  }
}

// iOS widgets cannot scroll, so the account lists page: the arrows run this intent, which stores the page per widget.
enum WidgetPages {
  static func page(_ kind: String) -> Int { UserDefaults(suiteName: "__APP_GROUP__")?.integer(forKey: "widget.page.\(kind)") ?? 0 }
  static func set(_ kind: String, _ page: Int) { UserDefaults(suiteName: "__APP_GROUP__")?.set(page, forKey: "widget.page.\(kind)") }
}

struct TurnPageIntent: AppIntent {
  static let title: LocalizedStringResource = "Turn the widget page"
  static let isDiscoverable = false
  @Parameter(title: "Widget") var kind: String
  @Parameter(title: "Page") var page: Int
  init() {}
  init(kind: String, page: Int) {
    self.kind = kind
    self.page = page
  }
  func perform() async throws -> some IntentResult {
    WidgetPages.set(kind, max(0, page))
    return .result()
  }
}

struct AccountLine: View {
  let account: CapacitySnapshot.Account
  let compact: Bool
  var body: some View {
    HStack(spacing: 9) {
      AccountRing(account: account, size: compact ? 26 : 30)
      VStack(alignment: .leading, spacing: 1) {
        Text(account.email).font(.system(size: 12, weight: .semibold)).lineLimit(1)
        detail
        .font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
      }
      Spacer(minLength: 4)
      Text(percentText(account.used)).font(.system(size: 15, weight: .semibold, design: .rounded)).monospacedDigit()
        .foregroundStyle(signalColor(account.signal))
    }
  }

  // One concatenated Text: a relative date inside an HStack stretches to fill the row.
  var detail: Text {
    var line = Text(account.window.isEmpty ? account.state : account.window)
    if let resetAt = account.resetAt, resetAt > Date().timeIntervalSince1970 {
      line = line + Text(" · ") + Text(Date(timeIntervalSince1970: resetAt), style: .relative)
    }
    if let tokens = account.tokens {
      line = line + Text(" · \(formatCount(tokens)) tok")
    }
    return line
  }
}

struct PageArrow: View {
  let kind: String
  let target: Int
  let symbol: String
  let enabled: Bool
  var body: some View {
    Button(intent: TurnPageIntent(kind: kind, page: target)) {
      Image(systemName: symbol).font(.system(size: 13, weight: .semibold)).frame(width: 30, height: 24)
        .background(.white.opacity(enabled ? 0.14 : 0.05), in: Capsule())
    }
    .buttonStyle(.plain).disabled(!enabled).opacity(enabled ? 1 : 0.35)
  }
}

enum WidgetRow: Identifiable {
  case account(CapacitySnapshot.Account)
  case agent(CapacitySnapshot.Agent)
  var id: String {
    switch self {
    case .account(let account): return "account-" + account.id
    case .agent(let agent): return "agent-" + agent.id
    }
  }
}

struct AccountListView: View {
  @Environment(\.widgetFamily) private var family
  let kind: String
  let title: String
  let empty: String
  let entry: CapacityEntry
  var withAgents = false
  let filter: (CapacitySnapshot.Account) -> Bool
  var body: some View {
    let all = entry.snapshot?.accounts ?? []
    let accounts = all.filter(filter)
    let agents = withAgents ? (entry.snapshot?.agents ?? []) : []
    let rows: [WidgetRow] = accounts.map { .account($0) } + agents.map { .agent($0) }
    let perPage = family == .systemLarge ? 7 : 3
    let pages = max(1, (rows.count + perPage - 1) / perPage)
    let page = min(WidgetPages.page(kind), pages - 1)
    Group {
      if entry.snapshot == nil {
        VStack(spacing: 6) {
          Image(systemName: "gauge.with.dots.needle.33percent").font(.title2)
          Text("Open Capacity to connect your proxy").font(.caption2).multilineTextAlignment(.center).foregroundStyle(.secondary)
        }
      } else {
        VStack(alignment: .leading, spacing: family == .systemLarge ? 8 : 5) {
          HStack(spacing: 6) {
            Text(title).font(.system(size: 13, weight: .bold))
            Text(withAgents ? "\(all.count) accounts · \(agents.count) agents" : "\(accounts.count) of \(all.count) with room").font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
            Spacer(minLength: 0)
            if pages > 1 {
              Text("\(page + 1)/\(pages)").font(.system(size: 10)).foregroundStyle(.secondary).monospacedDigit()
              PageArrow(kind: kind, target: page - 1, symbol: "chevron.up", enabled: page > 0)
              PageArrow(kind: kind, target: page + 1, symbol: "chevron.down", enabled: page < pages - 1)
            }
          }
          if rows.isEmpty {
            Spacer(minLength: 0)
            Text(empty).font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity)
            Spacer(minLength: 0)
          } else {
            ForEach(Array(rows.dropFirst(page * perPage).prefix(perPage))) { row in
              switch row {
              case .account(let account): AccountLine(account: account, compact: family != .systemLarge)
              case .agent(let agent): AgentLine(agent: agent)
              }
            }
            Spacer(minLength: 0)
          }
        }
      }
    }
    .foregroundStyle(.white)
    .containerBackground(.black, for: .widget)
    .widgetURL(URL(string: "makocapacity://"))
  }
}

struct AvailableWidget: Widget {
  var body: some WidgetConfiguration {
    StaticConfiguration(kind: "MakoAvailable", provider: CapacityProvider()) { entry in
      AccountListView(kind: "MakoAvailable", title: "Available", empty: "Every account is at its limit", entry: entry) { $0.hasRoom }
    }
    .configurationDisplayName("Available")
    .description("Accounts that still have usage left. Tap the arrows to page.")
    .supportedFamilies([.systemMedium, .systemLarge])
  }
}

struct AllAccountsWidget: Widget {
  var body: some WidgetConfiguration {
    StaticConfiguration(kind: "MakoAll", provider: CapacityProvider()) { entry in
      AccountListView(kind: "MakoAll", title: "All", empty: "No accounts on the proxy", entry: entry, withAgents: true) { _ in true }
    }
    .configurationDisplayName("All accounts")
    .description("Every account, most constrained first, then every agent. Tap the arrows to page.")
    .supportedFamilies([.systemMedium, .systemLarge])
  }
}

// The agents dock's ring: a circle filled to the progress, in the status colour.
struct AgentRingMark: View {
  let agent: CapacitySnapshot.Agent
  let size: CGFloat
  var body: some View {
    ZStack {
      Circle().stroke(.white.opacity(0.12), lineWidth: 3.5)
      Circle().trim(from: 0, to: min(agent.ring, 100) / 100)
        .stroke(signalColor(agent.signal), style: StrokeStyle(lineWidth: 3.5, lineCap: .round))
        .rotationEffect(.degrees(-90))
      ProviderMark(provider: agent.provider).frame(width: size * 0.43, height: size * 0.43).foregroundStyle(.white)
    }
    .frame(width: size, height: size)
  }
}

struct AgentLine: View {
  let agent: CapacitySnapshot.Agent
  var body: some View {
    HStack(spacing: 10) {
      AgentRingMark(agent: agent, size: 30)
      VStack(alignment: .leading, spacing: 1) {
        Text(agent.heading).font(.system(size: 13, weight: .semibold)).lineLimit(1)
        Text([agent.step.isEmpty ? "\(agent.name) · \(agent.state)" : agent.step, agent.subagentText].compactMap { $0 }.joined(separator: " · "))
          .font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
      }
      Spacer(minLength: 4)
      Text(agent.progress.map { "\(Int($0))%" } ?? agent.state)
        .font(.system(size: agent.progress == nil ? 11 : 15, weight: .semibold)).monospacedDigit()
        .foregroundStyle(signalColor(agent.signal)).lineLimit(1)
    }
  }
}

struct AgentsWidgetView: View {
  @Environment(\.widgetFamily) private var family
  let entry: CapacityEntry
  var body: some View {
    let agents = entry.snapshot?.agents ?? []
    Group {
      if agents.isEmpty {
        VStack(spacing: 6) {
          Image(systemName: "sparkles").font(.title2)
          Text(entry.snapshot?.agents == nil ? "Open Capacity, then the Agents tab" : "No agents on the Mac")
            .font(.caption2).multilineTextAlignment(.center).foregroundStyle(.secondary)
        }
      } else {
        VStack(alignment: .leading, spacing: family == .systemLarge ? 10 : 7) {
          Text("Agents").font(.system(size: 12, weight: .semibold)).foregroundStyle(.secondary)
          ForEach(agents.prefix(family == .systemLarge ? 7 : 3)) { AgentLine(agent: $0) }
          Spacer(minLength: 0)
        }
      }
    }
    .foregroundStyle(.white)
    .containerBackground(.black, for: .widget)
    .widgetURL(URL(string: "makocapacity:///agents"))
  }
}

struct AgentsWidget: Widget {
  var body: some WidgetConfiguration {
    StaticConfiguration(kind: "MakoAgents", provider: CapacityProvider()) { entry in
      AgentsWidgetView(entry: entry)
    }
    .configurationDisplayName("Agents")
    .description("The coding agents on your Mac: what each works on and how far along it is.")
    .supportedFamilies([.systemMedium, .systemLarge])
  }
}

@main
struct CapacityWidgetBundle: WidgetBundle {
  var body: some Widget {
    AvailableWidget()
    AllAccountsWidget()
    AgentsWidget()
  }
}
