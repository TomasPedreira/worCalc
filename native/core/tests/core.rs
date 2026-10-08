use flate2::{write::ZlibEncoder, Compression};
use std::io::Write;
use worcalc_core::{
    physics::{Launch, Physics, ProfilePoint},
    terrain::Terrain,
    METRES_TO_YARDS,
};
fn terrain_payload() -> Vec<u8> {
    let mut b = b"WRT1".to_vec();
    for v in [2u32, 1, 2, 1] {
        b.extend(v.to_le_bytes());
    }
    for v in [0i32, 0, 3, 0, 1] {
        b.extend(v.to_le_bytes());
    }
    // X-major asymmetric plane with a hole at the opposite cell.
    for x in 0..3 {
        for y in 0..3 {
            let raw = ((x * 20 + y * 40) << 4) | if x == 1 && y == 1 { 15 } else { 0 };
            b.extend((raw as u16).to_le_bytes());
        }
    }
    b
}
fn compressed(b: &[u8]) -> Vec<u8> {
    let mut z = ZlibEncoder::new(vec![], Compression::best());
    z.write_all(b).unwrap();
    z.finish().unwrap()
}
#[test]
fn terrain_preserves_axes_triangle_interpolation_holes_and_world_bounds() {
    let terrain = Terrain::decode(&compressed(&terrain_payload())).unwrap();
    assert!((terrain.elevation(0.25, 0.5).unwrap() - 1.25).abs() < 1e-12);
    assert_eq!(terrain.elevation(1.1, 1.1), None);
    assert_eq!(terrain.elevation(-0.001, 1.), None);
    assert_eq!(terrain.elevation(2., 0.), None);
    assert_eq!(terrain.elevation(f64::NAN, 0.), None);
}
#[test]
fn terrain_rejects_corruption_instead_of_panicking_or_guessing_heights() {
    let good = terrain_payload();
    for length in [0, 3, 19, 25, 40, good.len() - 1] {
        assert!(Terrain::decode(&compressed(&good[..length])).is_err());
    }
    let mut bad = good.clone();
    bad[0] = 0;
    assert!(Terrain::decode(&compressed(&bad)).is_err());
    let mut bad = good.clone();
    bad[28..32].copy_from_slice(&500i32.to_le_bytes());
    assert!(Terrain::decode(&compressed(&bad)).is_err());
    let mut bad = good;
    bad.push(0);
    assert!(Terrain::decode(&compressed(&bad)).is_err());
}
#[test]
fn vacuum_matches_independent_closed_form_and_drag_limit_converges() {
    let solver = Physics {
        speed: 100.,
        drag: 0.,
        gravity: 9.81,
        launch: Launch {
            height_metres: 0.,
            forward_metres: 0.,
            angle_offset_deg: 0.,
            minimum_display_deg: -8.,
            maximum_display_deg: 45.,
        },
    };
    let aim = solver
        .solve(100. * METRES_TO_YARDS, 0., true)
        .unwrap()
        .unwrap();
    let expected = (9.81f64 * 100. / 10000.).asin().to_degrees() / 2.;
    assert!((aim.elevation_degrees - expected).abs() < 1e-8);
    let almost = Physics {
        drag: 1e-10,
        ..solver
    }
    .solve(100. * METRES_TO_YARDS, 0., true)
    .unwrap()
    .unwrap();
    assert!((aim.elevation_degrees - almost.elevation_degrees).abs() < 1e-7);
    assert!(solver.solve(f64::NAN, 0., false).is_err());
    assert!(solver.solve(0., 0., false).is_err());
}
#[test]
fn narrow_crest_is_detected_and_corrected_without_warping_the_arc() {
    let solver = Physics {
        speed: 370.,
        drag: 0.1,
        gravity: 9.1,
        launch: Launch::default(),
    };
    let profile: Vec<_> = (0..4001)
        .map(|i| ProfilePoint {
            distance_yards: i as f64 * 300. / 4000.,
            elevation_metres: if i == 1377 { 20. } else { 0. },
        })
        .collect();
    let clearance = solver.clearance(300., 0., &profile, true).unwrap().unwrap();
    assert!(clearance.obstructed);
    let angle = clearance.clearing_elevation_deg.unwrap();
    let ridge = &profile[1377];
    assert!((solver.at_distance(ridge.distance_yards, angle).unwrap().0 - 20.01).abs() < 1e-6);
    assert!(
        solver
            .at_distance(ridge.distance_yards, angle - 0.001)
            .unwrap()
            .0
            < 20.01
    );
}
