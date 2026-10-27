import AppKit
import SwiftUI
import Combine

struct CapacityWindow: Codable, Identifiable {
    let label: String
    let used: Double
    let resetAt: Double?
    let detail: String?
    let spent: WindowSpend?
    let usedUpIn: Double?
    var id: String { label }
}

/// What this account used inside one quota window, from the proxy's usage tracker.
struct WindowSpend: Codable {
    let tokens: Double?
    let costUsd: Double?
    let planPercent: Double?
    var line: String {
        // API-equivalent spend against one week of the plan's price: 300% means three weeks of the plan.
        let plan = planPercent.map { $0 >= 200 ? String(format: "%.0f× the plan price", $0 / 100) : String(format: "%.0f%% of the plan price", $0) }
        return ["Used \(tokens.map(formatCount) ?? "—") tokens", costUsd.map { String(format: "$%.2f", $0) }, plan].compactMap { $0 }.joined(separator: " · ")
    }
}

struct CapacityAccount: Codable, Identifiable {
    let id: String
    let provider: String
    let email: String
    let title: String
    let plan: String
    let source: String
    let status: String
    let message: String
    let windows: [CapacityWindow]
    let fetchedAt: Double?
    let localUsage: LocalUsage?
    let onDemandUsd: Double?
    let proxyRef: String?
    var used: Double? { provider == "Cursor" ? windows.first(where: { $0.label == "Cursor Models" })?.used : windows.map(\.used).max() }
    var limitingWindow: String { windows.max(by: { $0.used < $1.used })?.label ?? "Unknown" }
    var accent: Color { provider == "Claude" ? .orange : provider == "Codex" ? .mint : .purple }
    var signal: Color { status == "loginRequired" ? .orange : (used ?? 0) >= 100 ? .red : (used ?? 0) >= 85 ? .orange : (used ?? 0) >= 70 ? .yellow : .green }
    var stateLabel: String {
        switch status {
        case "live": return provider == "Cursor" && plan.lowercased() == "free" ? "Free plan" : (used ?? 0) >= 100 ? "At limit" : "Available"
        case "loginRequired": return "Reconnect"
        case "rateLimited": return "Throttled"
        case "stale": return "Cached"
        case "unavailable": return "Unavailable"
        default: return "Unknown"
        }
    }
}

struct LocalUsage: Codable {
    let tokens: Double?
    let inputTokens: Double?
    let outputTokens: Double?
    let cacheReadTokens: Double?
    let cacheWriteTokens: Double?
    let costUsd: Double?
    let estimated: Bool?
    let unpricedModels: Int?
    let status: String
    let fetchedAt: Double?
    let message: String?
    let scope: String?
}

func formatCount(_ value: Double) -> String {
    if value >= 1_000_000_000 { return String(format: "%.1fB", value / 1_000_000_000) }
    if value >= 1_000_000 { return String(format: "%.1fM", value / 1_000_000) }
    if value >= 1_000 { return String(format: "%.1fK", value / 1_000) }
    return String(format: "%.0f", value)
}

struct CapacitySnapshot: Codable {
    let updatedAt: Double
    let accounts: [CapacityAccount]
    let hidden: [String: String]?
    let warning: String?
}

@MainActor
final class CapacityStore: ObservableObject {
    @Published var accounts: [CapacityAccount] = []
    @Published var hidden: [String: String] = [:]
    @Published var refreshing = false
    @Published var error: String?
    @Published var dockEdge = UserDefaults.standard.string(forKey: "dockEdge") ?? "right"
    @Published var dockScale = (UserDefaults.standard.object(forKey: "dockScale") as? Double ?? 1) {
        didSet { UserDefaults.standard.set(dockScale, forKey: "dockScale") }
    }
    @Published var dockLength = (UserDefaults.standard.object(forKey: "dockLength") as? Double ?? 820) {
        didSet { UserDefaults.standard.set(dockLength, forKey: "dockLength") }
    }
    @Published var roundIcons = UserDefaults.standard.bool(forKey: "roundIcons") {
        didSet { UserDefaults.standard.set(roundIcons, forKey: "roundIcons") }
    }
    @Published var showNames = (UserDefaults.standard.object(forKey: "showNames") as? Bool ?? true) {
        didSet { UserDefaults.standard.set(showNames, forKey: "showNames") }
    }
    @Published var dockOpacity = (UserDefaults.standard.object(forKey: "dockOpacity") as? Double ?? 1) {
        didSet { UserDefaults.standard.set(dockOpacity, forKey: "dockOpacity") }
    }
    /// Agents can live in this dock behind a switch, in place of their own dock.
    @Published var agentsInDock = UserDefaults.standard.bool(forKey: "agentsInDock") {
        didSet { UserDefaults.standard.set(agentsInDock, forKey: "agentsInDock") }
    }
    @Published var dockMode = UserDefaults.standard.string(forKey: "dockMode") ?? "capacity" {
        didSet { UserDefaults.standard.set(dockMode, forKey: "dockMode") }
    }
    var showsAgents: Bool { agentsInDock && dockMode == "agents" }
    private var timer: Timer?
    private var usageProcess: Process?
    private var queuedAction: [String] = []

    init() {
        let cache = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Mako Capacity/snapshot.json")
        if let data = try? Data(contentsOf: cache), let snapshot = try? JSONDecoder().decode(CapacitySnapshot.self, from: data) {
            accounts = snapshot.accounts
            hidden = snapshot.hidden ?? [:]
        }
        refresh()
        refreshUsage()
        timer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }

    /// `action` is a collector flag and account id, such as ["--hide", id].
    func refresh(force: Bool = false, action: [String] = []) {
        refreshUsage()
        guard !refreshing else {
            // A background poll is running: keep the user's action for the next run.
            if !action.isEmpty { queuedAction = action }
            return
        }
        refreshing = true
        let script = Bundle.main.resourceURL!.appendingPathComponent("collector.py")
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let process = Process()
            let output = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            let errors = Pipe()
            process.arguments = [script.path, "--skip-usage"] + (force ? ["--refresh"] : []) + action
            process.standardOutput = output
            process.standardError = errors
            do {
                try process.run()
                let data = output.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                guard process.terminationStatus == 0 else {
                    let message = String(decoding: errors.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    throw NSError(domain: "Collector", code: Int(process.terminationStatus),
                                  userInfo: action.isEmpty || message.isEmpty ? [:] : [NSLocalizedDescriptionKey: message])
                }
                let snapshot = try JSONDecoder().decode(CapacitySnapshot.self, from: data)
                DispatchQueue.main.async {
                    self?.accounts = snapshot.accounts
                    self?.hidden = snapshot.hidden ?? [:]
                    self?.error = snapshot.warning
                    self?.finishRefresh()
                }
            } catch {
                DispatchQueue.main.async {
                    let detail = (error as NSError).userInfo[NSLocalizedDescriptionKey] as? String
                    self?.error = detail ?? "Could not update accounts. Previous readings remain visible."
                    self?.finishRefresh()
                }
            }
        }
    }

    private func finishRefresh() {
        refreshing = false
        let action = queuedAction
        queuedAction = []
        if !action.isEmpty { refresh(action: action) }
    }

    func refreshUsage() {
        guard usageProcess?.isRunning != true else { return }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [Bundle.main.resourceURL!.appendingPathComponent("codeburn_usage.py").path]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        usageProcess = process
        try? process.run()
    }
}

