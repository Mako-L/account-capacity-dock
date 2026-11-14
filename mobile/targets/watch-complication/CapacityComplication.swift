import SwiftUI
import WidgetKit

struct ComplicationEntry: TimelineEntry {
  let date: Date
  let accounts: [CapacitySnapshot.Account]
}

struct ComplicationProvider: TimelineProvider {
  static let sample = [
    CapacitySnapshot.Account(id: "a", provider: "Claude", email: "work", used: 92, window: "Weekly",
                             resetAt: Date().timeIntervalSince1970 + 7200, state: "Available", signal: "red"),
    CapacitySnapshot.Account(id: "b", provider: "Codex", email: "personal", used: 64, window: "5-hour",
                             resetAt: Date().timeIntervalSince1970 + 3600, state: "Available", signal: "green"),
  ]

  func placeholder(in context: Context) -> ComplicationEntry { ComplicationEntry(date: Date(), accounts: Self.sample) }

  func getSnapshot(in context: Context, completion: @escaping (ComplicationEntry) -> Void) {
    completion(context.isPreview ? placeholder(in: context) : ComplicationEntry(date: Date(), accounts: WatchShelf.load()?.accounts ?? []))
  }

  func getTimeline(in context: Context, completion: @escaping (Timeline<ComplicationEntry>) -> Void) {
    let entry = ComplicationEntry(date: Date(), accounts: WatchShelf.load()?.accounts ?? [])
    completion(Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(15 * 60))))
  }
}

// The phone sorts accounts tightest first, so the first one is the most constrained.
struct ComplicationView: View {
  @Environment(\.widgetFamily) private var family
  let entry: ComplicationEntry

  var body: some View {
    if let top = entry.accounts.first {
      switch family {
      case .accessoryRectangular: rectangular
      case .accessoryInline: Text("\(top.provider) \(percent(top))")
      case .accessoryCorner:
        ProviderMark(provider: top.provider).padding(6)
          .widgetLabel { Gauge(value: (top.used ?? 0) / 100) { Text(percent(top)) }.tint(signalColor(top.signal)) }
      default: circular(top)
      }
    } else {
      Image(systemName: "iphone.and.arrow.forward")
    }
  }

  private func percent(_ account: CapacitySnapshot.Account) -> String {
    account.used.map { "\(Int($0.rounded()))%" } ?? "—"
  }

  private func circular(_ account: CapacitySnapshot.Account) -> some View {
    Gauge(value: (account.used ?? 0) / 100) {
      ProviderMark(provider: account.provider)
    } currentValueLabel: {
      Text(account.used.map { "\(Int($0.rounded()))" } ?? "—")
    }
    .gaugeStyle(.accessoryCircular)
    .tint(signalColor(account.signal))
  }

  private var rectangular: some View {
    VStack(alignment: .leading, spacing: 2) {
      ForEach(entry.accounts.prefix(3)) { account in
        HStack(spacing: 4) {
          ProviderMark(provider: account.provider).frame(width: 11, height: 11)
          Text(account.email).font(.system(size: 12)).lineLimit(1)
          Spacer(minLength: 2)
          Text(percent(account)).font(.system(size: 12, weight: .semibold)).monospacedDigit()
            .foregroundStyle(signalColor(account.signal))
        }
      }
    }
  }
}

@main
struct CapacityComplication: Widget {
  var body: some WidgetConfiguration {
    StaticConfiguration(kind: "CapacityComplication", provider: ComplicationProvider()) { entry in
      ComplicationView(entry: entry).containerBackground(.black, for: .widget)
    }
    .configurationDisplayName("Capacity")
    .description("The most constrained account's quota.")
    .supportedFamilies([.accessoryCircular, .accessoryRectangular, .accessoryInline, .accessoryCorner])
  }
}
