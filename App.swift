import AppKit
import SwiftUI
import Combine

struct CapacityWindow: Codable, Identifiable {
    let label: String
    let used: Double
    let resetAt: Double?
    let detail: String?
    var id: String { label }
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

struct CapacitySnapshot: Codable {
    let updatedAt: Double
    let accounts: [CapacityAccount]
}

@MainActor
final class CapacityStore: ObservableObject {
    @Published var accounts: [CapacityAccount] = []
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
    private var timer: Timer?

    init() {
        let cache = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Mako Capacity/snapshot.json")
        if let data = try? Data(contentsOf: cache), let snapshot = try? JSONDecoder().decode(CapacitySnapshot.self, from: data) {
            accounts = snapshot.accounts
        }
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }

    func refresh(force: Bool = false) {
        guard !refreshing else { return }
        refreshing = true
        let script = Bundle.main.resourceURL!.appendingPathComponent("collector.py")
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let process = Process()
            let output = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            process.arguments = [script.path] + (force ? ["--refresh"] : [])
            process.standardOutput = output
            process.standardError = FileHandle.nullDevice
            do {
                try process.run()
                let data = output.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                guard process.terminationStatus == 0 else { throw NSError(domain: "Collector", code: Int(process.terminationStatus)) }
                let snapshot = try JSONDecoder().decode(CapacitySnapshot.self, from: data)
                DispatchQueue.main.async {
                    self?.accounts = snapshot.accounts
                    self?.error = nil
                    self?.refreshing = false
                }
            } catch {
                DispatchQueue.main.async {
                    self?.error = "Could not update accounts. Previous readings remain visible."
                    self?.refreshing = false
                }
            }
        }
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
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(account.provider.uppercased()).font(.system(size: 10, weight: .semibold)).foregroundStyle(account.accent)
            HStack(spacing: 12) {
                AccountRing(account: account, size: 40)
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
                    }
                }
                if !account.message.isEmpty {
                    Text(account.message).font(.caption).foregroundStyle(.secondary)
                }
            }
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

struct OverviewView: View {
    @ObservedObject var store: CapacityStore
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Your accounts. One view.").font(.system(size: 28, weight: .semibold, design: .rounded))
                    Text("\(store.accounts.count) accounts across Claude, Codex and Cursor · percentages show capacity used")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer()
                Button { store.refresh(force: true) } label: {
                    Label(store.refreshing ? "Refreshing…" : "Refresh", systemImage: "arrow.clockwise")
                }.disabled(store.refreshing).keyboardShortcut("r", modifiers: .command)
            }
            if let error = store.error { Text(error).font(.caption).foregroundStyle(.orange) }
            if store.accounts.isEmpty {
                ProgressView("Discovering your accounts…").frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(minimum: 220), spacing: 16, alignment: .top), count: 4), alignment: .leading, spacing: 16) {
                        ForEach(store.accounts) { account in
                            AccountCard(account: account, showAllWindows: false)
                        }
                    }
                }
            }
            HStack {
                Text("Usage refreshes every 5 minutes. Credentials stay with your provider apps and proxies.")
                Spacer()
                Button("Claude accounts") { NSWorkspace.shared.open(URL(string: "http://127.0.0.1:8317/management.html")!) }
                Button("Codex accounts") { NSWorkspace.shared.open(URL(string: "http://127.0.0.1:8080")!) }
            }.font(.caption).foregroundStyle(.secondary)
        }
        .padding(24)
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

