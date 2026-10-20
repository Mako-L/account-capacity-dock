//! Geometry ported from the original Swift dock, with CodeBurn MIT attribution.
use eframe::egui::{self, Color32, Pos2, Rect, Stroke, Vec2};
fn quad(points: &mut Vec<Pos2>, control: Pos2, end: Pos2) {
    let start = *points.last().unwrap();
    for i in 1..=16 {
        let t = i as f32 / 16.0;
        points.push(Pos2::new(
            (1.0 - t).powi(2) * start.x + 2.0 * (1.0 - t) * t * control.x + t * t * end.x,
            (1.0 - t).powi(2) * start.y + 2.0 * (1.0 - t) * t * control.y + t * t * end.y,
        ));
    }
}
fn cubic(points: &mut Vec<Pos2>, a: Pos2, b: Pos2, end: Pos2) {
    let start = *points.last().unwrap();
    for i in 1..=16 {
        let t = i as f32 / 16.0;
        let u = 1.0 - t;
        points.push(Pos2::new(
            u * u * u * start.x + 3.0 * u * u * t * a.x + 3.0 * u * t * t * b.x + t * t * t * end.x,
            u * u * u * start.y + 3.0 * u * u * t * a.y + 3.0 * u * t * t * b.y + t * t * t * end.y,
        ));
    }
}
fn cross(a: Pos2, b: Pos2, c: Pos2) -> f32 {
    (b - a).x * (c - a).y - (b - a).y * (c - a).x
}
fn polygon(painter: &egui::Painter, points: Vec<Pos2>, fill: Color32, stroke: Stroke) {
    // Ear clipping preserves the concave edge flares and bubble tail.
    let area: f32 = points
        .iter()
        .zip(points.iter().cycle().skip(1))
        .take(points.len())
        .map(|(a, b)| a.x * b.y - b.x * a.y)
        .sum();
    let mut indices: Vec<usize> = (0..points.len()).collect();
    if area < 0.0 {
        indices.reverse();
    }
    // Triangulated fills need their own antialias fringe along the curved boundary.
    let boundary = points.clone();
    let aa = 1.0 / painter.ctx().pixels_per_point();
    let outward: Vec<Vec2> = (0..points.len())
        .map(|i| {
            let previous = points[(i + points.len() - 1) % points.len()];
            let next = points[(i + 1) % points.len()];
            let normal = |v: Vec2| Vec2::new(v.y, -v.x).normalized() * area.signum();
            let a = normal(points[i] - previous);
            let b = normal(next - points[i]);
            let bisector = (a + b).normalized();
            bisector / bisector.dot(b).max(0.2)
        })
        .collect();
    let points: Vec<Pos2> = boundary
        .iter()
        .zip(&outward)
        .map(|(p, n)| *p - *n * aa * 0.5)
        .collect();
    let mut mesh = egui::Mesh::default();
    for p in &points {
        mesh.colored_vertex(*p, fill);
    }
    while indices.len() > 2 {
        let mut found = false;
        for i in 0..indices.len() {
            let (a, b, c) = (
                indices[(i + indices.len() - 1) % indices.len()],
                indices[i],
                indices[(i + 1) % indices.len()],
            );
            if cross(points[a], points[b], points[c]) <= 0.001 {
                continue;
            }
            if indices.iter().any(|&p| {
                p != a
                    && p != b
                    && p != c
                    && cross(points[a], points[b], points[p]) >= 0.0
                    && cross(points[b], points[c], points[p]) >= 0.0
                    && cross(points[c], points[a], points[p]) >= 0.0
            }) {
                continue;
            }
            mesh.add_triangle(a as u32, b as u32, c as u32);
            indices.remove(i);
            found = true;
            break;
        }
        if !found {
            break;
        }
    }
    let count = boundary.len() as u32;
    for (point, normal) in boundary.iter().zip(&outward) {
        mesh.colored_vertex(*point + *normal * aa * 0.5, Color32::TRANSPARENT);
    }
    for i in 0..count {
        let next = (i + 1) % count;
        mesh.add_triangle(i, next, count + i);
        mesh.add_triangle(next, count + next, count + i);
    }
    painter.add(egui::Shape::mesh(mesh));
    painter.add(egui::Shape::closed_line(boundary, stroke));
}
pub fn dock(painter: &egui::Painter, rect: Rect, edge: &str, opacity: f32, scale: f32) {
    let fill = Color32::from_rgba_unmultiplied(17, 17, 17, (opacity * 255.0) as u8);
    let stroke = Stroke::new(scale, Color32::from_white_alpha(31));
    if edge == "floating" {
        painter.rect(rect, 24.0 * scale, fill, stroke, egui::StrokeKind::Inside);
        return;
    }
    let vertical = edge == "left" || edge == "right";
    let (w, h) = if vertical {
        (rect.width() / scale, rect.height() / scale)
    } else {
        (rect.height() / scale, rect.width() / scale)
    };
    let mut p = vec![Pos2::new(w, 0.0)];
    quad(&mut p, Pos2::new(w, 26.0), Pos2::new(w - 26.0, 26.0));
    p.push(Pos2::new(24.0, 24.0));
    quad(&mut p, Pos2::new(0.0, 24.0), Pos2::new(0.0, 48.0));
    p.push(Pos2::new(0.0, h - 48.0));
    quad(&mut p, Pos2::new(0.0, h - 24.0), Pos2::new(24.0, h - 24.0));
    p.push(Pos2::new(w - 26.0, h - 24.0));
    quad(&mut p, Pos2::new(w, h - 26.0), Pos2::new(w, h));
    for point in &mut p {
        *point = match edge {
            "left" => Pos2::new(w - point.x, point.y),
            "bottom" => Pos2::new(h - point.y, point.x),
            "top" => Pos2::new(h - point.y, w - point.x),
            _ => *point,
        } * scale
            + rect.min.to_vec2();
    }
    polygon(painter, p, fill, stroke);
}
pub fn bubble(painter: &egui::Painter, rect: Rect, points_left: bool, tail_y: f32) {
    let (w, h) = (rect.width(), rect.height());
    let right = w - 20.0;
    let mid = tail_y.clamp(50.0, (h - 50.0).max(50.0));
    let mut p = vec![Pos2::new(20.0, 0.0), Pos2::new(right - 20.0, 0.0)];
    quad(&mut p, Pos2::new(right, 0.0), Pos2::new(right, 20.0));
    p.push(Pos2::new(right, mid - 30.0));
    cubic(
        &mut p,
        Pos2::new(right, mid - 16.0),
        Pos2::new(w, mid - 8.0),
        Pos2::new(w, mid),
    );
    cubic(
        &mut p,
        Pos2::new(w, mid + 8.0),
        Pos2::new(right, mid + 16.0),
        Pos2::new(right, mid + 30.0),
    );
    p.push(Pos2::new(right, h - 20.0));
    quad(&mut p, Pos2::new(right, h), Pos2::new(right - 20.0, h));
    p.push(Pos2::new(20.0, h));
    quad(&mut p, Pos2::new(0.0, h), Pos2::new(0.0, h - 20.0));
    p.push(Pos2::new(0.0, 20.0));
    quad(&mut p, Pos2::ZERO, Pos2::new(20.0, 0.0));
    p.pop();
    for point in &mut p {
        if points_left {
            point.x = w - point.x;
        }
        *point += rect.min.to_vec2();
    }
    polygon(painter, p, Color32::from_rgb(17, 17, 17), Stroke::NONE);
}
// One continuous rounded outline is shared by the track and progress stroke.
pub fn ring_points(center: Pos2, radius: f32, corner: f32) -> Vec<Pos2> {
    let corner = corner.min(radius);
    let mut points = vec![center + Vec2::new(0.0, -radius)];
    for (x, y, angle) in [
        (1.0, -1.0, -90.0_f32),
        (1.0, 1.0, 0.0),
        (-1.0, 1.0, 90.0),
        (-1.0, -1.0, 180.0),
    ] {
        let arc_center = center + Vec2::new(x, y) * (radius - corner);
        for step in 0..=20 {
            let angle = (angle + step as f32 * 4.5).to_radians();
            points.push(arc_center + Vec2::angled(angle) * corner);
        }
    }
    points.push(points[0]);
    points
}
pub fn trim_path(points: &[Pos2], fraction: f32) -> Vec<Pos2> {
    let length: f32 = points.windows(2).map(|p| (p[1] - p[0]).length()).sum();
    let mut remaining = length * fraction;
    let mut trimmed = vec![points[0]];
    for pair in points.windows(2) {
        let distance = (pair[1] - pair[0]).length();
        if distance <= f32::EPSILON {
            continue;
        }
        if remaining < distance {
            if remaining > 0.0 {
                trimmed.push(pair[0] + (pair[1] - pair[0]) * (remaining / distance));
            }
            break;
        }
        trimmed.push(pair[1]);
        remaining -= distance;
    }
    trimmed
}
// Match Bubo's ShadowScrollView: 36-point gradients, a 24-point reveal range,
// and no shadows when the content fits. Painting overlays leaves input untouched.
pub fn scroll_shadow_strength(offset: f32, content: f32, viewport: f32, scale: f32) -> (f32, f32) {
    let maximum = (content - viewport).max(0.0);
    if maximum <= 0.5 {
        return (0.0, 0.0);
    }
    let offset = offset.clamp(0.0, maximum);
    (
        (offset / (24.0 * scale)).clamp(0.0, 1.0),
        if maximum - offset > 24.0 * scale {
            1.0
        } else {
            0.0
        },
    )
}
pub fn scroll_shadows(
    painter: &egui::Painter,
    rect: Rect,
    offset: Vec2,
    content: Vec2,
    horizontal: bool,
    scale: f32,
) {
    let (position, length, viewport) = if horizontal {
        (offset.x, content.x, rect.width())
    } else {
        (offset.y, content.y, rect.height())
    };
    let (start, end) = scroll_shadow_strength(position, length, viewport, scale);
    let depth = (36.0 * scale).min(viewport * 0.5);
    let painter = painter.with_clip_rect(rect);
    for (trailing, strength) in [(false, start), (true, end)] {
        if strength == 0.0 {
            continue;
        }
        let band = if horizontal {
            if trailing {
                Rect::from_min_max(Pos2::new(rect.max.x - depth, rect.min.y), rect.max)
            } else {
                Rect::from_min_max(rect.min, Pos2::new(rect.min.x + depth, rect.max.y))
            }
        } else if trailing {
            Rect::from_min_max(Pos2::new(rect.min.x, rect.max.y - depth), rect.max)
        } else {
            Rect::from_min_max(rect.min, Pos2::new(rect.max.x, rect.min.y + depth))
        };
        let shadow = Color32::from_black_alpha((46.0 * strength).round() as u8);
        let (near, far) = if trailing {
            (Color32::TRANSPARENT, shadow)
        } else {
            (shadow, Color32::TRANSPARENT)
        };
        let mut mesh = egui::Mesh::default();
        mesh.colored_vertex(band.left_top(), near);
        mesh.colored_vertex(band.right_top(), if horizontal { far } else { near });
        mesh.colored_vertex(band.right_bottom(), far);
        mesh.colored_vertex(band.left_bottom(), if horizontal { near } else { far });
        mesh.add_triangle(0, 1, 2);
        mesh.add_triangle(0, 2, 3);
        painter.add(egui::Shape::mesh(mesh));
    }
}
pub fn cube(painter: &egui::Painter, rect: Rect) {
    let points = [
        (12.0, 0.13),
        (1.89, 5.68),
        (1.47, 6.4),
        (1.47, 17.59),
        (1.89, 18.31),
        (11.5, 23.86),
        (12.5, 23.86),
        (22.11, 18.31),
        (22.53, 17.59),
        (22.53, 6.4),
        (22.11, 5.68),
        (12.5, 0.13),
    ];
    let p: Vec<_> = points
        .iter()
        .map(|(x, y)| rect.min + Vec2::new(x / 24.0 * rect.width(), y / 24.0 * rect.height()))
        .collect();
    polygon(painter, p, Color32::WHITE, Stroke::NONE);
    let points = [
        (2.66, 6.34),
        (21.21, 6.34),
        (21.51, 6.85),
        (12.23, 22.92),
        (12.0, 22.86),
        (12.0, 12.34),
        (11.7, 11.83),
        (2.59, 6.57),
    ];
    let p: Vec<_> = points
        .iter()
        .map(|(x, y)| rect.min + Vec2::new(x / 24.0 * rect.width(), y / 24.0 * rect.height()))
        .collect();
    polygon(painter, p, Color32::from_rgb(17, 17, 17), Stroke::NONE);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scroll_shadows_follow_bubo_overflow_and_edge_rules() {
        assert_eq!(scroll_shadow_strength(0.0, 100.0, 200.0, 1.0), (0.0, 0.0));
        assert_eq!(scroll_shadow_strength(0.0, 500.0, 200.0, 1.0), (0.0, 1.0));
        assert_eq!(scroll_shadow_strength(12.0, 500.0, 200.0, 1.0), (0.5, 1.0));
        assert_eq!(scroll_shadow_strength(24.0, 500.0, 200.0, 1.0), (1.0, 1.0));
        assert_eq!(scroll_shadow_strength(276.0, 500.0, 200.0, 1.0), (1.0, 0.0));
        assert_eq!(scroll_shadow_strength(300.0, 500.0, 200.0, 1.0), (1.0, 0.0));
        assert_eq!(
            scroll_shadow_strength(12.0 * 0.65, 500.0 * 0.65, 200.0 * 0.65, 0.65),
            (0.5, 1.0)
        );
    }
    #[test]
    fn rounded_ring_track_and_progress_share_the_top_right_curve() {
        let outline = ring_points(Pos2::ZERO, 19.0, 12.0);
        let progress = trim_path(&outline, 0.42);
        assert_eq!(progress[0], outline[0]);
        assert_eq!(
            &progress[..progress.len() - 1],
            &outline[..progress.len() - 1]
        );
        // The top-right curve is a circular arc, with no square corner in either stroke.
        for point in &outline[1..22] {
            assert!(((*point - Pos2::new(7.0, -7.0)).length() - 12.0).abs() < 0.001);
        }
        assert_eq!(outline.first(), outline.last());
    }
    #[test]
    fn attached_dock_geometry_scales_with_the_icons() {
        for edge in ["left", "right", "top", "bottom"] {
            let vertices = |scale: f32| {
                let ctx = egui::Context::default();
                let output = ctx.run(egui::RawInput::default(), |ctx| {
                    let painter = ctx.layer_painter(egui::LayerId::background());
                    let size = if edge == "left" || edge == "right" {
                        Vec2::new(88.0, 820.0)
                    } else {
                        Vec2::new(820.0, 114.0)
                    } * scale;
                    dock(
                        &painter,
                        Rect::from_min_size(Pos2::ZERO, size),
                        edge,
                        1.0,
                        scale,
                    );
                });
                let shapes = output.shapes;
                shapes
                    .into_iter()
                    .find_map(|shape| match shape.shape {
                        egui::Shape::Path(path) => {
                            Some(path.points.iter().map(|p| *p / scale).collect::<Vec<_>>())
                        }
                        _ => None,
                    })
                    .unwrap()
            };
            let baseline = vertices(1.0);
            for scale in [0.65, 0.8, 1.4] {
                let actual = vertices(scale);
                assert_eq!(actual.len(), baseline.len());
                for (a, b) in actual.iter().zip(&baseline) {
                    assert!(
                        (*a - *b).length() < 0.001,
                        "{edge} at {scale}: {a:?} vs {b:?}"
                    );
                }
            }
        }
    }
}
