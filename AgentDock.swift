import AppKit
import Combine
import SwiftUI

// The agents dock: a second floating dock with a ring per running coding agent.
// agents.py reads Herdr, Claude Code and Codex; this file only draws its snapshot.

struct AgentStep: Codable, Hashable {
    let title: String?
    let status: String?
}

struct AgentSubagent: Codable, Identifiable {
    let id: String
    let name: String?
    let description: String?
    let model: String?
    let running: Bool?
    let step: String?
    let updated: Double?
}

struct AgentEvent: Codable, Hashable {
    let at: Double?
    let text: String
    let kind: String?
}

struct AgentItem: Codable, Identifiable {
    let id: String
    let pane: String?
    let agent: String
    let name: String?
    let status: String
    let title: String?
    let project: String?
    let task: String?
    let prompt: String?
    let now: String?
    let steps: [AgentStep]?
    let activity: [AgentEvent]?
    let updated: Double?
    let progress: Double?
    let stepCount: [Int]?
    let subagents: [AgentSubagent]?

    var provider: String { agent == "codex" ? "Codex" : "Claude" }
    var heading: String { task ?? title ?? name ?? provider }
    var live: Bool { status == "working" || status == "blocked" }
    var runningSubagents: Int { (subagents ?? []).filter { $0.running == true }.count }
    /// Three colours: yellow while it works, red when it needs you, green when it finished.
    var signal: Color {
        switch status {
        case "working": return .yellow
        case "blocked": return .red
        case "done": return .green
        default: return .gray
        }
    }
    var stateLabel: String {
        switch status {
        case "working": return "Working"
        case "blocked": return "Needs you"
        case "done": return "Finished"
        default: return "Idle"
        }
    }
    /// The ring: progress when known, full when finished, a short arc while it works.
    var ring: Double { progress ?? (status == "done" ? 100 : live ? 8 : 0) }
}

struct AgentSnapshot: Codable {
    let agents: [AgentItem]
}

func ago(_ timestamp: Double?) -> String {
    guard let timestamp else { return "" }
    let seconds = max(0, Int(Date().timeIntervalSince1970 - timestamp))
    if seconds < 60 { return "\(seconds)s ago" }
    if seconds < 3600 { return "\(seconds / 60)m ago" }
    if seconds < 86400 { return "\(seconds / 3600)h ago" }
    return "\(seconds / 86400)d ago"
}

/// Runs a command with the folders where Homebrew and Herdr install, which apps opened from Finder lack.
func runTool(_ path: String, _ arguments: [String]) -> Process {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: path)
    process.arguments = arguments
    var environment = ProcessInfo.processInfo.environment
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    environment["PATH"] = ["\(home)/.local/bin", "/opt/homebrew/bin", "/usr/local/bin", environment["PATH"] ?? "/usr/bin:/bin"].joined(separator: ":")
    process.environment = environment
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    return process
}

@MainActor
final class AgentStore: ObservableObject {
    @Published var agents: [AgentItem] = []
    @Published var edge = UserDefaults.standard.string(forKey: "agentDockEdge") ?? "left"
    private var timer: Timer?
    private var running = false
    private var observed = Date.distantPast
    private var lastData: Data?
    private var lastShowIdle = false
    static let snapshot = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Mako Capacity/agents.json")

    init() {
        load()
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 6, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }

    func load() {
        let showIdle = Self.showIdle()
        guard let data = try? Data(contentsOf: Self.snapshot), data != lastData || showIdle != lastShowIdle,
              let snapshot = try? JSONDecoder().decode(AgentSnapshot.self, from: data) else { return }
        lastData = data
        lastShowIdle = showIdle
        // Idle agents show only when Settings turns them on, the same setting the terminal app uses.
        agents = showIdle ? snapshot.agents : snapshot.agents.filter { $0.status != "idle" }
    }

