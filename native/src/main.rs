#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]
use eframe::egui::{self, Color32, Pos2, Stroke, Vec2};
mod design;
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    path::PathBuf,
    process::Command,
    sync::mpsc,
    time::{Duration, Instant},
};

#[derive(Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Window {
    label: String,
    used: f32,
    reset_at: Option<f64>,
    detail: Option<String>,
}
#[derive(Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Usage {
    tokens: Option<f64>,
    input_tokens: Option<f64>,
    output_tokens: Option<f64>,
    cache_read_tokens: Option<f64>,
    cache_write_tokens: Option<f64>,
    cost_usd: Option<f64>,
    estimated: Option<bool>,
    unpriced_models: Option<usize>,
    status: String,
    message: Option<String>,
    fetched_at: Option<f64>,
}
#[derive(Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Account {
    id: String,
    provider: String,
    title: String,
    email: String,
    plan: String,
    status: String,
    message: String,
    source: String,
    windows: Vec<Window>,
    local_usage: Option<Usage>,
    on_demand_usd: Option<f64>,
    proxy_ref: Option<String>,
}
#[derive(Default, Deserialize)]
struct Snapshot {
    accounts: Vec<Account>,
    #[serde(default)]
    hidden: HashMap<String, String>,
}
impl Account {
    fn used(&self) -> Option<f32> {
        if self.provider == "Cursor" {
            self.windows
                .iter()
                .find(|w| w.label == "Cursor Models")
                .map(|w| w.used)
        } else {
            self.windows.iter().map(|w| w.used).reduce(f32::max)
        }
    }
    fn signal(&self) -> Color32 {
        if self.status == "loginRequired" {
            Color32::from_rgb(255, 159, 10)
        } else if self.used().unwrap_or(0.0) >= 100.0 {
            Color32::from_rgb(255, 69, 58)
        } else if self.used().unwrap_or(0.0) >= 85.0 {
            Color32::from_rgb(255, 159, 10)
        } else if self.used().unwrap_or(0.0) >= 70.0 {
            Color32::from_rgb(255, 214, 10)
        } else {
            Color32::from_rgb(48, 209, 88)
        }
    }
    fn state_label(&self) -> &str {
        match self.status.as_str() {
            "live" => {
                if self.used().unwrap_or(0.0) >= 100.0 {
                    "At limit"
                } else {
                    "Available"
                }
            }
            "loginRequired" => "Reconnect",
            "rateLimited" => "Throttled",
            "stale" => "Cached",
            "unavailable" => "Unavailable",
            _ => "Unknown",
        }
    }
    fn color(&self) -> Color32 {
        match self.provider.as_str() {
            "Claude" => Color32::from_rgb(230, 152, 96),
            "Codex" => Color32::from_rgb(92, 214, 179),
            _ => Color32::from_rgb(179, 132, 242),
        }
    }
}
#[derive(Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
struct Preferences {
    edge: String,
    size: f32,
    labels: bool,
    round: bool,
    opacity: f32,
    offset: f32,
}
impl Default for Preferences {
    fn default() -> Self {
        Self {
            edge: "right".into(),
            size: 1.0,
            labels: true,
            round: false,
            opacity: 1.0,
            offset: 0.5,
        }
    }
}
fn state_dir() -> PathBuf {
    std::env::var_os("MAKO_CAPACITY_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| dirs::home_dir().unwrap_or_default().join(".mako-capacity"))
}
fn cache_dir() -> PathBuf {
    #[cfg(target_os = "macos")]
    return dirs::home_dir()
        .unwrap_or_default()
        .join("Library/Application Support/Mako Capacity");
    #[cfg(not(target_os = "macos"))]
    dirs::cache_dir()
        .unwrap_or_else(state_dir)
        .join("mako-capacity")
}
fn count(value: Option<f64>) -> String {
    match value {
        Some(v) if v >= 1_000_000.0 => format!("{:.1}M", v / 1_000_000.0),
        Some(v) if v >= 1_000.0 => format!("{:.1}K", v / 1_000.0),
        Some(v) => format!("{v:.0}"),
        None => "—".into(),
    }
}
fn money(value: Option<f64>) -> String {
    value
        .map(|v| format!("${v:.2}"))
        .unwrap_or_else(|| "—".into())
}
fn now() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}
fn reset(value: Option<f64>) -> String {
    match value {
        Some(at) if at > now() => {
            let seconds = (at - now()) as u64;
            if seconds >= 86400 {
                format!("Resets in {}d {}h", seconds / 86400, seconds % 86400 / 3600)
            } else {
                format!("Resets in {}h {}m", seconds / 3600, seconds % 3600 / 60)
            }
        }
        Some(_) => "Reset due".into(),
        None => "Reset unknown".into(),
    }
}
// Match the original dock: release within 48 points of an edge to attach,
// retaining the position along that edge instead of jumping to its center.
fn snap_edge(frame: egui::Rect, screen: Vec2) -> (&'static str, f32) {
    let candidates = [
        ("left", frame.min.x.abs()),
        ("right", (frame.max.x - screen.x).abs()),
        ("top", frame.min.y.abs()),
        ("bottom", (frame.max.y - screen.y).abs()),
    ];
    let (edge, distance) = candidates
        .into_iter()
        .min_by(|a, b| a.1.total_cmp(&b.1))
        .unwrap();
    if distance > 48.0 {
        return ("floating", 0.5);
    }
    let (distance, span) = if edge == "top" || edge == "bottom" {
        (frame.min.x, screen.x - frame.width())
    } else {
        (frame.min.y, screen.y - frame.height())
    };
    (
        edge,
        if span > 0.0 {
            (distance / span).clamp(0.0, 1.0)
        } else {
            0.5
        },
    )
}
enum Update {
    Accounts(Result<Snapshot, String>),
    Usage(Result<HashMap<String, Usage>, String>),
}
struct Dock {
    accounts: Vec<Account>,
    hidden: HashMap<String, String>,
    confirm_delete: Option<String>,
    show_hidden: bool,
    queued_action: Vec<String>,
    prefs: Preferences,
    error: Option<String>,
    refreshing: bool,
    hovered: Option<Account>,
    last_hover: Instant,
    preview: bool,
    receiver: mpsc::Receiver<Update>,
    sender: mpsc::Sender<Update>,
    last_poll: Instant,
    last_usage: Instant,
    usage_loading: bool,
    overview: bool,
    settings: bool,
    icons: Vec<egui::TextureHandle>,
    layout: Option<(String, Vec2, Vec2, f32)>,
    drag_anchor: Option<Pos2>,
    last_drag_move: Instant,
    drag_position: Option<Pos2>,
    hover_height: f32,
    hover_anchor: Pos2,
}
impl Dock {
    fn new(cc: &eframe::CreationContext<'_>) -> Self {
        cc.egui_ctx.set_visuals(egui::Visuals::dark());
        let font_path = if cfg!(target_os = "macos") {
            "/System/Library/Fonts/SFNS.ttf"
        } else if cfg!(windows) {
            "C:/Windows/Fonts/segoeui.ttf"
        } else {
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        };
        if let Ok(bytes) = std::fs::read(font_path) {
            let mut fonts = egui::FontDefinitions::default();
            fonts
                .font_data
                .insert("system".into(), egui::FontData::from_owned(bytes).into());
            fonts
                .families
                .get_mut(&egui::FontFamily::Proportional)
                .unwrap()
                .insert(0, "system".into());
            cc.egui_ctx.set_fonts(fonts);
        }
        cc.egui_ctx.style_mut(|style| {
            style.visuals.override_text_color = Some(Color32::WHITE);
            style
                .text_styles
                .insert(egui::TextStyle::Body, egui::FontId::proportional(12.0));
            style
                .text_styles
                .insert(egui::TextStyle::Small, egui::FontId::proportional(10.0));
            style
                .text_styles
                .insert(egui::TextStyle::Heading, egui::FontId::proportional(13.0));
            style.spacing.item_spacing = Vec2::new(8.0, 4.0);
        });
        let mut prefs: Preferences = cc
            .storage
            .and_then(|s| eframe::get_value(s, "preferences"))
            .unwrap_or_default();
        if cfg!(target_os = "linux")
            && std::env::var("XDG_SESSION_TYPE").as_deref() == Ok("wayland")
        {
            prefs.edge = "floating".into();
        }
        let (sender, receiver) = mpsc::channel();
        let args: Vec<String> = std::env::args().collect();
        let preview_path = args
            .iter()
            .position(|a| a == "--preview")
            .and_then(|i| args.get(i + 1));
        let Snapshot { accounts, hidden } = std::fs::read(
            preview_path
                .map(PathBuf::from)
                .unwrap_or_else(|| cache_dir().join("snapshot.json")),
        )
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Snapshot>(&bytes).ok())
        .unwrap_or_default();
        let mut icons = Vec::new();
        for (name, bytes) in [
            (
                "Claude",
                include_bytes!("../../Resources/claude.png").as_slice(),
            ),
            (
                "Codex",
                include_bytes!("../../Resources/codex.png").as_slice(),
            ),
        ] {
            if let Ok(image) = image::load_from_memory(bytes) {
                let mut image = image.to_rgba8();
                for pixel in image.pixels_mut() {
                    pixel[0] = 255;
                    pixel[1] = 255;
                    pixel[2] = 255;
                }
                let size = [image.width() as usize, image.height() as usize];
                icons.push(cc.egui_ctx.load_texture(
                    name,
                    egui::ColorImage::from_rgba_unmultiplied(size, image.as_raw()),
                    Default::default(),
                ));
            }
        }
        let mut app = Self {
            accounts,
            hidden,
            confirm_delete: None,
            show_hidden: false,
            queued_action: vec![],
            prefs,
            error: None,
            refreshing: false,
            receiver,
            sender,
            last_poll: Instant::now(),
            last_usage: Instant::now(),
            usage_loading: false,
            overview: args.iter().any(|arg| arg == "--overview"),
            settings: args.iter().any(|arg| arg == "--settings"),
            icons,
            layout: None,
            drag_anchor: None,
            last_drag_move: Instant::now(),
            drag_position: None,
            hover_height: 450.0,
            hover_anchor: Pos2::new(44.0, 90.0),
            hovered: None,
            last_hover: Instant::now(),
            preview: preview_path.is_some(),
        };
        if app.preview {
            app.prefs = Preferences::default();
            if let Some(scale) = args
                .iter()
                .position(|arg| arg == "--preview-scale")
                .and_then(|i| args.get(i + 1))
                .and_then(|s| s.parse::<f32>().ok())
            {
                app.prefs.size = scale.clamp(0.65, 1.4);
            }
            app.hover_anchor = Pos2::new(44.0 * app.prefs.size, 73.5 * app.prefs.size);
            app.hovered = app.accounts.first().cloned();
        } else {
            app.refresh(cc.egui_ctx.clone(), false, &[]);
            app.refresh_usage(cc.egui_ctx.clone(), false);
        }
        app
    }
    /// `action` is a collector flag and account id, such as `["--hide", id]`.
    fn refresh(&mut self, ctx: egui::Context, force: bool, action: &[&str]) {
        let action: Vec<String> = action.iter().map(|arg| arg.to_string()).collect();
        if self.refreshing {
            // A background poll is running: keep the user's action for the next run.
            if !action.is_empty() {
                self.queued_action = action;
            }
            return;
        }
        self.refreshing = true;
        self.last_poll = Instant::now();
        let sender = self.sender.clone();
        std::thread::spawn(move || {
            let result = (|| -> Result<Snapshot, String> {
                let resources = state_dir().join("resources");
                std::fs::create_dir_all(&resources).map_err(|e| e.to_string())?;
                for (name, source) in [
                    ("collector.py", include_str!("../../collector.py")),
                    ("codeburn_usage.py", include_str!("../../codeburn_usage.py")),
                    ("platform_paths.py", include_str!("../../platform_paths.py")),
                ] {
                    std::fs::write(resources.join(name), source).map_err(|e| e.to_string())?;
                }
                let settings: serde_json::Value = std::fs::read(state_dir().join("settings.json"))
                    .ok()
                    .and_then(|data| serde_json::from_slice(&data).ok())
                    .unwrap_or_default();
                let python = settings
                    .get("PYTHON_COMMAND")
                    .and_then(|v| v.as_str())
                    .unwrap_or(if cfg!(windows) { "python" } else { "python3" });
                let mut command = Command::new(python);
                command
                    .arg(resources.join("collector.py"))
                    .arg("--skip-usage");
                if force {
                    command.arg("--refresh");
                }
                command.args(&action);
                #[cfg(target_os = "windows")]
                {
                    use std::os::windows::process::CommandExt;
                    command.creation_flags(0x08000000); // Avoid a console on each poll.
                }
                let output = command.output().map_err(|_| {
                    "Python collector could not start. Run the setup CLI.".to_string()
                })?;
                if !output.status.success() {
                    let message = String::from_utf8_lossy(&output.stderr).trim().to_string();
                    return Err(if action.is_empty() || message.is_empty() {
                        "Collector failed; previous readings remain visible.".into()
                    } else {
                        message
                    });
                }
                serde_json::from_slice(&output.stdout)
                    .map_err(|e| format!("Invalid collector snapshot: {e}"))
            })();
            let _ = sender.send(Update::Accounts(result));
            ctx.request_repaint();
        });
    }
    fn refresh_usage(&mut self, ctx: egui::Context, force: bool) {
        if self.usage_loading {
            return;
        }
        self.usage_loading = true;
        self.last_usage = Instant::now();
        let sender = self.sender.clone();
        std::thread::spawn(move || {
            let result = (|| -> Result<HashMap<String, Usage>, String> {
                let resources = state_dir().join("usage-resources");
                std::fs::create_dir_all(&resources).map_err(|e| e.to_string())?;
                for (name, source) in [
                    ("codeburn_usage.py", include_str!("../../codeburn_usage.py")),
                    ("platform_paths.py", include_str!("../../platform_paths.py")),
                ] {
                    std::fs::write(resources.join(name), source).map_err(|e| e.to_string())?;
                }
                let settings: serde_json::Value = std::fs::read(state_dir().join("settings.json"))
                    .ok()
                    .and_then(|b| serde_json::from_slice(&b).ok())
                    .unwrap_or_default();
                let python = settings
                    .get("PYTHON_COMMAND")
                    .and_then(|v| v.as_str())
                    .unwrap_or(if cfg!(windows) { "python" } else { "python3" });
                let mut command = Command::new(python);
                command.arg(resources.join("codeburn_usage.py"));
                if force {
                    command.arg("--refresh");
                }
                #[cfg(target_os = "windows")]
                {
                    use std::os::windows::process::CommandExt;
                    command.creation_flags(0x08000000);
                }
                let output = command.output().map_err(|e| e.to_string())?;
                if !output.status.success() {
                    return Err("Usage collector failed".into());
                }
                serde_json::from_slice(&output.stdout).map_err(|e| e.to_string())
            })();
            let _ = sender.send(Update::Usage(result));
            ctx.request_repaint();
        });
    }
    fn dock_length(&self) -> f32 {
        let horizontal = self.prefs.edge == "top" || self.prefs.edge == "bottom";
        let count = self.accounts.len().max(1);
        if horizontal {
            return 130.0 + count as f32 * 72.0 + (count - 1) as f32 * 8.0;
        }
        let padding = if self.prefs.edge == "floating" {
            12.0
        } else {
            32.0
        };
        let heights = self
            .accounts
            .iter()
            .map(|account| {
                (if self.prefs.labels { 78.0 } else { 66.0 })
                    + if account.provider == "Cursor" {
                        (account.windows.len().max(3) - 2) as f32 * 16.0
                    } else {
                        0.0
                    }
            })
            .sum::<f32>()
            .max(if self.prefs.labels { 78.0 } else { 66.0 });
        padding * 2.0 + 44.0 + heights + (count - 1) as f32 * 6.0
    }
    fn position(&mut self, ctx: &egui::Context) {
        if self.drag_anchor.is_some() {
            return;
        }
        let monitor = ctx.input(|i| i.viewport().monitor_size);
        if let Some(screen) = monitor {
            let horizontal = self.prefs.edge == "top" || self.prefs.edge == "bottom";
            let size = if horizontal {
                Vec2::new(
                    (self.dock_length() * self.prefs.size).min(screen.x),
                    114.0 * self.prefs.size,
                )
            } else {
                Vec2::new(
                    88.0 * self.prefs.size,
                    (self.dock_length() * self.prefs.size).min(screen.y - 24.0),
                )
            };
            let layout = (self.prefs.edge.clone(), size, screen, self.prefs.offset);
            let changed = self.layout.as_ref() != Some(&layout);
            self.layout = Some(layout);
            let actual = ctx.input(|i| i.viewport().inner_rect);
            if actual.is_none_or(|r| (r.size() - size).length() > 1.0) {
                ctx.send_viewport_cmd(egui::ViewportCommand::InnerSize(size));
            }
            if self.prefs.edge != "floating" {
                let pos = match self.prefs.edge.as_str() {
                    "left" => Pos2::new(0.0, (screen.y - size.y) * self.prefs.offset),
                    "top" => Pos2::new((screen.x - size.x) * self.prefs.offset, 0.0),
                    "bottom" => {
                        Pos2::new((screen.x - size.x) * self.prefs.offset, screen.y - size.y)
                    }
                    _ => Pos2::new(screen.x - size.x, (screen.y - size.y) * self.prefs.offset),
                };
                let actual = ctx.input(|i| i.viewport().outer_rect);
                if changed || actual.is_none_or(|r| (r.min - pos).length() > 1.0) {
                    ctx.send_viewport_cmd(egui::ViewportCommand::OuterPosition(pos));
                }
            }
        }
    }
    fn overview_ui(&mut self, ui: &mut egui::Ui) {
        ui.spacing_mut().item_spacing = Vec2::new(16.0, 20.0);
        ui.horizontal(|ui| {
            ui.vertical(|ui| {
                ui.label(egui::RichText::new("Your accounts. One view.").size(28.0).strong());
                ui.label(egui::RichText::new(format!("{} accounts across Claude, Codex and Cursor · percentages show capacity used", self.accounts.len()))
                    .size(13.0).color(Color32::from_gray(153)));
            });
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui.add_enabled(!self.refreshing, egui::Button::new(if self.refreshing { "Refreshing…" } else { "Refresh" })).clicked() {
                    self.refresh(ui.ctx().clone(), true, &[]);
                }
                if !self.hidden.is_empty() {
                    ui.toggle_value(&mut self.show_hidden, format!("Hidden ({})", self.hidden.len()));
                }
            });
        });
        if self.show_hidden && !self.hidden.is_empty() {
            let mut hidden: Vec<_> = self.hidden.iter().collect();
            hidden.sort_by(|a, b| a.1.cmp(b.1));
            let mut restore = None;
            ui.horizontal_wrapped(|ui| {
                for (id, label) in hidden {
                    if ui.button(format!("Restore {label}")).clicked() {
                        restore = Some(id.clone());
                    }
                }
            });
            if let Some(id) = restore {
                self.refresh(ui.ctx().clone(), false, &["--restore", &id]);
            }
        }
        if let Some(error) = &self.error {
            ui.colored_label(Color32::LIGHT_RED, error);
        }
        let height = (ui.available_height() - 42.0).max(100.0);
        let scroll = egui::ScrollArea::vertical()
            .id_salt(if self.preview {
                "preview-all-accounts-scroll"
            } else {
                "all-accounts-scroll"
            })
            .auto_shrink([false, false])
            .max_height(height)
            .show(ui, |ui| {
                if self.accounts.is_empty() {
                    ui.label("Discovering your accounts…");
                    return;
                }
                let width = ((ui.available_width() - 48.0) / 4.0).floor();
                let mut confirm = self.confirm_delete.clone();
                let mut action: Option<(&str, String)> = None;
                egui::Grid::new("all-accounts-grid")
                    .num_columns(4)
                    .spacing([16.0, 16.0])
                    .start_row(0)
                    .show(ui, |ui| {
                        for (index, account) in self.accounts.iter().enumerate() {
                            ui.push_id(&account.id, |ui| {
                                ui.vertical(|ui| {
                                    ui.set_width(width);
                                    self.card(ui, account, width, false);
                                    ui.add_enabled_ui(self.queued_action.is_empty(), |ui| {
                                        if confirm.as_ref() == Some(&account.id) {
                                            ui.colored_label(
                                                Color32::LIGHT_RED,
                                                format!("Delete {} from the {} proxy? You cannot undo this.", account.email, account.provider),
                                            );
                                        }
                                        ui.horizontal(|ui| {
                                            if confirm.as_ref() == Some(&account.id) {
                                                if ui.small_button("Delete").clicked() {
                                                    action = Some(("--delete", account.id.clone()));
                                                    confirm = None;
                                                }
                                                if ui.small_button("Cancel").clicked() {
                                                    confirm = None;
                                                }
                                            } else {
                                                if ui.small_button("Hide").clicked() {
                                                    action = Some(("--hide", account.id.clone()));
                                                }
                                                if account.proxy_ref.is_some()
                                                    && ui
                                                        .small_button(format!("Delete from {} proxy…", account.provider))
                                                        .clicked()
                                                {
                                                    confirm = Some(account.id.clone());
                                                }
                                            }
                                        });
                                    });
                                });
                            });
                            if index % 4 == 3 {
                                ui.end_row();
                            }
                        }
                    });
                self.confirm_delete = confirm;
                if let Some((flag, id)) = action {
                    self.refresh(ui.ctx().clone(), false, &[flag, &id]);
                }
            });
        design::scroll_shadows(
            ui.painter(),
            scroll.inner_rect,
            scroll.state.offset,
            scroll.content_size,
            false,
            1.0,
        );
        ui.horizontal(|ui| {
            ui.label(egui::RichText::new("Usage refreshes every 5 minutes. Credentials stay with your provider apps and proxies.")
                .size(11.0).color(Color32::from_gray(153)));
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                ui.hyperlink_to("Proxy accounts", "http://127.0.0.1:8317/management.html");
            });
        });
    }
    fn settings_ui(&mut self, ui: &mut egui::Ui) {
        ui.spacing_mut().slider_width = ui.available_width();
        ui.spacing_mut().item_spacing.y = 8.0;
        ui.spacing_mut().slider_rail_height = 6.0;
        ui.visuals_mut().handle_shape = egui::style::HandleShape::Circle;
        ui.visuals_mut().slider_trailing_fill = true;
        ui.style_mut()
            .text_styles
            .insert(egui::TextStyle::Body, egui::FontId::proportional(13.0));
        ui.visuals_mut().selection.bg_fill = Color32::from_rgb(10, 132, 255);
        ui.label(egui::RichText::new("Dock settings").size(17.0).strong());
        ui.add_space(12.0);
        ui.label(
            egui::RichText::new("Changes apply immediately and are saved.")
                .size(13.0)
                .color(Color32::from_gray(153)),
        );
        ui.add_space(12.0);
        ui.label(format!("Size · {:.0}%", self.prefs.size * 100.0));
        ui.add(
            egui::Slider::new(&mut self.prefs.size, 0.65..=1.4)
                .step_by(0.05)
                .show_value(false),
        );
        ui.add_space(12.0);
        ui.label(
            egui::RichText::new("The dock fits your accounts and scrolls when needed.")
                .size(11.0)
                .color(Color32::from_gray(153)),
        );
        ui.add_space(12.0);
        ui.horizontal(|ui| {
            ui.label("Icon shape");
            for (round, label) in [(false, "Rounded square"), (true, "Circle")] {
                let selected = self.prefs.round == round;
                let button = egui::Button::new(label)
                    .fill(if selected {
                        Color32::from_rgb(10, 132, 255)
                    } else {
                        Color32::from_gray(48)
                    })
                    .corner_radius(5.0);
                if ui
                    .add_sized([if round { 95.0 } else { 115.0 }, 25.0], button)
                    .clicked()
                {
                    self.prefs.round = round;
                }
            }
        });
        ui.add_space(8.0);
        ui.checkbox(&mut self.prefs.labels, "Show account names");
        ui.add_space(12.0);
        ui.label(format!(
            "Background opacity · {:.0}%",
            self.prefs.opacity * 100.0
        ));
        ui.add(
            egui::Slider::new(&mut self.prefs.opacity, 0.25..=1.0)
                .step_by(0.05)
                .show_value(false),
        );
        ui.add_space(12.0);
        ui.horizontal(|ui| {
            ui.label("Screen edge");
            let title = |edge: &str| match edge {
                "left" => "Left",
                "top" => "Top",
                "bottom" => "Bottom",
                "floating" => "Floating",
                _ => "Right",
            };
            egui::ComboBox::from_id_salt("screen-edge")
                .width(100.0)
                .selected_text(title(&self.prefs.edge))
                .show_ui(ui, |ui| {
                    for edge in ["right", "left", "top", "bottom", "floating"] {
                        ui.selectable_value(&mut self.prefs.edge, edge.into(), title(edge));
                    }
                });
        });
        ui.add_space(12.0);
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            if ui.button("Restore defaults").clicked() {
                self.prefs = Preferences::default();
            }
        });
    }

    fn cell(&mut self, ui: &mut egui::Ui, account: &Account, horizontal: bool) {
        let scale = self.prefs.size;
        let width = if horizontal { 72.0 } else { 64.0 } * scale;
        let height = (if self.prefs.labels { 78.0 } else { 66.0 }
            + if account.provider == "Cursor" {
                (account.windows.len().max(3) - 2) as f32 * 16.0
            } else {
                0.0
            })
            * scale;
        let (rect, response) =
            ui.allocate_exact_size(Vec2::new(width, height), egui::Sense::click());
        let ring_size = if horizontal || account.provider == "Cursor" {
            36.0
        } else {
            42.0
        } * scale;
        let rows = if account.provider == "Cursor" && !account.windows.is_empty() {
            account.windows.len()
        } else {
            0
        };
        let quota_height = if rows > 0 { rows as f32 * 12.0 } else { 18.0 } * scale;
        let content_height = ring_size
            + 3.0 * scale
            + quota_height
            + if self.prefs.labels { 14.0 * scale } else { 0.0 };
        let top = rect.min.y + ((height - content_height) * 0.5).max(0.0);
        let ring_rect = egui::Rect::from_center_size(
            Pos2::new(rect.center().x, top + ring_size * 0.5),
            Vec2::splat(ring_size),
        );
        let mut ring_ui = ui.new_child(
            egui::UiBuilder::new()
                .max_rect(ring_rect)
                .layout(egui::Layout::top_down(egui::Align::Center)),
        );
        let ring = self.ring(&mut ring_ui, account, ring_size, self.prefs.round, scale);
        if response.clicked() || ring.clicked() {
            self.overview = true;
        }
        let mut y = top + ring_size + 3.0 * scale;
        if rows > 0 {
            for window in &account.windows {
                let name = match window.label.as_str() {
                    "Cursor Models" => "Models",
                    "Other Models" => "Other",
                    "Grok Bot" => "Grok",
                    _ => "Spend",
                };
                let half_width = 29.5 * scale;
                ui.painter().text(
                    Pos2::new(rect.center().x - half_width, y),
                    egui::Align2::LEFT_TOP,
                    name,
                    egui::FontId::proportional(9.0 * scale),
                    Color32::from_gray(166),
                );
                ui.painter().text(
                    Pos2::new(rect.center().x + half_width, y),
                    egui::Align2::RIGHT_TOP,
                    format!("{:.0}%", window.used),
                    egui::FontId::proportional(9.0 * scale),
                    if window.used >= 100.0 {
                        Color32::LIGHT_RED
                    } else {
                        account.signal()
                    },
                );
                y += 12.0 * scale;
            }
        } else {
            ui.painter().text(
                Pos2::new(rect.center().x, y),
                egui::Align2::CENTER_TOP,
                account
                    .used()
                    .map(|v| format!("{v:.0}%"))
                    .unwrap_or_else(|| "—".into()),
                egui::FontId::proportional(if horizontal { 13.0 } else { 15.0 } * scale),
                account.signal(),
            );
            y += quota_height;
        }
        if self.prefs.labels {
            let mut job = egui::text::LayoutJob::simple(
                account.title.clone(),
                egui::FontId::proportional(9.0 * scale),
                Color32::from_gray(153),
                width,
            );
            job.wrap.max_rows = 1;
            job.wrap.break_anywhere = true;
            let galley = ui.painter().layout_job(job);
            ui.painter().galley(
                Pos2::new(rect.center().x - galley.size().x * 0.5, y + 3.0 * scale),
                galley,
                Color32::from_gray(153),
            );
        }
        if response.contains_pointer() {
            self.hover_anchor = ring_rect.center();
            self.hovered = Some(account.clone());
            self.last_hover = Instant::now();
        }
    }
    fn ring(
        &self,
        ui: &mut egui::Ui,
        account: &Account,
        size: f32,
        round: bool,
        scale: f32,
    ) -> egui::Response {
        let (rect, response) = ui.allocate_exact_size(Vec2::splat(size), egui::Sense::click());
        let radius = size * 0.5 - 2.0 * scale;
        let center = rect.center();
        let points = design::ring_points(center, radius, if round { radius } else { size * 0.30 });
        ui.painter().add(egui::Shape::line(
            points.clone(),
            Stroke::new(4.0 * scale, Color32::from_gray(46)),
        ));
        if let Some(used) = account.used() {
            let progress = design::trim_path(&points, used.clamp(0.0, 100.0) / 100.0);
            if progress.len() > 1 {
                let color = if used >= 100.0 {
                    Color32::LIGHT_RED
                } else {
                    account.signal()
                };
                ui.painter().add(egui::Shape::line(
                    progress.clone(),
                    Stroke::new(4.0 * scale, color),
                ));
                for point in [progress[0], *progress.last().unwrap()] {
                    ui.painter().circle_filled(point, 2.0 * scale, color);
                }
            }
        }
        let icon = match account.provider.as_str() {
            "Claude" => self.icons.first(),
            "Codex" => self.icons.get(1),
            _ => None,
        };
        if let Some(icon) = icon {
            ui.painter().image(
                icon.id(),
                egui::Rect::from_center_size(center, Vec2::splat(size * 0.43)),
                egui::Rect::from_min_max(Pos2::ZERO, Pos2::new(1.0, 1.0)),
                Color32::WHITE,
            );
        } else {
            design::cube(
                ui.painter(),
                egui::Rect::from_center_size(center, Vec2::splat(size * 0.43)),
            );
        }
        response
    }
    fn card(
        &self,
        ui: &mut egui::Ui,
        account: &Account,
        width: f32,
        show_all_windows: bool,
    ) -> egui::Response {
        egui::Frame::new()
            .fill(Color32::from_rgb(28, 28, 28))
            .corner_radius(18.0)
            .stroke(Stroke::new(1.0, Color32::from_rgb(43, 43, 43)))
            .inner_margin(16.0)
            .show(ui, |ui| {
                // The border consumes one point on each side in addition to padding.
                ui.set_width(width - 34.0);
                ui.spacing_mut().item_spacing.y = 14.0;
                ui.label(
                    egui::RichText::new(account.provider.to_uppercase())
                        .size(10.0)
                        .strong()
                        .color(account.color()),
                );
                ui.horizontal(|ui| {
                    self.ring(ui, account, 40.0, self.prefs.round, 1.0);
                    ui.add_space(4.0);
                    let title_width = (ui.available_width() - 70.0).max(20.0);
                    let mut job = egui::text::LayoutJob::simple(
                        account.title.clone(),
                        egui::FontId::proportional(13.0),
                        Color32::WHITE,
                        title_width,
                    );
                    job.wrap.max_rows = 2;
                    job.wrap.break_anywhere = false;
                    let title = ui.painter().layout_job(job);
                    ui.add_sized(
                        [title_width, 40.0],
                        egui::Label::new(title).halign(egui::Align::Min),
                    );
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(
                            egui::RichText::new(
                                account
                                    .used()
                                    .map(|v| format!("{v:.0}%"))
                                    .unwrap_or_else(|| "—".into()),
                            )
                            .size(25.0)
                            .strong()
                            .color(account.signal()),
                        );
                    });
                });
                ui.label(
                    egui::RichText::new(&account.email)
                        .size(11.0)
                        .color(Color32::from_gray(153)),
                );
                ui.horizontal(|ui| {
                    ui.label(if account.provider == "Claude" || account.plan.is_empty() {
                        &account.provider
                    } else {
                        &account.plan
                    });
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.colored_label(account.signal(), account.state_label());
                    });
                });
                let window_count = if show_all_windows || account.provider == "Cursor" {
                    account.windows.len()
                } else {
                    2
                };
                for window in account.windows.iter().take(window_count) {
                    ui.vertical(|ui| {
                        ui.spacing_mut().item_spacing.y = 4.0;
                        ui.horizontal(|ui| {
                            ui.label(&window.label);
                            ui.with_layout(
                                egui::Layout::right_to_left(egui::Align::Center),
                                |ui| {
                                    ui.label(format!("{:.0}% used", window.used));
                                },
                            );
                        });
                        let (rect, _) = ui.allocate_exact_size(
                            Vec2::new(ui.available_width(), 5.0),
                            egui::Sense::hover(),
                        );
                        ui.painter().rect_filled(rect, 2.5, Color32::from_gray(48));
                        ui.painter().rect_filled(
                            egui::Rect::from_min_size(
                                rect.min,
                                Vec2::new(
                                    rect.width() * window.used.clamp(0.0, 100.0) / 100.0,
                                    5.0,
                                ),
                            ),
                            2.5,
                            if window.used >= 100.0 {
                                Color32::LIGHT_RED
                            } else {
                                account.color()
                            },
                        );
                        ui.label(
                            egui::RichText::new(reset(window.reset_at))
                                .size(10.0)
                                .color(Color32::GRAY),
                        );
                        if let Some(detail) = &window.detail {
                            ui.small(detail);
                        }
                    });
                }
                if !account.message.is_empty() {
                    ui.label(
                        egui::RichText::new(&account.message)
                            .size(12.0)
                            .color(Color32::GRAY),
                    );
                }
                ui.vertical(|ui| {
                    ui.spacing_mut().item_spacing.y = 6.0;
                    ui.separator();
                    ui.label(
                        egui::RichText::new(format!(
                            "Today · local {} usage",
                            if account.provider == "Cursor" {
                                "Cursor CLI"
                            } else {
                                &account.provider
                            }
                        ))
                        .size(11.0)
                        .strong(),
                    );
                    let usage = account.local_usage.as_ref();
                    for (label, value) in [
                        (
                            if usage.and_then(|u| u.estimated).unwrap_or(false) {
                                "Tokens (estimated)"
                            } else {
                                "Tokens"
                            },
                            count(usage.and_then(|u| u.tokens)),
                        ),
                        ("API-equivalent cost", money(usage.and_then(|u| u.cost_usd))),
                    ] {
                        ui.horizontal(|ui| {
                            ui.label(label);
                            ui.with_layout(
                                egui::Layout::right_to_left(egui::Align::Center),
                                |ui| {
                                    ui.label(value);
                                },
                            );
                        });
                    }
                    if let Some(usage) = usage {
                        ui.small(format!(
                            "Input {} · Output {}",
                            count(usage.input_tokens),
                            count(usage.output_tokens)
                        ));
                        ui.small(format!(
                            "Cache read {} · Write {}",
                            count(usage.cache_read_tokens),
                            count(usage.cache_write_tokens)
                        ));
                        if usage.status == "partial" {
                            ui.small("Indexing · totals are incomplete");
                        }
                        if usage.status == "stale" {
                            ui.small(format!(
                                "Cached · {}m ago",
                                ((now() - usage.fetched_at.unwrap_or(now())) / 60.0).max(0.0)
                                    as u64
                            ));
                        }
                        if let Some(message) = &usage.message {
                            if !message.is_empty() {
                                ui.small(message);
                            }
                        }
                        if usage.unpriced_models.unwrap_or(0) > 0 {
                            ui.small("Some models have no price; cost is incomplete.");
                        }
                    } else {
                        ui.small("Usage unavailable · install CodeBurn using the setup CLI.");
                    }
                    ui.small("CodeBurn · all local accounts · not your bill");
                    if let Some(spend) = account.on_demand_usd {
                        ui.label(format!("On-demand · billing cycle: ${spend:.2}"));
                    }
                });
                ui.label(
                    egui::RichText::new(&account.source)
                        .size(10.0)
                        .color(Color32::GRAY),
                );
            })
            .response
    }
}
impl eframe::App for Dock {
    fn clear_color(&self, _: &egui::Visuals) -> [f32; 4] {
        [0.0, 0.0, 0.0, 0.0]
    }
    fn save(&mut self, storage: &mut dyn eframe::Storage) {
        if !self.preview {
            eframe::set_value(storage, "preferences", &self.prefs);
        }
    }
    fn update(&mut self, ctx: &egui::Context, frame: &mut eframe::Frame) {
        while let Ok(update) = self.receiver.try_recv() {
            match update {
                Update::Accounts(result) => {
                    self.refreshing = false;
                    let queued = std::mem::take(&mut self.queued_action);
                    if !queued.is_empty() {
                        let queued: Vec<&str> = queued.iter().map(String::as_str).collect();
                        self.refresh(ctx.clone(), false, &queued);
                    }
                    match result {
                        Ok(snapshot) => {
                            self.accounts = snapshot.accounts;
                            self.hidden = snapshot.hidden;
                            self.hovered = self.hovered.as_ref().and_then(|hovered| {
                                self.accounts
                                    .iter()
                                    .find(|account| account.id == hovered.id)
                                    .cloned()
                            });
                            self.error = None;
                        }
                        Err(error) => self.error = Some(error),
                    }
                }
                Update::Usage(result) => {
                    self.usage_loading = false;
                    if let Ok(usage) = result {
                        for account in &mut self.accounts {
                            account.local_usage = usage.get(&account.provider).cloned();
                        }
                    }
                }
            }
        }
        if !self.preview && self.last_usage.elapsed() >= Duration::from_secs(300) {
            self.refresh_usage(ctx.clone(), false);
        }
        if !self.preview && self.last_poll.elapsed() >= Duration::from_secs(10) {
            self.refresh(ctx.clone(), false, &[]);
        }
        ctx.request_repaint_after(Duration::from_secs(1));
        if self.drag_anchor.is_some() {
            ctx.request_repaint_after(Duration::from_millis(16));
            if let Some(frame) = ctx.input(|i| i.viewport().outer_rect) {
                if self.drag_position != Some(frame.min) {
                    self.drag_position = Some(frame.min);
                    self.last_drag_move = Instant::now();
                }
                if self.last_drag_move.elapsed() >= Duration::from_millis(150)
                    && !ctx.input(|i| i.pointer.primary_down())
                {
                    self.drag_anchor = None;
                    if let Some(screen) = ctx.input(|i| i.viewport().monitor_size) {
                        let (edge, offset) = snap_edge(frame, screen);
                        self.prefs.edge = edge.into();
                        self.prefs.offset = offset;
                    }
                    self.layout = None;
                }
            }
        }
        self.position(ctx);
        egui::CentralPanel::default()
            .frame(egui::Frame::NONE)
            .show(ctx, |ui| {
                let rect = ui.max_rect();
                // Register the background before child controls so it cannot cover them.
                let background = ui.interact(rect, ui.id().with("context"), egui::Sense::click());
                design::dock(
                    ui.painter(),
                    rect,
                    &self.prefs.edge,
                    self.prefs.opacity,
                    self.prefs.size,
                );
                let scale = self.prefs.size;
                let horizontal = self.prefs.edge == "top" || self.prefs.edge == "bottom";
                let pad = if self.prefs.edge == "floating" {
                    12.0
                } else {
                    32.0
                } * scale;
                let drag_rect = egui::Rect::from_center_size(
                    if horizontal {
                        Pos2::new(pad + 6.0, rect.center().y)
                    } else {
                        Pos2::new(rect.center().x, pad + 6.0)
                    },
                    Vec2::splat(12.0 * scale),
                );
                for offset in [-3.0, 0.0, 3.0] {
                    ui.painter().line_segment(
                        [
                            drag_rect.center() + Vec2::new(-6.0, offset),
                            drag_rect.center() + Vec2::new(6.0, offset),
                        ],
                        Stroke::new(1.0, Color32::GRAY),
                    );
                }
                let drag = ui.interact(drag_rect, ui.id().with("drag"), egui::Sense::drag());
                if drag.drag_started() {
                    self.drag_anchor = ctx.input(|i| i.viewport().outer_rect.map(|r| r.min));
                    self.drag_position = self.drag_anchor;
                    self.last_drag_move = Instant::now();
                    self.hovered = None;
                    ctx.send_viewport_cmd(egui::ViewportCommand::StartDrag);
                }
                let area = if horizontal {
                    egui::Rect::from_min_max(
                        Pos2::new(54.0 * scale, 14.0 * scale),
                        Pos2::new(rect.max.x - 76.0 * scale, rect.max.y - 14.0 * scale),
                    )
                } else {
                    egui::Rect::from_min_max(
                        Pos2::new(12.0 * scale, pad + 20.0 * scale),
                        Pos2::new(rect.max.x - 12.0 * scale, rect.max.y - pad - 24.0 * scale),
                    )
                };
                let mut cells = ui.new_child(
                    egui::UiBuilder::new()
                        .max_rect(area)
                        .layout(egui::Layout::top_down(egui::Align::Center)),
                );
                let accounts = self.accounts.clone();
                let scroll = if horizontal {
                    egui::ScrollArea::horizontal()
                } else {
                    egui::ScrollArea::vertical()
                };
                let scroll = scroll
                    .scroll_bar_visibility(egui::scroll_area::ScrollBarVisibility::AlwaysHidden)
                    .show(&mut cells, |ui| {
                        if accounts.is_empty() {
                            ui.small("Discovering…");
                        }
                        if horizontal {
                            ui.horizontal(|ui| {
                                for account in &accounts {
                                    self.cell(ui, account, true);
                                }
                            });
                        } else {
                            for account in &accounts {
                                ui.push_id(&account.id, |ui| self.cell(ui, account, false));
                                ui.add_space(6.0 * scale);
                            }
                        }
                    });
                design::scroll_shadows(
                    ui.painter(),
                    scroll.inner_rect,
                    scroll.state.offset,
                    scroll.content_size,
                    horizontal,
                    scale,
                );
                let controls = if horizontal {
                    Pos2::new(rect.max.x - 60.0 * scale, rect.center().y)
                } else {
                    Pos2::new(
                        rect.center().x - 14.0 * scale,
                        rect.max.y - pad - 6.0 * scale,
                    )
                };
                let grid = egui::Rect::from_center_size(controls, Vec2::splat(16.0 * scale));
                for (x, y) in [(0.0, 0.0), (7.0, 0.0), (0.0, 7.0), (7.0, 7.0)] {
                    ui.painter().rect_filled(
                        egui::Rect::from_min_size(
                            grid.min + Vec2::new(x, y) * scale,
                            Vec2::splat(5.0 * scale),
                        ),
                        1.0,
                        Color32::WHITE,
                    );
                }
                if ui
                    .interact(grid, ui.id().with("overview"), egui::Sense::click())
                    .on_hover_text("Open all accounts")
                    .clicked()
                {
                    self.overview = true;
                }
                let gear = egui::Rect::from_center_size(
                    controls + Vec2::new(28.0 * scale, 0.0),
                    Vec2::splat(16.0 * scale),
                );
                let points = (0..32)
                    .map(|i| {
                        let a = i as f32 / 32.0 * std::f32::consts::TAU;
                        gear.center()
                            + Vec2::angled(a)
                                * if i % 4 == 0 || i % 4 == 3 {
                                    7.0 * scale
                                } else {
                                    5.5 * scale
                                }
                    })
                    .collect();
                ui.painter().add(egui::Shape::closed_line(
                    points,
                    Stroke::new(1.0, Color32::WHITE),
                ));
                ui.painter().circle_stroke(
                    gear.center(),
                    2.5 * scale,
                    Stroke::new(1.0, Color32::WHITE),
                );
                if ui
                    .interact(gear, ui.id().with("settings"), egui::Sense::click())
                    .on_hover_text("Dock settings")
                    .clicked()
                {
                    self.settings = true;
                }
                background.context_menu(|ui| {
                    if ui.button("Dock settings…").clicked() {
                        self.settings = true;
                        ui.close();
                    }
                    if ui.button("All accounts").clicked() {
                        self.overview = true;
                        ui.close();
                    }
                    if ui.button("Refresh").clicked() {
                        self.refresh(ctx.clone(), true, &[]);
                        ui.close();
                    }
                    if ui.button("Quit").clicked() {
                        ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                    }
                });
            });
        if !self.preview && self.last_hover.elapsed() > Duration::from_millis(350) {
            self.hovered = None;
        }
        if self.drag_anchor.is_some() {
            self.hovered = None;
        }
        if let Some(account) = self.hovered.clone() {
            if !self.preview {
                ctx.request_repaint_after(
                    Duration::from_millis(350).saturating_sub(self.last_hover.elapsed()),
                );
            }
            let root = ctx
                .input(|i| i.viewport().outer_rect)
                .unwrap_or(egui::Rect::from_min_size(
                    Pos2::ZERO,
                    Vec2::new(88.0, 820.0),
                ));
            let x = if root.min.x >= 374.0 {
                root.min.x - 374.0
            } else {
                root.max.x + 8.0
            };
            let screen_height = ctx
                .input(|i| i.viewport().monitor_size.map(|s| s.y))
                .unwrap_or(root.max.y);
            let y = (root.min.y + self.hover_anchor.y - self.hover_height * 0.5)
                .clamp(0.0, (screen_height - self.hover_height).max(0.0));
            ctx.show_viewport_immediate(
                egui::ViewportId::from_hash_of("hover"),
                egui::ViewportBuilder::default()
                    .with_title("Mako Capacity — Details")
                    .with_decorations(false)
                    .with_inner_size([366.0, self.hover_height])
                    .with_transparent(true)
                    .with_has_shadow(false)
                    .with_position([x, y])
                    .with_always_on_top(),
                |ctx, _| {
                    if ctx.input(|i| i.pointer.hover_pos().is_some()) {
                        self.last_hover = Instant::now();
                    }
                    egui::CentralPanel::default()
                        .frame(egui::Frame::NONE)
                        .show(ctx, |ui| {
                            let points_left = root.min.x < 374.0;
                            design::bubble(
                                ui.painter(),
                                ui.max_rect(),
                                points_left,
                                root.min.y + self.hover_anchor.y - y,
                            );
                            let left = if points_left { 28.0 } else { 8.0 };
                            let mut card_ui = ui.new_child(egui::UiBuilder::new().max_rect(
                                egui::Rect::from_min_size(
                                    Pos2::new(left, 8.0),
                                    Vec2::new(330.0, 600.0),
                                ),
                            ));
                            let response = self.card(&mut card_ui, &account, 330.0, true);
                            let height = (response.rect.height() + 16.0).ceil();
                            if (self.hover_height - height).abs() > 0.5 {
                                self.hover_height = height;
                                ctx.request_repaint();
                            }
                        });
                },
            );
        }
        if self.overview {
            ctx.show_viewport_immediate(
                egui::ViewportId::from_hash_of("overview"),
                egui::ViewportBuilder::default()
                    .with_title("Mako Capacity — All accounts")
                    .with_inner_size([1120.0, 880.0])
                    .with_min_inner_size([1040.0, 550.0]),
                |ctx, _| {
                    if ctx.input(|i| i.viewport().close_requested()) {
                        self.overview = false;
                    }
                    egui::CentralPanel::default()
                        .frame(
                            egui::Frame::NONE
                                .fill(Color32::from_rgb(30, 30, 30))
                                .inner_margin(24.0),
                        )
                        .show(ctx, |ui| self.overview_ui(ui));
                },
            );
        }
        if self.settings {
            let previous = self.prefs.clone();
            ctx.show_viewport_immediate(
                egui::ViewportId::from_hash_of("settings"),
                egui::ViewportBuilder::default()
                    .with_title("Mako Capacity — Settings")
                    .with_inner_size([390.0, 430.0])
                    .with_resizable(false),
                |ctx, _| {
                    if ctx.input(|i| i.viewport().close_requested()) {
                        self.settings = false;
                    }
                    egui::CentralPanel::default()
                        .frame(
                            egui::Frame::NONE
                                .fill(Color32::from_rgb(30, 30, 30))
                                .inner_margin(26.0),
                        )
                        .show(ctx, |ui| {
                            self.settings_ui(ui);
                        });
                },
            );
            if self.prefs != previous {
                self.layout = None;
                self.position(ctx);
                ctx.request_repaint();
                if !self.preview {
                    if let Some(storage) = frame.storage_mut() {
                        self.save(storage);
                        storage.flush();
                    }
                }
            }
        }
    }
}
fn main() -> eframe::Result {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("Mako Capacity")
            .with_inner_size([88.0, 720.0])
            .with_decorations(false)
            .with_transparent(true)
            .with_has_shadow(false)
            .with_always_on_top(),
        ..Default::default()
    };
    eframe::run_native(
        "Mako Capacity",
        options,
        Box::new(|cc| Ok(Box::new(Dock::new(cc)))),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    fn test_dock() -> Dock {
        let (sender, receiver) = mpsc::channel();
        Dock {
            accounts: vec![],
            hidden: HashMap::new(),
            confirm_delete: None,
            show_hidden: false,
            queued_action: vec![],
            prefs: Preferences::default(),
            error: None,
            refreshing: false,
            hovered: None,
            last_hover: Instant::now(),
            preview: true,
            receiver,
            sender,
            last_poll: Instant::now(),
            last_usage: Instant::now(),
            usage_loading: false,
            overview: false,
            settings: false,
            icons: vec![],
            layout: None,
            drag_anchor: None,
            last_drag_move: Instant::now(),
            drag_position: None,
            hover_height: 450.0,
            hover_anchor: Pos2::ZERO,
        }
    }
    fn settings_pass(
        ctx: &egui::Context,
        dock: &mut Dock,
        events: Vec<egui::Event>,
    ) -> egui::FullOutput {
        ctx.run(
            egui::RawInput {
                screen_rect: Some(egui::Rect::from_min_size(
                    Pos2::ZERO,
                    Vec2::new(390.0, 478.0),
                )),
                events,
                ..Default::default()
            },
            |ctx| {
                egui::CentralPanel::default()
                    .frame(egui::Frame::NONE.inner_margin(26.0))
                    .show(ctx, |ui| dock.settings_ui(ui));
            },
        )
    }
    fn click_setting(ctx: &egui::Context, dock: &mut Dock, pos: Pos2) -> egui::FullOutput {
        settings_pass(ctx, dock, vec![egui::Event::PointerMoved(pos)]);
        settings_pass(
            ctx,
            dock,
            vec![egui::Event::PointerButton {
                pos,
                button: egui::PointerButton::Primary,
                pressed: true,
                modifiers: Default::default(),
            }],
        );
        settings_pass(
            ctx,
            dock,
            vec![egui::Event::PointerButton {
                pos,
                button: egui::PointerButton::Primary,
                pressed: false,
                modifiers: Default::default(),
            }],
        )
    }
    fn text_position(output: &egui::FullOutput, text: &str) -> Pos2 {
        output
            .shapes
            .iter()
            .find_map(|shape| match &shape.shape {
                egui::Shape::Text(shape) if shape.galley.text() == text => {
                    Some(shape.pos + shape.galley.size() * 0.5)
                }
                _ => None,
            })
            .unwrap_or_else(|| panic!("missing {text}"))
    }
    #[test]
    fn dock_length_adapts_to_accounts_and_label_visibility() {
        let mut dock = test_dock();
        let empty = dock.dock_length();
        dock.accounts = vec![Account::default(); 3];
        assert_eq!(dock.dock_length(), 354.0);
        assert!(dock.dock_length() > empty);
        dock.prefs.labels = false;
        assert_eq!(dock.dock_length(), 318.0);
        dock.accounts[0].provider = "Cursor".into();
        assert_eq!(dock.dock_length(), 334.0);
        dock.prefs.edge = "top".into();
        assert_eq!(dock.dock_length(), 362.0);
    }
    #[test]
    fn settings_controls_change_preferences_and_restore_defaults() {
        let ctx = egui::Context::default();
        let mut dock = test_dock();
        settings_pass(&ctx, &mut dock, vec![]);
        let output = settings_pass(&ctx, &mut dock, vec![]);
        let handle = output
            .shapes
            .iter()
            .find_map(|shape| match &shape.shape {
                egui::Shape::Circle(circle) => Some(circle.center),
                _ => None,
            })
            .unwrap();
        let output = click_setting(&ctx, &mut dock, Pos2::new(350.0, handle.y));
        assert!(dock.prefs.size >= 1.3, "size slider did not apply");
        let circle = text_position(&output, "Circle");
        let output = click_setting(&ctx, &mut dock, circle);
        assert!(dock.prefs.round, "shape button did not apply");
        let names = text_position(&output, "Show account names");
        let output = click_setting(&ctx, &mut dock, names);
        assert!(!dock.prefs.labels, "names checkbox did not apply");
        let edge = text_position(&output, "Right");
        click_setting(&ctx, &mut dock, edge);
        let output = settings_pass(&ctx, &mut dock, vec![]);
        let left = text_position(&output, "Left");
        let output = click_setting(&ctx, &mut dock, left);
        assert_eq!(dock.prefs.edge, "left", "edge selector did not apply");
        let reset = text_position(&output, "Restore defaults");
        click_setting(&ctx, &mut dock, reset);
        assert!(
            dock.prefs == Preferences::default(),
            "restore defaults did not apply"
        );
    }
    #[test]
    fn overview_has_four_columns_and_keeps_cards_inside_the_window() {
        let ctx = egui::Context::default();
        let mut dock = test_dock();
        dock.accounts = (0..8)
            .map(|i| Account {
                id: i.to_string(),
                provider: "Claude".into(),
                title: format!("Account {i}"),
                email: "long-email-address@example.test".into(),
                status: "live".into(),
                ..Default::default()
            })
            .collect();
        let mut draw = || {
            ctx.run(
                egui::RawInput {
                    screen_rect: Some(egui::Rect::from_min_size(
                        Pos2::ZERO,
                        Vec2::new(1120.0, 880.0),
                    )),
                    ..Default::default()
                },
                |ctx| {
                    egui::CentralPanel::default()
                        .frame(egui::Frame::NONE.inner_margin(24.0))
                        .show(ctx, |ui| dock.overview_ui(ui));
                },
            )
        };
        draw();
        let output = draw();
        let titles: Vec<_> = (0..8)
            .map(|i| text_position(&output, &format!("Account {i}")))
            .collect();
        for row in titles.chunks(4) {
            for pair in row.windows(2) {
                assert!(pair[1].x - pair[0].x > 240.0);
                assert!((pair[1].y - pair[0].y).abs() < 1.0);
            }
        }
        assert!(titles[4].y > titles[0].y + 100.0);
        for shape in &output.shapes {
            if let egui::Shape::Rect(rect) = &shape.shape {
                if rect.fill == Color32::from_rgb(28, 28, 28) {
                    assert!(
                        rect.rect.min.x >= 24.0 && rect.rect.max.x <= 1096.0,
                        "card exceeds window: {:?}",
                        rect.rect
                    );
                }
            }
        }
    }
    #[test]
    fn drag_release_snaps_to_each_edge_and_preserves_offset() {
        let screen = Vec2::new(1440.0, 900.0);
        for (position, expected) in [
            (Pos2::new(20.0, 100.0), "left"),
            (Pos2::new(1332.0, 100.0), "right"),
            (Pos2::new(200.0, 20.0), "top"),
            (Pos2::new(200.0, 680.0), "bottom"),
        ] {
            let (edge, offset) = snap_edge(
                egui::Rect::from_min_size(position, Vec2::new(88.0, 200.0)),
                screen,
            );
            assert_eq!(edge, expected);
            let expected_offset = if edge == "left" || edge == "right" {
                100.0 / 700.0
            } else {
                200.0 / 1352.0
            };
            assert!((offset - expected_offset).abs() < 0.001);
        }
        assert_eq!(
            snap_edge(
                egui::Rect::from_min_size(Pos2::new(49.0, 100.0), Vec2::new(88.0, 200.0)),
                screen
            )
            .0,
            "floating"
        );
        assert_eq!(
            snap_edge(
                egui::Rect::from_min_size(Pos2::new(48.0, 100.0), Vec2::new(88.0, 200.0)),
                screen
            )
            .0,
            "left"
        );
    }
    #[test]
    fn old_snapshots_and_missing_usage_are_supported() {
        let snapshot: Snapshot = serde_json::from_str(r#"{"accounts":[{"id":"1","provider":"Claude","title":"Test","email":"test@example.test","plan":"","status":"unknown","message":"","source":"test","windows":[] }]}"#).unwrap();
        assert_eq!(snapshot.accounts[0].used(), None);
        assert!(snapshot.accounts[0].local_usage.is_none());
        assert_eq!(money(None), "—");
    }
    #[test]
    fn snapshots_carry_hidden_accounts_and_proxy_references() {
        let snapshot: Snapshot = serde_json::from_str(r#"{"accounts":[{"id":"1","provider":"Codex","title":"Pro","email":"a@example.test","plan":"","status":"live","message":"","source":"test","windows":[],"proxyRef":"pool-1"}],"hidden":{"2":"Cursor · b"}}"#).unwrap();
        assert_eq!(snapshot.accounts[0].proxy_ref.as_deref(), Some("pool-1"));
        assert_eq!(
            snapshot.hidden.get("2").map(String::as_str),
            Some("Cursor · b")
        );
    }
    #[test]
    fn cursor_uses_models_quota_and_claude_uses_most_constrained_window() {
        let mut account = Account {
            provider: "Cursor".into(),
            windows: vec![
                Window {
                    label: "Cursor Models".into(),
                    used: 20.0,
                    ..Default::default()
                },
                Window {
                    label: "Other Models".into(),
                    used: 95.0,
                    ..Default::default()
                },
            ],
            ..Default::default()
        };
        assert_eq!(account.used(), Some(20.0));
        account.provider = "Claude".into();
        assert_eq!(account.used(), Some(95.0));
    }
}