func age(_ timestamp: Double?) -> String {
    guard let timestamp else { return "Not checked" }
    let minutes = max(0, Int((Date().timeIntervalSince1970 - timestamp) / 60))
    return minutes == 0 ? "Updated just now" : "Updated \(minutes)m ago"
}

func resetTime(_ timestamp: Double?) -> String {
    guard let timestamp else { return "No active reset" }
    let seconds = Int(timestamp - Date().timeIntervalSince1970)
    guard seconds > 0 else { return "Reset due" }
    if seconds >= 86400 { return "Resets in \(seconds / 86400)d \((seconds % 86400) / 3600)h" }
    if seconds >= 3600 { return "Resets in \(seconds / 3600)h \((seconds % 3600) / 60)m" }
    return "Resets in \(max(1, seconds / 60))m"
}

// Cursor cube geometry adapted from LLimit's ProviderIcon (MIT).
struct CursorCube: Shape {
    func path(in rect: CGRect) -> Path {
        let size = min(rect.width, rect.height)
        func point(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: rect.midX - size / 2 + x / 24 * size, y: rect.midY - size / 2 + y / 24 * size)
        }
        var path = Path()
        for polygon: [(CGFloat, CGFloat)] in [
            [(12, 0.13), (1.89, 5.68), (1.47, 6.40), (1.47, 17.59), (1.89, 18.31),
             (11.50, 23.86), (12.50, 23.86), (22.11, 18.31), (22.53, 17.59),
             (22.53, 6.40), (22.11, 5.68), (12.50, 0.13)],
            [(2.66, 6.34), (21.21, 6.34), (21.51, 6.85), (12.23, 22.92),
             (12, 22.86), (12, 12.34), (11.70, 11.83), (2.59, 6.57)]
        ] {
            path.move(to: point(polygon[0].0, polygon[0].1))
            for (x, y) in polygon.dropFirst() { path.addLine(to: point(x, y)) }
            path.closeSubpath()
        }
        return path
    }
}

struct ProviderMark: View {
    let provider: String
    var body: some View {
        if provider == "Cursor" {
            CursorCube().fill(style: FillStyle(eoFill: true))
        } else if let url = Bundle.main.url(forResource: provider.lowercased(), withExtension: "png"), let image = NSImage(contentsOf: url) {
            Image(nsImage: image).resizable().renderingMode(.template).scaledToFit()
        } else {
            Image(systemName: "sparkle").resizable().scaledToFit()
        }
    }
}

struct RingOutline: Shape {
    var circular: Bool
    var cornerRadius: CGFloat
    func path(in rect: CGRect) -> Path {
        circular ? Circle().path(in: rect) : RoundedRectangle(cornerRadius: cornerRadius, style: .continuous).path(in: rect)
    }
}

struct AccountRing: View {
    let account: CapacityAccount
    var size: CGFloat = 48
    var dockStyle = false
    var round = false
    var cornerRadius: CGFloat { size * (round || !dockStyle ? 0.50 : 0.30) }
    var body: some View {
        ZStack {
            RingOutline(circular: round, cornerRadius: cornerRadius)
                .stroke(.black.opacity(0.75), lineWidth: 6)
            RingOutline(circular: round, cornerRadius: cornerRadius)
                .stroke(.white.opacity(0.12), lineWidth: 4)
            if let used = account.used {
                RingOutline(circular: round, cornerRadius: cornerRadius).trim(from: 0, to: used / 100)
                    .stroke(account.signal, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                    .rotationEffect(.degrees(-90))
            }
            ProviderMark(provider: account.provider).frame(width: size * 0.43, height: size * 0.43).foregroundStyle(.white)
        }
        .frame(width: size, height: size)
        .accessibilityLabel("\(account.provider), \(account.email), \(account.used.map { String(Int($0)) + " percent used" } ?? "capacity unknown"), \(account.stateLabel)")
    }
}

struct AccountCard: View {
    let account: CapacityAccount
    var showAllWindows = true
    var roundIcons = false
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(account.provider.uppercased()).font(.system(size: 10, weight: .semibold)).foregroundStyle(account.accent)
            HStack(spacing: 12) {
                AccountRing(account: account, size: 40, dockStyle: true, round: roundIcons)
                VStack(alignment: .leading, spacing: 3) {
                    Text(account.title).font(.headline)
                }
                Spacer(minLength: 0)
                Text(account.used.map { "\(Int($0))%" } ?? "—").font(.system(size: 25, weight: .semibold, design: .rounded)).foregroundStyle(account.signal)
            }
            Text(account.email).font(.system(size: 11)).foregroundStyle(.secondary).textSelection(.enabled).lineLimit(2).help(account.email)
            HStack {
                Text(account.provider == "Claude" || account.plan.isEmpty ? account.provider : account.plan).lineLimit(1).help(account.plan)
                Spacer()
                Text(account.stateLabel).foregroundStyle(account.signal)
            }.font(.caption)
            if account.windows.isEmpty {
                Text(account.message.isEmpty ? "Capacity unknown" : account.message).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            } else {
                ForEach(showAllWindows || account.provider == "Cursor" ? account.windows : Array(account.windows.prefix(2))) { window in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(window.label)
                            Spacer()
                            Text("\(Int(window.used))% used").monospacedDigit()
                        }.font(.caption)
                        GeometryReader { geometry in
                            ZStack(alignment: .leading) {
                                Capsule().fill(.white.opacity(0.09))
                                Capsule().fill(window.used >= 100 ? Color.red : account.accent)
                                    .frame(width: geometry.size.width * min(1, window.used / 100))
                            }
                        }.frame(height: 5)
                        Text(resetTime(window.resetAt)).font(.system(size: 10)).foregroundStyle(.secondary)
                        if let detail = window.detail { Text(detail).font(.system(size: 10)).foregroundStyle(.secondary) }
                        if let spent = window.spent { Text(spent.line).font(.system(size: 10)).foregroundStyle(.secondary) }
                        if let usedUpIn = window.usedUpIn { Text("Used up in \(span(usedUpIn))").font(.system(size: 10)).foregroundStyle(.secondary) }
                    }
                }
                if !account.message.isEmpty {
                    Text(account.message).font(.caption).foregroundStyle(.secondary)
                }
            }
            VStack(alignment: .leading, spacing: 6) {
                Divider().overlay(.white.opacity(0.08))
                Text(account.localUsage?.scope == "account" ? "Last 24 h · this account" : "Today · local \(account.provider == "Cursor" ? "Cursor CLI" : account.provider) usage")
                    .font(.system(size: 11, weight: .semibold))
                HStack {
                    Text("Tokens\(account.localUsage?.estimated == true ? " (estimated)" : "")")
                    Spacer()
                    Text(account.localUsage?.tokens.map(formatCount) ?? "—").monospacedDigit()
                }
                HStack {
                    Text("API-equivalent cost")
                    Spacer()
                    Text(account.localUsage?.costUsd.map { String(format: "$%.2f", $0) } ?? "—").monospacedDigit()
                }
                if let usage = account.localUsage, usage.tokens != nil {
                    Text("Input \(usage.inputTokens.map(formatCount) ?? "—") · Output \(usage.outputTokens.map(formatCount) ?? "—")\nCache read \(usage.cacheReadTokens.map(formatCount) ?? "—") · Write \(usage.cacheWriteTokens.map(formatCount) ?? "—")")
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                }
                Text(account.localUsage?.scope == "account" ? "Proxy usage tracker · CodeBurn prices · not your bill" : "CodeBurn · all local accounts · not your bill")
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                if let usage = account.localUsage {
                    if usage.status != "live" {
                        Text(usage.status == "partial" ? "Indexing · totals are incomplete" : usage.message?.isEmpty == false ? usage.message! : "Cached · \(age(usage.fetchedAt))")
                            .font(.system(size: 10)).foregroundStyle(.secondary)
                    }
                    if (usage.unpricedModels ?? 0) > 0 {
                        Text("Some models have no price; cost is incomplete.")
                            .font(.system(size: 10)).foregroundStyle(.secondary)
                    }
                } else {
                    Text("Usage unavailable · install CodeBurn with the setup CLI.")
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                }
                if let spend = account.onDemandUsd {
                    HStack {
                        Text("On-demand · billing cycle")
                        Spacer()
                        Text(String(format: "$%.2f", spend)).monospacedDigit()
                    }
                }
            }.font(.caption)
            HStack {
                Text(account.source)
                Spacer()
                Text(age(account.fetchedAt))
            }.font(.system(size: 10)).foregroundStyle(.secondary)
        }
        .padding(16)
        .background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(.white.opacity(0.07)))
    }
}