    static let settings = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".mako-capacity/settings.json")
    static func showIdle() -> Bool {
        guard let data = try? Data(contentsOf: settings),
              let values = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return values["SHOW_IDLE_AGENTS"] as? String == "1"
    }

    func setShowIdle(_ show: Bool) {
        // settings.json may hold the proxy key: keep its mode, and create it private.
        var values = (try? Data(contentsOf: Self.settings)).flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        values["SHOW_IDLE_AGENTS"] = show ? "1" : nil
        guard let data = try? JSONSerialization.data(withJSONObject: values, options: [.prettyPrinted, .sortedKeys]) else { return }
        if FileManager.default.fileExists(atPath: Self.settings.path) {
            try? data.write(to: Self.settings)
        } else {
            try? FileManager.default.createDirectory(at: Self.settings.deletingLastPathComponent(), withIntermediateDirectories: true)
            FileManager.default.createFile(atPath: Self.settings.path, contents: data, attributes: [.posixPermissions: 0o600])
        }
        lastData = nil
        load()
    }

    func refresh() {
        guard !running, let script = Bundle.main.resourceURL?.appendingPathComponent("agents.py") else { return }
        running = true
        // The observer model runs at most every 45 s; the cheap parts run every time.
        let observe = Date().timeIntervalSince(observed) > 45
        if observe { observed = Date() }
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let process = runTool("/usr/bin/python3", [script.path] + (observe ? ["--observe"] : []))
            try? process.run()
            process.waitUntilExit()
            DispatchQueue.main.async {
                self?.running = false
                self?.load()
            }
        }
    }

    /// Brings the agent's Herdr pane forward, then the terminal that shows Herdr.
    func focus(_ agent: AgentItem) {
        guard let pane = agent.pane else { return }
        let process = runTool("/usr/bin/env", ["herdr", "agent", "focus", pane])
        try? process.run()
        for id in ["com.mitchellh.ghostty", "net.kovidgoyal.kitty", "com.github.wez.wezterm"] {
            if let app = NSRunningApplication.runningApplications(withBundleIdentifier: id).first {
                app.activate()
                break
            }
        }
    }
}

struct AgentRing: View {
    let agent: AgentItem
    var size: CGFloat = 42
    @State private var pulse = false
    @State private var beat = false
    var body: some View {
        ZStack {
            Circle().stroke(.black.opacity(0.75), lineWidth: 6)
            Circle().stroke(.white.opacity(0.12), lineWidth: 4)
            Circle().trim(from: 0, to: min(agent.ring, 100) / 100)
                .stroke(agent.signal, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                .rotationEffect(.degrees(-90))
            ProviderMark(provider: agent.provider).frame(width: size * 0.43, height: size * 0.43).foregroundStyle(.white)
        }
        .frame(width: size, height: size)
        .overlay(alignment: .bottomTrailing) {
            // While the agent works, the status light beats and sends out a ring, like a pulse.
            ZStack {
                if agent.status == "working" {
                    Circle().stroke(agent.signal, lineWidth: 1.5)
                        .scaleEffect(pulse ? 2.4 : 1)
                        .opacity(pulse ? 0 : 0.9)
                }
                Circle().fill(agent.signal)
                    .overlay(Circle().stroke(Color(white: 0.065), lineWidth: 2))
                    .scaleEffect(agent.status == "working" && beat ? 1.3 : 1)
            }
            .frame(width: size * 0.26, height: size * 0.26)
            .offset(x: 2, y: 2)
        }
        .onAppear {
            guard agent.status == "working" else { return }
            withAnimation(.easeOut(duration: 1.2).repeatForever(autoreverses: false)) { pulse = true }
            withAnimation(.easeInOut(duration: 0.6).repeatForever(autoreverses: true)) { beat = true }
        }
        .accessibilityLabel("\(agent.provider), \(agent.heading), \(agent.stateLabel)")
    }
}

struct AgentCard: View {
    let agent: AgentItem
    var focus: () -> Void
    func section(_ title: String) -> some View {
        Text(title.uppercased()).font(.system(size: 10, weight: .bold)).foregroundStyle(.secondary).padding(.top, 2)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(agent.provider.uppercased()).font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(agent.provider == "Codex" ? Color.mint : .orange)
                Spacer()
                Text(agent.stateLabel).font(.system(size: 10, weight: .semibold)).foregroundStyle(agent.signal)
                    .padding(.horizontal, 7).padding(.vertical, 2).background(agent.signal.opacity(0.16), in: Capsule())
            }
            HStack(spacing: 12) {
                AgentRing(agent: agent, size: 40)
                VStack(alignment: .leading, spacing: 3) {
                    Text(agent.heading).font(.headline).lineLimit(2).fixedSize(horizontal: false, vertical: true)
                    Text([agent.name, agent.project].compactMap { $0 }.uniqued().joined(separator: " · "))
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer(minLength: 0)
                if let progress = agent.progress {
                    Text("\(Int(progress))%").font(.system(size: 22, weight: .semibold, design: .rounded)).foregroundStyle(agent.signal)
                }
            }
            if let now = agent.now {
                HStack(spacing: 8) {
                    Circle().fill(agent.signal).frame(width: 7, height: 7)
                    Text(now).font(.caption).lineLimit(2)
                }
                .padding(9).frame(maxWidth: .infinity, alignment: .leading)
                .background(agent.signal.opacity(0.09), in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(agent.signal.opacity(0.25)))
            }
            if let steps = agent.steps, !steps.isEmpty {
                section(agent.stepCount.map { "Steps · \($0[0]) of \($0[1])" } ?? "Steps")
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(Array(steps.enumerated()), id: \.offset) { _, step in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: step.status == "done" ? "checkmark.circle.fill" : step.status == "active" ? "circle.inset.filled" : "circle")
                                .foregroundStyle(step.status == "done" ? Color.green : step.status == "active" ? agent.signal : .secondary)
                            Text(step.title ?? "").foregroundStyle(step.status == "pending" ? .secondary : .primary)
                                .fontWeight(step.status == "active" ? .semibold : .regular)
                                .fixedSize(horizontal: false, vertical: true)
                        }.font(.caption)
                    }
                }
            }
            if let subagents = agent.subagents, !subagents.isEmpty {
                section("Subagents")
                ForEach(subagents) { sub in
                    HStack(alignment: .top, spacing: 8) {
                        Circle().fill(sub.running == true ? Color.yellow : .green).frame(width: 7, height: 7).padding(.top, 4)
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(sub.description ?? sub.name ?? "Subagent").font(.caption.weight(.semibold)).lineLimit(1)
                                if let model = sub.model, !model.isEmpty {
                                    Text(model).font(.system(size: 9)).foregroundStyle(.secondary)
                                        .padding(.horizontal, 5).background(.white.opacity(0.08), in: Capsule())
                                }
                            }
                            Text("\(sub.running == true ? "▸ " + (sub.step ?? "Working") : "Done") · \(ago(sub.updated))")
                                .font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
                        }
                    }
                }
            }
            if let activity = agent.activity, !activity.isEmpty {
                section("Recent activity")
                ForEach(Array(activity.suffix(4).reversed().enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: 8) {
                        Text(ago(item.at)).frame(width: 48, alignment: .leading).foregroundStyle(.secondary)
                        Text(item.text).foregroundStyle(item.kind == "say" ? .primary : .secondary).lineLimit(1)
                    }.font(.system(size: 10))
                }
            }
            HStack {
                Text(ago(agent.updated)).font(.system(size: 10)).foregroundStyle(.secondary)
                Spacer()
                if agent.pane != nil { Button("Go to pane", action: focus) }
            }
        }
        .padding(16)
        .background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(.white.opacity(0.07)))
    }
}