struct DetailBubble: Shape {
    var pointsLeft: Bool
    func path(in rect: CGRect) -> Path {
        let radius: CGFloat = 20
        let tail: CGFloat = 20
        let right = rect.width - tail
        let mid = rect.midY
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

struct RailView: View {
    @ObservedObject var store: CapacityStore
    var showOverview: () -> Void
    var showSettings: () -> Void
    var hover: (CapacityAccount?) -> Void
    var horizontal: Bool { store.dockEdge == "top" || store.dockEdge == "bottom" }
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
        .contextMenu { Button("Dock settings…", action: showSettings); Button("All accounts", action: showOverview) }
    }
    var railContent: some View {
        Group {
            if horizontal {
                HStack(spacing: 8) {
                    Image(systemName: "line.3.horizontal").font(.system(size: 10)).foregroundStyle(.secondary).help("Drag to attach to a screen edge")
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) { ForEach(store.accounts) { cell($0) } }
                    }
                    Button(action: showOverview) { Image(systemName: "square.grid.2x2.fill") }.buttonStyle(.plain)
                    Button(action: showSettings) { Image(systemName: "gearshape") }.buttonStyle(.plain).help("Dock settings")
                }.padding(.horizontal, 34).padding(.vertical, 14)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "line.3.horizontal").font(.system(size: 12)).foregroundStyle(.secondary)
                        .padding(.top, store.dockEdge == "floating" ? 12 : 32).help("Drag to attach to a screen edge")
                    ScrollView(showsIndicators: false) {
                        VStack(spacing: 6) { ForEach(store.accounts) { cell($0) } }.padding(.horizontal, 12)
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

struct DockSettingsView: View {
    @ObservedObject var store: CapacityStore
    var attach: (String) -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            Text("Dock settings").font(.title2.bold())
            Text("Changes apply immediately and are saved.").foregroundStyle(.secondary)
            VStack(alignment: .leading) {
                Text("Size · \(Int((store.dockScale * 100).rounded()))%")
                Slider(value: $store.dockScale, in: 0.65...1.4, step: 0.05)
            }
            VStack(alignment: .leading) {
                Text("Length · \(Int(store.dockLength)) pt")
                Slider(value: $store.dockLength, in: 400...1100, step: 20)
                Text("Accounts scroll when the dock is shorter than the list.").font(.caption).foregroundStyle(.secondary)
            }
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
            HStack {
                Spacer()
                Button("Restore defaults") {
                    store.dockScale = 1; store.dockLength = 820; store.roundIcons = false
                    store.showNames = true; store.dockOpacity = 1; attach("right")
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
    var settings: NSWindow?
    var layoutSubscription: AnyCancellable?
    var statusItem: NSStatusItem!
    var closeDetailWork: DispatchWorkItem?
    var dockingWork: DispatchWorkItem?
    var placingRail = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.appearance = NSAppearance(named: .darkAqua)
        overview = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1120, height: 880), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        overview.title = "Mako Capacity"
        overview.isReleasedWhenClosed = false
        overview.contentView = NSHostingView(rootView: OverviewView(store: store))
        overview.center()
        overview.setFrameAutosaveName("MakoCapacityOverview")
        rail = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 88, height: 820), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        rail.isOpaque = false
        rail.backgroundColor = .clear
        rail.level = .floating
        rail.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        rail.isMovableByWindowBackground = true
        rail.hidesOnDeactivate = false
        rail.delegate = self
        positionRail(edge: store.dockEdge)
        rail.contentView = NSHostingView(rootView: RailView(store: store, showOverview: { [weak self] in self?.showOverview() }, showSettings: { [weak self] in self?.showSettings() }, hover: { [weak self] in self?.showDetail($0) }))
        layoutSubscription = Publishers.CombineLatest(store.$dockScale, store.$dockLength)
            .dropFirst().receive(on: RunLoop.main).sink { [weak self] _ in self?.repositionRail() }
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
        if args.contains("--settings") { showSettings() }
        if args.contains("--overview") || args.contains("--screenshot") { showOverview() }
        if let index = args.firstIndex(of: "--screenshot"), args.count > index + 1 {
            let path = args[index + 1]
            DispatchQueue.main.asyncAfter(deadline: .now() + 4) { [weak self] in self?.capture(path) }
        }
    }

    @objc func showOverview() { overview.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    @objc func showSettings() {
        showDetail(nil)
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
    @objc func toggleRail() { if rail.isVisible { rail.orderOut(nil) } else { rail.orderFrontRegardless() } }
    @objc func refresh() { store.refresh(force: true) }
    @objc func repositionRail() { positionRail(edge: store.dockEdge) }
    @objc func attachRail(_ item: NSMenuItem) { positionRail(edge: item.representedObject as? String ?? "right"); rail.orderFrontRegardless() }
    @objc func quit() { NSApp.terminate(nil) }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showOverview(); return true }

    func positionRail(edge: String, screen preferred: NSScreen? = nil) {
        guard let screen = preferred ?? rail?.screen ?? NSScreen.main else { return }
        placingRail = true
        store.dockEdge = edge
        UserDefaults.standard.set(edge, forKey: "dockEdge")
        let horizontal = edge == "top" || edge == "bottom"
        let scale = store.dockScale
        let size = horizontal ? NSSize(width: min(store.dockLength * scale, screen.visibleFrame.width), height: 114 * scale) : NSSize(width: 88 * scale, height: min(store.dockLength * scale, screen.visibleFrame.height - 24))
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
        if detail == nil {
            detail = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
            detail?.isOpaque = false
            detail?.backgroundColor = .clear
            detail?.level = .floating
            detail?.hidesOnDeactivate = false
            detail?.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        }
        let pointsLeft = store.dockEdge == "left"
        let content = AccountCard(account: account).frame(width: 330).padding(8)
            .padding(pointsLeft ? .leading : .trailing, 20)
            .background(DetailBubble(pointsLeft: pointsLeft).fill(Color(white: 0.065)))
            .onHover { [weak self] inside in if inside { self?.closeDetailWork?.cancel() } else { self?.showDetail(nil) } }
            .preferredColorScheme(.dark)
        let view = NSHostingView(rootView: content)
        let size = view.fittingSize
        let screen = rail.screen?.visibleFrame ?? NSScreen.main!.visibleFrame
        let right = rail.frame.minX - size.width - 8
        let x = right >= screen.minX ? right : rail.frame.maxX + 8
        let y = min(screen.maxY - size.height, max(screen.minY, NSEvent.mouseLocation.y - size.height / 2))
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