// Scroll-edge gradients follow Bubo's ShadowScrollView behavior.
private struct ScrollContentFrame: PreferenceKey {
    static var defaultValue: CGRect = .zero
    static func reduce(value: inout CGRect, nextValue: () -> CGRect) { value = nextValue() }
}
struct ShadowScrollView<Content: View>: View {
    var axis: Axis.Set = .vertical
    var showsIndicators = true
    @ViewBuilder var content: () -> Content
    @State private var coordinateID = UUID()
    @State private var contentFrame: CGRect = .zero
    var body: some View {
        GeometryReader { viewport in
            let horizontal = axis == .horizontal
            let offset = max(0, horizontal ? -contentFrame.minX : -contentFrame.minY)
            let contentSize = horizontal ? contentFrame.width : contentFrame.height
            let viewportSize = horizontal ? viewport.size.width : viewport.size.height
            let overflow = max(0, contentSize - viewportSize)
            ScrollView(axis, showsIndicators: showsIndicators) {
                content().background(GeometryReader { geometry in
                    Color.clear.preference(key: ScrollContentFrame.self,
                        value: geometry.frame(in: .named(coordinateID)))
                })
            }
            .coordinateSpace(name: coordinateID)
            .onPreferenceChange(ScrollContentFrame.self) { contentFrame = $0 }
            .overlay(alignment: horizontal ? .leading : .top) {
                LinearGradient(colors: [.black.opacity(0.18), .clear],
                    startPoint: horizontal ? .leading : .top, endPoint: horizontal ? .trailing : .bottom)
                    .frame(width: horizontal ? min(36, viewportSize / 2) : nil,
                           height: horizontal ? nil : min(36, viewportSize / 2))
                    .opacity(overflow > 0.5 ? min(1, offset / 24) : 0)
                    .allowsHitTesting(false)
            }
            .overlay(alignment: horizontal ? .trailing : .bottom) {
                LinearGradient(colors: [.clear, .black.opacity(0.18)],
                    startPoint: horizontal ? .leading : .top, endPoint: horizontal ? .trailing : .bottom)
                    .frame(width: horizontal ? min(36, viewportSize / 2) : nil,
                           height: horizontal ? nil : min(36, viewportSize / 2))
                    .opacity(overflow - offset > 24 ? 1 : 0)
                    .allowsHitTesting(false)
            }
        }
    }
}

struct OverviewView: View {
    @ObservedObject var store: CapacityStore
    @State private var pendingDelete: CapacityAccount?
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Your accounts. One view.").font(.system(size: 28, weight: .semibold, design: .rounded))
                    Text("\(store.accounts.count) accounts across Claude, Codex and Cursor · percentages show capacity used")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer()
                if !store.hidden.isEmpty {
                    Menu("Hidden (\(store.hidden.count))") {
                        ForEach(store.hidden.sorted(by: { $0.value < $1.value }), id: \.key) { id, label in
                            Button("Restore \(label)") { store.refresh(action: ["--restore", id]) }
                        }
                    }.fixedSize()
                }
                Button { store.refresh(force: true) } label: {
                    Label(store.refreshing ? "Refreshing…" : "Refresh", systemImage: "arrow.clockwise")
                }.disabled(store.refreshing).keyboardShortcut("r", modifiers: .command)
            }
            if let error = store.error { Text(error).font(.caption).foregroundStyle(.orange) }
            if store.accounts.isEmpty {
                ProgressView("Discovering your accounts…").frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ShadowScrollView {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(minimum: 220), spacing: 16, alignment: .top), count: 4), alignment: .leading, spacing: 16) {
                        ForEach(store.accounts) { account in
                            AccountCard(account: account, showAllWindows: false, roundIcons: store.roundIcons)
                                .overlay(alignment: .topTrailing) {
                                    Menu {
                                        Button("Hide from Mako") { store.refresh(action: ["--hide", account.id]) }
                                        if account.proxyRef != nil {
                                            Button("Delete from \(account.provider) proxy…", role: .destructive) { pendingDelete = account }
                                        }
                                    } label: { Image(systemName: "ellipsis") }
                                    .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                                    .help("Remove account").padding(12)
                                }
                        }
                    }
                }
            }
            HStack {
                Text("Usage refreshes every 5 minutes. Credentials stay with your provider apps and proxies.")
                Spacer()
                Button("Proxy accounts") {
                    if let url = URL(string: ProxySettings.base + "/management.html") { NSWorkspace.shared.open(url) }
                }
            }.font(.caption).foregroundStyle(.secondary)
        }
        .padding(24)
        .alert("Delete \(pendingDelete?.email ?? "account")?", isPresented: Binding(get: { pendingDelete != nil }, set: { if !$0 { pendingDelete = nil } }), presenting: pendingDelete) { account in
            Button("Delete", role: .destructive) { store.refresh(action: ["--delete", account.id]) }
            Button("Cancel", role: .cancel) {}
        } message: { account in
            Text("This removes the credentials from the \(account.provider) proxy. You cannot undo it. Sign in again to add the account back.")
        }
        .frame(minWidth: 1040, minHeight: 550)
        .background(Color(nsColor: .windowBackgroundColor))
        .preferredColorScheme(.dark)
    }
}

struct DockSurface: Shape {
    var edge: String
    func path(in rect: CGRect) -> Path {
        if edge == "floating" { return Path(roundedRect: rect, cornerRadius: 24) }
        let vertical = edge == "left" || edge == "right"
        let w = vertical ? rect.width : rect.height
        let h = vertical ? rect.height : rect.width
        var path = Path()
        path.move(to: CGPoint(x: w, y: 0))
        path.addQuadCurve(to: CGPoint(x: w - 26, y: 26), control: CGPoint(x: w, y: 26))
        path.addLine(to: CGPoint(x: 24, y: 24))
        path.addQuadCurve(to: CGPoint(x: 0, y: 48), control: CGPoint(x: 0, y: 24))
        path.addLine(to: CGPoint(x: 0, y: h - 48))
        path.addQuadCurve(to: CGPoint(x: 24, y: h - 24), control: CGPoint(x: 0, y: h - 24))
        path.addLine(to: CGPoint(x: w - 26, y: h - 24))
        path.addQuadCurve(to: CGPoint(x: w, y: h), control: CGPoint(x: w, y: h - 26))
        path.closeSubpath()
        if edge == "left" { return path.applying(CGAffineTransform(a: -1, b: 0, c: 0, d: 1, tx: w, ty: 0)) }
        if edge == "bottom" { return path.applying(CGAffineTransform(a: 0, b: 1, c: -1, d: 0, tx: h, ty: 0)) }
        if edge == "top" { return path.applying(CGAffineTransform(a: 0, b: -1, c: -1, d: 0, tx: h, ty: w)) }
        return path
    }
}