extension Array where Element == String {
    func uniqued() -> [String] { reduce(into: []) { if !$0.contains($1) { $0.append($1) } } }
}

struct AgentRailView: View {
    @ObservedObject var store: AgentStore
    @ObservedObject var capacity: CapacityStore
    var hover: (AgentItem?) -> Void
    var hide: () -> Void
    var horizontal: Bool { store.edge == "top" || store.edge == "bottom" }
    func cell(_ agent: AgentItem) -> some View {
        Button { store.focus(agent) } label: {
            VStack(spacing: 3) {
                AgentRing(agent: agent, size: horizontal ? 36 : 42)
                Text(agent.progress.map { "\(Int($0))%" } ?? agent.stateLabel)
                    .font(.system(size: agent.progress == nil ? 10 : 15, weight: .medium)).monospacedDigit()
                    .foregroundStyle(agent.signal).lineLimit(1)
                Text(agent.name ?? agent.project ?? "").font(.system(size: 9, weight: .medium)).foregroundStyle(.white.opacity(0.6)).lineLimit(1)
            }.frame(width: horizontal ? 72 : 64, height: 78)
        }.buttonStyle(.plain).onHover { inside in hover(inside ? agent : nil) }
            .help("\(agent.provider) · \(agent.heading) · \(agent.stateLabel)")
    }
    var empty: some View {
        VStack(spacing: 4) {
            Image(systemName: "sparkles").font(.system(size: 18)).foregroundStyle(.secondary)
            Text("No agents").font(.system(size: 9)).foregroundStyle(.secondary)
        }.frame(width: 64, height: 78)
    }
    var body: some View {
        GeometryReader { geometry in
            content
                .frame(width: geometry.size.width / capacity.dockScale, height: geometry.size.height / capacity.dockScale)
                .scaleEffect(capacity.dockScale, anchor: .topLeading)
        }
        .contextMenu { Button("Hide agents dock", action: hide) }
    }
    var content: some View {
        Group {
            if horizontal {
                HStack(spacing: 8) {
                    Image(systemName: "line.3.horizontal").font(.system(size: 10)).foregroundStyle(.secondary).help("Drag to attach to a screen edge")
                    ShadowScrollView(axis: .horizontal, showsIndicators: false) {
                        HStack(spacing: 8) { if store.agents.isEmpty { empty }; ForEach(store.agents) { cell($0) } }
                    }
                }.padding(.horizontal, 34).padding(.vertical, 14)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "line.3.horizontal").font(.system(size: 12)).foregroundStyle(.secondary)
                        .padding(.top, store.edge == "floating" ? 12 : 32).help("Drag to attach to a screen edge")
                    ShadowScrollView(showsIndicators: false) {
                        VStack(spacing: 6) { if store.agents.isEmpty { empty }; ForEach(store.agents) { cell($0) } }.padding(.horizontal, 12)
                    }
                    Image(systemName: "sparkles").font(.system(size: 12)).foregroundStyle(.secondary).help("Agents")
                        .padding(.bottom, store.edge == "floating" ? 12 : 32)
                }
            }
        }
        .foregroundStyle(.white)
        .background(DockSurface(edge: store.edge).fill(Color(white: 0.065).opacity(capacity.dockOpacity)))
        .overlay(DockSurface(edge: store.edge).stroke(.white.opacity(0.12)))
        .preferredColorScheme(.dark)
    }
}

/// Owns the agents dock panel: placement on an edge or floating, drag to snap, and the hover card.
@MainActor
final class AgentDockController: NSObject, NSWindowDelegate {
    let store = AgentStore()
    let capacity: CapacityStore
    var panel: NSPanel!
    var detail: NSPanel?
    var closeDetailWork: DispatchWorkItem?
    var dockingWork: DispatchWorkItem?
    var placing = false
    var subscription: AnyCancellable?

    init(capacity: CapacityStore) {
        self.capacity = capacity
        super.init()
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 88, height: 400), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.hasShadow = false
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isMovableByWindowBackground = true
        panel.hidesOnDeactivate = false
        panel.delegate = self
        panel.contentView = NSHostingView(rootView: AgentRailView(store: store, capacity: capacity,
            hover: { [weak self] in self?.showDetail($0) }, hide: { [weak self] in self?.setVisible(false) }))
        place(edge: store.edge)
        subscription = Publishers.CombineLatest(store.$agents, capacity.$dockScale).dropFirst().receive(on: RunLoop.main)
            .sink { [weak self] _, _ in self?.place(edge: self?.store.edge ?? "left") }
        if UserDefaults.standard.object(forKey: "agentDockVisible") as? Bool ?? true { panel.orderFrontRegardless() }
    }

    var visible: Bool { panel.isVisible }

    func setVisible(_ visible: Bool) {
        UserDefaults.standard.set(visible, forKey: "agentDockVisible")
        if visible { place(edge: store.edge); panel.orderFrontRegardless() } else { panel.orderOut(nil); detail?.orderOut(nil) }
    }

    func place(edge: String, screen preferred: NSScreen? = nil) {
        guard let screen = preferred ?? panel.screen ?? NSScreen.main else { return }
        placing = true
        store.edge = edge
        UserDefaults.standard.set(edge, forKey: "agentDockEdge")
        let horizontal = edge == "top" || edge == "bottom"
        let scale = capacity.dockScale
        let count = max(1, store.agents.count)
        let padding: CGFloat = edge == "floating" ? 12 : 32
        let length = horizontal ? CGFloat(90 + count * 72 + (count - 1) * 8) : padding * 2 + 44 + CGFloat(count * 78 + (count - 1) * 6)
        let size = horizontal ? NSSize(width: min(length * scale, screen.visibleFrame.width), height: 114 * scale)
            : NSSize(width: 88 * scale, height: min(length * scale, screen.visibleFrame.height - 24))
        let offset = UserDefaults.standard.object(forKey: "agentDockOffset") as? Double ?? 0.5
        var origin = NSPoint(x: screen.visibleFrame.minX + (screen.visibleFrame.width - size.width) * offset,
                             y: screen.visibleFrame.minY + (screen.visibleFrame.height - size.height) * offset)
        switch edge {
        case "right": origin.x = screen.frame.maxX - size.width
        case "left": origin.x = screen.frame.minX
        case "top": origin.y = screen.visibleFrame.maxY - size.height
        case "bottom": origin.y = screen.visibleFrame.minY
        default:
            origin.x = UserDefaults.standard.object(forKey: "agentFloatingX") as? Double ?? origin.x
            // A floating dock grows downwards from its top edge as agents start.
            let top = UserDefaults.standard.object(forKey: "agentFloatingTop") as? Double ?? (origin.y + size.height)
            origin.y = top - size.height
            origin.x = max(screen.visibleFrame.minX, min(origin.x, screen.visibleFrame.maxX - size.width))
            origin.y = max(screen.visibleFrame.minY, min(origin.y, screen.visibleFrame.maxY - size.height))
        }
        panel.setFrame(NSRect(origin: origin, size: size), display: true)
        placing = false
    }

    func windowDidMove(_ notification: Notification) {
        guard !placing else { return }
        closeDetailWork?.cancel()
        detail?.orderOut(nil)
        scheduleDocking()
    }

    func scheduleDocking() {
        dockingWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            if NSEvent.pressedMouseButtons != 0 { self.scheduleDocking(); return }
            guard let screen = self.panel.screen ?? NSScreen.main else { return }
            let frame = self.panel.frame
            let candidates: [(String, CGFloat)] = [("left", abs(frame.minX - screen.frame.minX)), ("right", abs(frame.maxX - screen.frame.maxX)),
                                                   ("top", abs(frame.maxY - screen.visibleFrame.maxY)), ("bottom", abs(frame.minY - screen.visibleFrame.minY))]
            let nearest = candidates.min(by: { $0.1 < $1.1 })!
            if nearest.1 <= 48 {
                let horizontal = nearest.0 == "top" || nearest.0 == "bottom"
                let span = horizontal ? screen.visibleFrame.width - frame.width : screen.visibleFrame.height - frame.height
                let distance = horizontal ? frame.minX - screen.visibleFrame.minX : frame.minY - screen.visibleFrame.minY
                UserDefaults.standard.set(max(0, min(1, span > 0 ? distance / span : 0.5)), forKey: "agentDockOffset")
                self.place(edge: nearest.0, screen: screen)
            } else {
                UserDefaults.standard.set(frame.minX, forKey: "agentFloatingX")
                UserDefaults.standard.set(frame.maxY, forKey: "agentFloatingTop")
                self.place(edge: "floating", screen: screen)
            }
        }
        dockingWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15, execute: work)
    }

    func showDetail(_ agent: AgentItem?) {
        closeDetailWork?.cancel()
        guard let agent else {
            let work = DispatchWorkItem { [weak self] in self?.detail?.orderOut(nil) }
            closeDetailWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: work)
            return
        }
        if detail == nil {
            detail = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
            detail?.hasShadow = false
            detail?.isOpaque = false
            detail?.backgroundColor = .clear
            detail?.level = .floating
            detail?.hidesOnDeactivate = false
            detail?.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        }
        let screen = panel.screen?.visibleFrame ?? NSScreen.main!.visibleFrame
        // The card opens on the side with room: right of a dock on the left edge, left of any other.
        let pointsLeft = panel.frame.minX - 380 < screen.minX
        let content = AgentCard(agent: agent, focus: { [weak self] in self?.store.focus(agent) }).frame(width: 330).padding(8)
            .padding(pointsLeft ? .leading : .trailing, 20)
            .background(DetailBubble(pointsLeft: pointsLeft).fill(Color(white: 0.065)))
            .onHover { [weak self] inside in if inside { self?.closeDetailWork?.cancel() } else { self?.showDetail(nil) } }
            .preferredColorScheme(.dark)
        let view = NSHostingView(rootView: content)
        let size = view.fittingSize
        let x = pointsLeft ? panel.frame.maxX + 8 : panel.frame.minX - size.width - 8
        let y = min(screen.maxY - size.height, max(screen.minY, NSEvent.mouseLocation.y - size.height / 2))
        detail?.setFrame(NSRect(origin: NSPoint(x: x, y: y), size: size), display: false)
        detail?.contentView = view
        detail?.orderFrontRegardless()
    }
}