/// A card with a tail on one side that points at the dock. `at` is where the tail sits along that side.
struct DetailBubble: Shape {
    var tail: Edge = .trailing
    var at: CGFloat?
    init(pointsLeft: Bool) { tail = pointsLeft ? .leading : .trailing }
    init(tail: Edge, at: CGFloat? = nil) { self.tail = tail; self.at = at }

    func path(in rect: CGRect) -> Path {
        // A tail on the top or bottom is the side tail drawn with x and y swapped.
        guard tail == .top || tail == .bottom else { return sidePath(in: rect, left: tail == .leading) }
        let swapped = CGRect(x: 0, y: 0, width: rect.height, height: rect.width)
        return sidePath(in: swapped, left: tail == .top).applying(CGAffineTransform(a: 0, b: 1, c: 1, d: 0, tx: 0, ty: 0))
    }

    func sidePath(in rect: CGRect, left pointsLeft: Bool) -> Path {
        let radius: CGFloat = 20
        let tail: CGFloat = 20
        let right = rect.width - tail
        let mid = min(max(at ?? rect.midY, radius + 30), rect.height - radius - 30)
        var path = Path()
        path.move(to: CGPoint(x: radius, y: 0))
        path.addLine(to: CGPoint(x: right - radius, y: 0))
        path.addQuadCurve(to: CGPoint(x: right, y: radius), control: CGPoint(x: right, y: 0))
        path.addLine(to: CGPoint(x: right, y: mid - 30))
        path.addCurve(to: CGPoint(x: rect.width, y: mid), control1: CGPoint(x: right, y: mid - 16), control2: CGPoint(x: rect.width, y: mid - 8))
        path.addCurve(to: CGPoint(x: right, y: mid + 30), control1: CGPoint(x: rect.width, y: mid + 8), control2: CGPoint(x: right, y: mid + 16))
        path.addLine(to: CGPoint(x: right, y: rect.height - radius))
        path.addQuadCurve(to: CGPoint(x: right - radius, y: rect.height), control: CGPoint(x: right, y: rect.height))
        path.addLine(to: CGPoint(x: radius, y: rect.height))
        path.addQuadCurve(to: CGPoint(x: 0, y: rect.height - radius), control: CGPoint(x: 0, y: rect.height))
        path.addLine(to: CGPoint(x: 0, y: radius))
        path.addQuadCurve(to: CGPoint(x: radius, y: 0), control: .zero)
        path.closeSubpath()
        return pointsLeft ? path.applying(CGAffineTransform(a: -1, b: 0, c: 0, d: 1, tx: rect.width, ty: 0)) : path
    }
}

/// Where a card opens next to a dock: beside a side dock, above a bottom dock, below a top dock.
/// The tail points at the pointer, so it lands on the hovered ring.
struct DetailPlacement {
    let dock: NSRect, edge: String, screen: NSRect, mouse: NSPoint
    var vertical: Bool { edge == "top" || edge == "bottom" }
    var tail: Edge {
        if edge == "bottom" { return .bottom }
        if edge == "top" { return .top }
        return dock.minX - 360 < screen.minX ? .leading : .trailing
    }
    /// The tail position inside the card, set by `origin`.
    /// Cards are 330 wide plus 8 padding each side when the tail is on the top or bottom.
    var tailAt: CGFloat? { vertical ? mouse.x - x(width: 346) : nil }

    func x(width: CGFloat) -> CGFloat {
        min(max(mouse.x - width / 2, screen.minX + 4), screen.maxX - width - 4)
    }

    func origin(size: NSSize) -> (CGFloat, CGFloat) {
        switch tail {
        case .bottom: return (x(width: size.width), dock.maxY + 4)
        case .top: return (x(width: size.width), dock.minY - size.height - 4)
        default:
            let x = tail == .trailing ? dock.minX - size.width - 8 : dock.maxX + 8
            return (x, min(screen.maxY - size.height, max(screen.minY, mouse.y - size.height / 2)))
        }
    }
}

struct RailView: View {
    @ObservedObject var store: CapacityStore
    @ObservedObject var agents: AgentStore
    var showOverview: () -> Void
    var showSettings: () -> Void
    var hover: (CapacityAccount?) -> Void
    var hoverAgent: (AgentItem?) -> Void
    var horizontal: Bool { store.dockEdge == "top" || store.dockEdge == "bottom" }
    /// Two icons at the top of the dock: accounts and agents.
    var modeSwitch: some View {
        HStack(spacing: 2) {
            ForEach([("capacity", "gauge.with.dots.needle.50percent", "Accounts"), ("agents", "sparkles", "Agents")], id: \.0) { mode, icon, label in
                Button { store.dockMode = mode } label: {
                    Image(systemName: icon).font(.system(size: 11, weight: .semibold)).frame(width: 26, height: 20)
                        .background(store.dockMode == mode ? Color.white.opacity(0.18) : .clear, in: RoundedRectangle(cornerRadius: 6))
                        .foregroundStyle(store.dockMode == mode ? Color.white : Color.secondary)
                        .contentShape(Rectangle())
                }.buttonStyle(.plain).help(label).accessibilityLabel(label)
            }
        }.padding(2).background(Color.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 8))
    }
    @ViewBuilder var top: some View {
        if store.agentsInDock { modeSwitch } else {
            Image(systemName: "line.3.horizontal").font(.system(size: horizontal ? 10 : 12)).foregroundStyle(.secondary).help("Drag to attach to a screen edge")
        }
    }
    @ViewBuilder var cells: some View {
        if store.showsAgents {
            if agents.agents.isEmpty { NoAgents() }
            ForEach(agents.agents) { agent in
                AgentCell(agent: agent, horizontal: horizontal, focus: { agents.focus(agent) }, hover: hoverAgent)
            }
        } else {
            ForEach(store.accounts) { cell($0) }
        }
    }
    func cursorQuotas(_ account: CapacityAccount) -> some View {
        VStack(spacing: 1) {
            ForEach(account.windows) { window in
                HStack(spacing: 2) {
                    Text(window.label == "Cursor Models" ? "Models" : window.label == "Other Models" ? "Other" : window.label == "Grok Bot" ? "Grok" : "Spend")
                        .foregroundStyle(.white.opacity(0.65))
                    Spacer(minLength: 0)
                    Text("\(Int(window.used))%").monospacedDigit()
                        .foregroundStyle(window.used >= 100 ? Color.red : window.used >= 85 ? .orange : .green)
                }
            }
        }.font(.system(size: 9, weight: .medium)).frame(width: 59)
    }
    func cell(_ account: CapacityAccount) -> some View {
        Button(action: showOverview) {
            if horizontal {
                VStack(spacing: 4) {
                    AccountRing(account: account, size: 36, dockStyle: true, round: store.roundIcons)
                    if store.showNames { Text(account.title).font(.system(size: 10, weight: .semibold)).lineLimit(1) }
                    if account.provider == "Cursor" && !account.windows.isEmpty {
                        cursorQuotas(account)
                    } else {
                        Text(account.used.map { "\(Int($0))%" } ?? "—").font(.system(size: 13, weight: .semibold, design: .rounded)).foregroundStyle(account.signal)
                    }
                }.frame(width: 72)
            } else {
                VStack(spacing: 3) {
                    AccountRing(account: account, size: account.provider == "Cursor" ? 36 : 42, dockStyle: true, round: store.roundIcons)
                    if account.provider == "Cursor" && !account.windows.isEmpty {
                        cursorQuotas(account)
                    } else {
                        Text(account.used.map { "\(Int($0))%" } ?? "—")
                            .font(.system(size: 15, weight: .medium)).monospacedDigit().foregroundStyle(account.signal)
                    }
                    if store.showNames { Text(account.title).font(.system(size: 9, weight: .medium)).foregroundStyle(.white.opacity(0.6)).lineLimit(1) }
                }.frame(width: 64, height: (store.showNames ? 78 : 66) + (account.provider == "Cursor" ? CGFloat(max(3, account.windows.count) - 2) * 16 : 0))
            }
        }.buttonStyle(.plain).onHover { inside in hover(inside ? account : nil) }
            .help("\(account.provider) · \(account.email) · \(account.stateLabel)")
    }
    var body: some View {
        GeometryReader { geometry in
            railContent
                .frame(width: geometry.size.width / store.dockScale, height: geometry.size.height / store.dockScale)
                .scaleEffect(store.dockScale, anchor: .topLeading)
        }
        .contextMenu {
            Button("Dock settings…", action: showSettings); Button("All accounts", action: showOverview)
            if store.agentsInDock { Button(store.showsAgents ? "Show accounts" : "Show agents") { store.dockMode = store.showsAgents ? "capacity" : "agents" } }
        }
    }
    var railContent: some View {
        Group {
            if horizontal {
                HStack(spacing: 8) {
                    top
                    ShadowScrollView(axis: .horizontal, showsIndicators: false) {
                        HStack(spacing: 8) { cells }
                    }
                    Button(action: showOverview) { Image(systemName: "square.grid.2x2.fill") }.buttonStyle(.plain)
                    Button(action: showSettings) { Image(systemName: "gearshape") }.buttonStyle(.plain).help("Dock settings")
                }.padding(.horizontal, 34).padding(.vertical, 14)
            } else {
                VStack(spacing: 8) {
                    top.padding(.top, store.dockEdge == "floating" ? 12 : 32)
                    ShadowScrollView(showsIndicators: false) {
                        VStack(spacing: 6) { cells }.padding(.horizontal, 12)
                    }
                    HStack(spacing: 14) {
                        Button(action: showOverview) { Image(systemName: "square.grid.2x2.fill") }.help("Open all accounts")
                        Button(action: showSettings) { Image(systemName: "gearshape") }.help("Dock settings")
                    }.font(.system(size: 13)).buttonStyle(.plain)
                        .padding(.bottom, store.dockEdge == "floating" ? 12 : 32)
                }
            }
        }
        .foregroundStyle(.white)
        .background(DockSurface(edge: store.dockEdge).fill(Color(white: 0.065).opacity(store.dockOpacity)))
        .overlay(DockSurface(edge: store.dockEdge).stroke(.white.opacity(0.12)))
        .preferredColorScheme(.dark)
    }
}

/// Shared with the collector and CLI: ~/.mako-capacity/settings.json.
enum ProxySettings {
    static var file: URL {
        let home = ProcessInfo.processInfo.environment["MAKO_CAPACITY_HOME"].map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".mako-capacity")
        return home.appendingPathComponent("settings.json")
    }
    static func read() -> [String: Any] {
        (try? Data(contentsOf: file)).flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
    }
    /// The CLIProxyAPI address: a configured remote server, else the local Docker port.
    static var base: String {
        let settings = read()
        if let url = settings["PROXY_URL"] as? String, !url.isEmpty { return url }
        return "http://127.0.0.1:\(settings["CLAUDE_PROXY_PORT"] as? String ?? "8317")"
    }
    /// Save a remote proxy, or clear it with an empty URL. Returns an error message or nil.
    static func save(url rawURL: String, key: String) -> String? {
        let url = rawURL.trimmingCharacters(in: .whitespaces).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        var settings = read()
        if url.isEmpty {
            settings["PROXY_URL"] = nil
            settings["PROXY_MANAGEMENT_KEY"] = nil
        } else {
            guard let parsed = URL(string: url), ["http", "https"].contains(parsed.scheme ?? ""), parsed.host != nil else {
                return "Use an address like https://server:8317."
            }
            guard !key.trimmingCharacters(in: .whitespaces).isEmpty else { return "A remote proxy needs its management key." }
            settings["PROXY_URL"] = url
            settings["PROXY_MANAGEMENT_KEY"] = key.trimmingCharacters(in: .whitespaces)
        }
        do {
            try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
            try JSONSerialization.data(withJSONObject: settings, options: [.prettyPrinted, .sortedKeys]).write(to: file)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
        } catch {
            return "Could not save settings: \(error.localizedDescription)"
        }
        return nil
    }
}

/// All accounts and Settings open in the GPUIX app when Bun is installed, so the dock and the terminal share one dashboard.
/// Without Bun, or while its packages install the first time, the Swift windows open instead.
@MainActor
enum Dashboard {
    static var process: Process?
    static var view: String?
    static var installing = false
    /// The newest Bun found, because an older Bun cannot read the lockfile a newer one wrote.
    static let bun: String? = {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let found = ["\(home)/.bun/bin/bun", "/opt/homebrew/bin/bun", "/usr/local/bin/bun"].filter { FileManager.default.isExecutableFile(atPath: $0) }
        func version(_ path: String) -> [Int] {
            let probe = Process(), pipe = Pipe()
            probe.executableURL = URL(fileURLWithPath: path)
            probe.arguments = ["--version"]
            probe.standardOutput = pipe
            guard (try? probe.run()) != nil else { return [] }
            probe.waitUntilExit()
            let text = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            return text.trimmingCharacters(in: .whitespacesAndNewlines).split(separator: ".").map { Int($0) ?? 0 }
        }
        return found.max { version($0).lexicographicallyPrecedes(version($1)) }
    }()
    /// A writable copy of the bundled app, beside settings.json, where its packages can install.
    static var folder: URL { ProxySettings.file.deletingLastPathComponent().appendingPathComponent("gpuix-app") }

    static func open(view: String) -> Bool {
        guard let bun, let resources = Bundle.main.resourceURL,
              FileManager.default.fileExists(atPath: resources.appendingPathComponent("gpuix-app/app.tsx").path) else { return false }
        if let process, process.isRunning {
            if self.view == view {
                NSRunningApplication(processIdentifier: process.processIdentifier)?.activate()
                return true
            }
            process.terminate()
        }
        guard ready(source: resources.appendingPathComponent("gpuix-app"), bun: bun) else { return false }
        let child = Process()
        child.executableURL = URL(fileURLWithPath: bun)
        child.arguments = ["app.tsx", "--view=\(view)"]
        child.currentDirectoryURL = folder
        var environment = ProcessInfo.processInfo.environment
        environment["MAKO_ROOT"] = resources.path
        environment["MAKO_DOCK_DEFAULTS"] = Bundle.main.bundleIdentifier ?? "com.mako-l.capacity"
        child.environment = environment
        do { try child.run() } catch { return false }
        process = child
        self.view = view
        return true
    }

    /// Copies changed sources into the folder. Returns false while `bun install` still has to run.
    static func ready(source: URL, bun: String) -> Bool {
        let files = FileManager.default
        try? files.createDirectory(at: folder, withIntermediateDirectories: true)
        var packagesChanged = false
        for name in (try? files.contentsOfDirectory(atPath: source.path)) ?? [] {
            let from = source.appendingPathComponent(name), to = folder.appendingPathComponent(name)
            if files.contentsEqual(atPath: from.path, andPath: to.path) { continue }
            try? files.removeItem(at: to)
            try? files.copyItem(at: from, to: to)
            if name == "bun.lock" || name == "package.json" { packagesChanged = true }
        }
        if !packagesChanged && files.fileExists(atPath: folder.appendingPathComponent("node_modules").path) { return true }
        if !installing {
            installing = true
            let install = Process(), folder = folder
            install.executableURL = URL(fileURLWithPath: bun)
            install.arguments = ["install", "--frozen-lockfile"]
            install.currentDirectoryURL = folder
            install.terminationHandler = { finished in
                // A lockfile this Bun cannot read falls back to the exact versions in package.json.
                if finished.terminationStatus != 0 {
                    let retry = Process()
                    retry.executableURL = URL(fileURLWithPath: bun)
                    retry.arguments = ["install"]
                    retry.currentDirectoryURL = folder
                    try? retry.run()
                    retry.waitUntilExit()
                }
                Task { @MainActor in installing = false }
            }
            if (try? install.run()) == nil { installing = false }
        }
        return false
    }
}

/// The GPUIX settings window changes dock settings with `defaults write`. This applies them to the running dock.
final class DefaultsWatcher: NSObject {
    static let keys = ["dockScale", "dockOpacity", "roundIcons", "showNames", "dockEdge", "agentsInDock"]
    let changed: @MainActor () -> Void
    init(changed: @escaping @MainActor () -> Void) {
        self.changed = changed
        super.init()
        for key in Self.keys { UserDefaults.standard.addObserver(self, forKeyPath: key, options: [.new], context: nil) }
    }
    override func observeValue(forKeyPath keyPath: String?, of object: Any?, change: [NSKeyValueChangeKey: Any]?, context: UnsafeMutableRawPointer?) {
        Task { @MainActor in self.changed() }
    }
}

struct DockSettingsView: View {
    @ObservedObject var store: CapacityStore
    var attach: (String) -> Void
    @State private var proxyURL = ProxySettings.read()["PROXY_URL"] as? String ?? ""
    @State private var proxyKey = ProxySettings.read()["PROXY_MANAGEMENT_KEY"] as? String ?? ""
    @State private var proxyMessage = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            Text("Dock settings").font(.title2.bold())
            Text("Changes apply immediately and are saved.").foregroundStyle(.secondary)
            VStack(alignment: .leading) {
                Text("Size · \(Int((store.dockScale * 100).rounded()))%")
                Slider(value: $store.dockScale, in: 0.65...1.4, step: 0.05)
            }
            Text("The dock fits your accounts and scrolls when needed.").font(.caption).foregroundStyle(.secondary)
            Picker("Icon shape", selection: $store.roundIcons) {
                Text("Rounded square").tag(false)
                Text("Circle").tag(true)
            }.pickerStyle(.segmented)
            Toggle("Show account names", isOn: $store.showNames)
            VStack(alignment: .leading) {
                Text("Background opacity · \(Int((store.dockOpacity * 100).rounded()))%")
                Slider(value: $store.dockOpacity, in: 0.25...1, step: 0.05)
            }
            Picker("Screen edge", selection: Binding(get: { store.dockEdge }, set: attach)) {
                ForEach(["right", "left", "top", "bottom", "floating"], id: \.self) { Text($0.capitalized).tag($0) }
            }
            VStack(alignment: .leading, spacing: 6) {
                Picker("Agents", selection: $store.agentsInDock) {
                    Text("Own dock").tag(false)
                    Text("In this dock").tag(true)
                }.pickerStyle(.segmented)
                Text("In this dock, the switch at the top moves between accounts and agents.").font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                Spacer()
                Button("Restore defaults") {
                    store.dockScale = 1; store.dockLength = 820; store.roundIcons = false
                    store.showNames = true; store.dockOpacity = 1; attach("right")
                }
            }
            Divider()
            VStack(alignment: .leading, spacing: 8) {
                Text("Proxy server").font(.headline)
                Text("Leave the address empty to use the local Docker proxy.").font(.caption).foregroundStyle(.secondary)
                TextField("https://server:8317", text: $proxyURL).textFieldStyle(.roundedBorder)
                SecureField("Management key", text: $proxyKey).textFieldStyle(.roundedBorder)
                HStack {
                    Text(proxyMessage).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    Button("Save") {
                        if let error = ProxySettings.save(url: proxyURL, key: proxyKey) {
                            proxyMessage = error
                        } else {
                            proxyMessage = proxyURL.isEmpty ? "Using the local Docker proxy." : "Saved. Accounts reload from this server."
                            store.refresh(force: true)
                        }
                    }
                }
            }
        }.padding(26).frame(width: 390).background(Color(nsColor: .windowBackgroundColor)).preferredColorScheme(.dark)
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    let store = CapacityStore()
    var overview: NSWindow!
    var rail: NSPanel!
    var detail: NSPanel?
    var detailAccountID: String?
    var settings: NSWindow?
    var layoutSubscription: AnyCancellable?
    var statusItem: NSStatusItem!
    var closeDetailWork: DispatchWorkItem?
    var dockingWork: DispatchWorkItem?
    var placingRail = false
    var agentDock: AgentDockController!
    var modeSubscription: AnyCancellable?
    var defaultsWatcher: DefaultsWatcher?
    var mergedState: [String] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.appearance = NSAppearance(named: .darkAqua)
        overview = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1120, height: 880), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        overview.title = "Mako Capacity"
        overview.isReleasedWhenClosed = false
        overview.contentView = NSHostingView(rootView: OverviewView(store: store))
        overview.center()
        overview.setFrameAutosaveName("MakoCapacityOverview")
        rail = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 88, height: 820), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        rail.hasShadow = false
        rail.isOpaque = false
        rail.backgroundColor = .clear
        rail.level = .floating
        rail.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        rail.isMovableByWindowBackground = true
        rail.hidesOnDeactivate = false
        rail.delegate = self
        agentDock = AgentDockController(capacity: store)
        agentDock.host = rail
        positionRail(edge: store.dockEdge)
        rail.contentView = NSHostingView(rootView: RailView(store: store, agents: agentDock.store, showOverview: { [weak self] in self?.showOverview() },
            showSettings: { [weak self] in self?.showSettings() }, hover: { [weak self] in self?.showDetail($0) },
            hoverAgent: { [weak self] in self?.agentDock.showDetail($0) }))
        layoutSubscription = Publishers.CombineLatest3(store.$dockScale, store.$showNames, store.$accounts)
            .dropFirst().receive(on: RunLoop.main).sink { [weak self] _, _, accounts in
                guard let self else { return }
                if let id = self.detailAccountID, !accounts.contains(where: { $0.id == id }) {
                    self.detail?.orderOut(nil)
                    self.detailAccountID = nil
                }
                self.repositionRail()
            }
        // Switching what the dock shows, or agents coming and going in it, resizes the dock.
        modeSubscription = Publishers.CombineLatest3(store.$agentsInDock, store.$dockMode, agentDock.store.$agents)
            .dropFirst().receive(on: RunLoop.main).sink { [weak self] inDock, mode, _ in
                guard let self else { return }
                let state = [inDock ? "1" : "0", mode]
                let switched = self.mergedState != state
                if switched {
                    self.mergedState = state
                    self.showDetail(nil)
                    self.agentDock.closeCards()
                    self.agentDock.syncMerged()
                }
                // Agents coming and going resize the dock only while it shows them.
                if switched || self.store.showsAgents { self.repositionRail() }
            }
        rail.orderFrontRegardless()
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusItem.button?.image = NSImage(systemSymbolName: "gauge.with.dots.needle.50percent", accessibilityDescription: "Mako Capacity")
        let menu = NSMenu()
        menu.addItem(withTitle: "All accounts", action: #selector(showOverview), keyEquivalent: "")
        menu.addItem(withTitle: "Dock settings…", action: #selector(showSettings), keyEquivalent: ",")
        menu.addItem(withTitle: "Show / hide capacity dock", action: #selector(toggleRail), keyEquivalent: "")
        let edges = NSMenuItem(title: "Attach to screen", action: nil, keyEquivalent: "")
        let edgesMenu = NSMenu()
        for edge in ["Right", "Left", "Top", "Bottom"] {
            let item = edgesMenu.addItem(withTitle: edge, action: #selector(attachRail(_:)), keyEquivalent: "")
            item.representedObject = edge.lowercased()
            item.target = self
        }
        edges.submenu = edgesMenu
        menu.addItem(edges)
        menu.addItem(.separator())
        menu.addItem(withTitle: "Show / hide agents dock", action: #selector(toggleAgents), keyEquivalent: "")
        let agentEdges = NSMenuItem(title: "Attach agents dock", action: nil, keyEquivalent: "")
        let agentEdgesMenu = NSMenu()
        for edge in ["Left", "Right", "Top", "Bottom"] {
            let item = agentEdgesMenu.addItem(withTitle: edge, action: #selector(attachAgents(_:)), keyEquivalent: "")
            item.representedObject = edge.lowercased()
            item.target = self
        }
        agentEdges.submenu = agentEdgesMenu
        menu.addItem(agentEdges)
        let idle = menu.addItem(withTitle: "Show idle agents", action: #selector(toggleIdleAgents(_:)), keyEquivalent: "")
        idle.state = AgentStore.showIdle() ? .on : .off
        let activity = menu.addItem(withTitle: "Show recent activity", action: #selector(toggleAgentActivity(_:)), keyEquivalent: "")
        activity.state = AgentStore.showActivity() ? .on : .off
        menu.addItem(.separator())
        menu.addItem(withTitle: "Refresh", action: #selector(refresh), keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit Mako Capacity", action: #selector(quit), keyEquivalent: "q")
        for item in menu.items { item.target = self }
        statusItem.menu = menu
        let mainMenu = NSMenu()
        let appMenuItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "All accounts", action: #selector(showOverview), keyEquivalent: "0").target = self
        appMenu.addItem(withTitle: "Dock settings…", action: #selector(showSettings), keyEquivalent: ",").target = self
        appMenu.addItem(withTitle: "Refresh", action: #selector(refresh), keyEquivalent: "r").target = self
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit Mako Capacity", action: #selector(quit), keyEquivalent: "q").target = self
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)
        NSApp.mainMenu = mainMenu
        NotificationCenter.default.addObserver(self, selector: #selector(repositionRail), name: NSApplication.didChangeScreenParametersNotification, object: nil)
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(repositionRail), name: NSWorkspace.didWakeNotification, object: nil)
        let args = CommandLine.arguments
        if args.contains("--settings") { showSwiftSettings() }
        if args.contains("--overview") || args.contains("--screenshot") { showSwiftOverview() }
        defaultsWatcher = DefaultsWatcher { [weak self] in self?.applyDefaults() }
        if let index = args.firstIndex(of: "--screenshot"), args.count > index + 1 {
            let path = args[index + 1]
            DispatchQueue.main.asyncAfter(deadline: .now() + 4) { [weak self] in self?.capture(path) }
        }
    }

    @objc func showOverview() {
        if Dashboard.open(view: "accounts") { return }
        showSwiftOverview()
    }
    func showSwiftOverview() { overview.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    @objc func showSettings() {
        showDetail(nil)
        if Dashboard.open(view: "settings") { return }
        showSwiftSettings()
    }
    func showSwiftSettings() {
        if settings == nil {
            let view = NSHostingView(rootView: DockSettingsView(store: store, attach: { [weak self] edge in self?.positionRail(edge: edge) }))
            let window = NSWindow(contentRect: NSRect(origin: .zero, size: view.fittingSize), styleMask: [.titled, .closable], backing: .buffered, defer: false)
            window.title = "Mako Capacity — Dock settings"
            window.isReleasedWhenClosed = false
            window.contentView = view
            window.center()
            settings = window
        }
        settings?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
    /// Takes dock settings that another process wrote, such as the GPUIX settings window.
    func applyDefaults() {
        let defaults = UserDefaults.standard
        if let value = defaults.object(forKey: "dockScale") as? Double, value != store.dockScale { store.dockScale = value }
        if let value = defaults.object(forKey: "dockOpacity") as? Double, value != store.dockOpacity { store.dockOpacity = value }
        if let value = defaults.object(forKey: "showNames") as? Bool, value != store.showNames { store.showNames = value }
        if defaults.bool(forKey: "roundIcons") != store.roundIcons { store.roundIcons = defaults.bool(forKey: "roundIcons") }
        if defaults.bool(forKey: "agentsInDock") != store.agentsInDock { store.agentsInDock = defaults.bool(forKey: "agentsInDock") }
        if let edge = defaults.string(forKey: "dockEdge"), edge != store.dockEdge { positionRail(edge: edge) }
    }
    @objc func toggleRail() { if rail.isVisible { rail.orderOut(nil) } else { rail.orderFrontRegardless() } }
    @objc func refresh() { store.refresh(force: true) }
    @objc func repositionRail() {
        positionRail(edge: store.dockEdge)
        agentDock?.place(edge: agentDock.store.edge)
    }
    @objc func toggleIdleAgents(_ item: NSMenuItem) {
        let show = !AgentStore.showIdle()
        agentDock.store.setSetting("SHOW_IDLE_AGENTS", show)
        item.state = show ? .on : .off
    }
    @objc func toggleAgentActivity(_ item: NSMenuItem) {
        let show = !AgentStore.showActivity()
        agentDock.store.setSetting("SHOW_AGENT_ACTIVITY", show)
        item.state = show ? .on : .off
    }
    @objc func toggleAgents() {
        // With agents in the capacity dock, showing their own dock moves them back out.
        if store.agentsInDock { store.agentsInDock = false; agentDock.setVisible(true); return }
        agentDock.setVisible(!agentDock.visible)
    }
    @objc func attachAgents(_ item: NSMenuItem) {
        store.agentsInDock = false
        agentDock.place(edge: item.representedObject as? String ?? "left")
        agentDock.setVisible(true)
    }
    @objc func attachRail(_ item: NSMenuItem) { positionRail(edge: item.representedObject as? String ?? "right"); rail.orderFrontRegardless() }
    @objc func quit() { NSApp.terminate(nil) }
    func applicationWillTerminate(_ notification: Notification) { Dashboard.process?.terminate() }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showOverview(); return true }

    func positionRail(edge: String, screen preferred: NSScreen? = nil) {
        guard let screen = preferred ?? rail?.screen ?? NSScreen.main else { return }
        placingRail = true
        store.dockEdge = edge
        UserDefaults.standard.set(edge, forKey: "dockEdge")
        let horizontal = edge == "top" || edge == "bottom"
        let scale = store.dockScale
        let agentCount = store.showsAgents ? agentDock?.store.agents.count ?? 0 : nil
        let count = max(1, agentCount ?? store.accounts.count)
        let padding: CGFloat = edge == "floating" ? 12 : 32
        let cells = agentCount.map { CGFloat(max(1, $0) * 78) } ?? store.accounts.reduce(CGFloat(0)) { total, account in
            total + (store.showNames ? 78 : 66) + (account.provider == "Cursor" ? CGFloat(max(3, account.windows.count) - 2) * 16 : 0)
        }
        // The switch takes more room than the drag handle it replaces.
        let switchRoom: CGFloat = store.agentsInDock ? (horizontal ? 50 : 10) : 0
        let length = switchRoom + (horizontal ? CGFloat(130 + count * 72 + (count - 1) * 8) : padding * 2 + 44 + max(cells, store.showNames ? 78 : 66) + CGFloat((count - 1) * 6))
        let size = horizontal ? NSSize(width: min(length * scale, screen.visibleFrame.width), height: 114 * scale) : NSSize(width: 88 * scale, height: min(length * scale, screen.visibleFrame.height - 24))
        let offset = UserDefaults.standard.object(forKey: "dockOffset") as? Double ?? 0.5
        var origin = NSPoint(x: screen.visibleFrame.minX + (screen.visibleFrame.width - size.width) * offset,
                             y: screen.visibleFrame.minY + (screen.visibleFrame.height - size.height) * offset)
        switch edge {
        case "right": origin.x = screen.frame.maxX - size.width
        case "left": origin.x = screen.frame.minX
        case "top": origin.y = screen.visibleFrame.maxY - size.height
        case "bottom": origin.y = screen.visibleFrame.minY
        default:
            origin.x = UserDefaults.standard.object(forKey: "floatingX") as? Double ?? origin.x
            origin.y = UserDefaults.standard.object(forKey: "floatingY") as? Double ?? origin.y
            origin.x = max(screen.visibleFrame.minX, min(origin.x, screen.visibleFrame.maxX - size.width))
            origin.y = max(screen.visibleFrame.minY, min(origin.y, screen.visibleFrame.maxY - size.height))
        }
        rail.setFrame(NSRect(origin: origin, size: size), display: true)
        placingRail = false
    }

    func windowDidMove(_ notification: Notification) {
        guard let window = notification.object as? NSWindow, window === rail, !placingRail else { return }
        closeDetailWork?.cancel()
        detail?.orderOut(nil)
        scheduleDocking()
    }

    func scheduleDocking() {
        dockingWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            if NSEvent.pressedMouseButtons != 0 { self.scheduleDocking(); return }
            guard let screen = self.rail.screen ?? NSScreen.main else { return }
            let frame = self.rail.frame
            let candidates: [(String, CGFloat)] = [("left", abs(frame.minX - screen.frame.minX)), ("right", abs(frame.maxX - screen.frame.maxX)), ("top", abs(frame.maxY - screen.visibleFrame.maxY)), ("bottom", abs(frame.minY - screen.visibleFrame.minY))]
            let nearest = candidates.min(by: { $0.1 < $1.1 })!
            if nearest.1 <= 48 {
                let horizontal = nearest.0 == "top" || nearest.0 == "bottom"
                let span = horizontal ? screen.visibleFrame.width - frame.width : screen.visibleFrame.height - frame.height
                let distance = horizontal ? frame.minX - screen.visibleFrame.minX : frame.minY - screen.visibleFrame.minY
                UserDefaults.standard.set(max(0, min(1, span > 0 ? distance / span : 0.5)), forKey: "dockOffset")
                self.positionRail(edge: nearest.0, screen: screen)
            } else {
                UserDefaults.standard.set(frame.minX, forKey: "floatingX")
                UserDefaults.standard.set(frame.minY, forKey: "floatingY")
                self.positionRail(edge: "floating", screen: screen)
            }
        }
        dockingWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15, execute: work)
    }

    func showDetail(_ account: CapacityAccount?) {
        closeDetailWork?.cancel()
        guard let account else {
            let work = DispatchWorkItem { [weak self] in self?.detail?.orderOut(nil) }
            closeDetailWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: work)
            return
        }
        detailAccountID = account.id
        if detail == nil {
            detail = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
            detail?.hasShadow = false
            detail?.isOpaque = false
            detail?.backgroundColor = .clear
            detail?.level = .floating
            detail?.hidesOnDeactivate = false
            detail?.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        }
        let screen = rail.screen?.visibleFrame ?? NSScreen.main!.visibleFrame
        let mouse = NSEvent.mouseLocation
        let placed = DetailPlacement(dock: rail.frame, edge: store.dockEdge, screen: screen, mouse: mouse)
        let content = AccountCard(account: account, roundIcons: store.roundIcons).frame(width: 330).padding(8)
            .padding(Edge.Set(placed.tail), 20)
            .background(DetailBubble(tail: placed.tail, at: placed.tailAt).fill(Color(white: 0.065)))
            .onHover { [weak self] inside in if inside { self?.closeDetailWork?.cancel() } else { self?.showDetail(nil) } }
            .preferredColorScheme(.dark)
        let view = NSHostingView(rootView: content)
        let size = view.fittingSize
        let (x, y) = placed.origin(size: size)
        detail?.setFrame(NSRect(origin: NSPoint(x: x, y: y), size: size), display: false)
        detail?.contentView = view
        detail?.orderFrontRegardless()
    }

    func capture(_ path: String) {
        guard let view = overview.contentView, let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return }
        view.cacheDisplay(in: view.bounds, to: bitmap)
        if let png = bitmap.representation(using: .png, properties: [:]) { try? png.write(to: URL(fileURLWithPath: path)) }
        if let view = rail.contentView, let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) {
            view.cacheDisplay(in: view.bounds, to: bitmap)
            if let png = bitmap.representation(using: .png, properties: [:]) { try? png.write(to: URL(fileURLWithPath: path + ".dock.png")) }
        }
        let screen = rail.screen ?? NSScreen.main!
        let layout: [String: Any] = ["edge": store.dockEdge, "railMaxX": rail.frame.maxX,
            "screenMaxX": screen.frame.maxX, "railHeight": rail.frame.height,
            "accounts": store.accounts.count, "railWidth": rail.frame.width,
            "scale": store.dockScale, "roundIcons": store.roundIcons]
        if let view = settings?.contentView, let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) {
            view.cacheDisplay(in: view.bounds, to: bitmap)
            if let png = bitmap.representation(using: .png, properties: [:]) { try? png.write(to: URL(fileURLWithPath: path + ".settings.png")) }
        }
        if let data = try? JSONSerialization.data(withJSONObject: layout, options: [.prettyPrinted]) {
            try? data.write(to: URL(fileURLWithPath: path + ".layout.json"))
        }
        overview.orderOut(nil)
    }
}

@main
enum Launcher {
    @MainActor
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        let delegate = AppDelegate()
        app.delegate = delegate
        withExtendedLifetime(delegate) { app.run() }
    }
}
