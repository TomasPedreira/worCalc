use serde::{Deserialize, Serialize};
#[derive(Clone, Copy, Deserialize, Serialize)]
pub struct Sample {
    pub elevation_degrees: f64,
    pub range_yards: f64,
}
#[derive(Clone, Copy, Deserialize, Serialize, Debug)]
pub struct EmpiricalAim {
    pub elevation_degrees: f64,
    pub distinct_settings: usize,
    pub sample_count: usize,
}
pub fn estimate(samples: &[Sample], target: f64) -> Option<EmpiricalAim> {
    let mut far: Vec<_> = samples
        .iter()
        .filter(|s| s.range_yards >= target * 0.75)
        .collect();
    far.sort_by(|a, b| a.elevation_degrees.total_cmp(&b.elevation_degrees));
    let mut grouped: Vec<(f64, f64, usize)> = vec![];
    for sample in &far {
        let angle = (sample.elevation_degrees * 100.).round_ties_even() / 100.;
        if let Some(last) = grouped.last_mut().filter(|p| p.0 == angle) {
            last.1 += sample.range_yards;
            last.2 += 1;
        } else {
            grouped.push((angle, sample.range_yards, 1));
        }
    }
    let points: Vec<_> = grouped.iter().map(|p| (p.0, p.1 / p.2 as f64)).collect();
    if points.len() < 3 {
        return None;
    }
    let min_a = points.first()?.0;
    let max_a = points.last()?.0;
    let min_r = points.iter().map(|p| p.1).fold(f64::INFINITY, f64::min);
    let max_r = points.iter().map(|p| p.1).fold(f64::NEG_INFINITY, f64::max);
    if max_a - min_a < 0.02 || max_r - min_r < 5. {
        return None;
    }
    let result = |a| EmpiricalAim {
        elevation_degrees: a,
        distinct_settings: points.len(),
        sample_count: far.len(),
    };
    let low = points
        .iter()
        .filter(|p| p.1 <= target)
        .max_by(|a, b| a.1.total_cmp(&b.1));
    let high = points
        .iter()
        .filter(|p| p.1 >= target)
        .min_by(|a, b| a.1.total_cmp(&b.1));
    if let (Some(low), Some(high)) = (low, high) {
        if high.1 > low.1 && high.0 > low.0 {
            return Some(result((low.0 + 0.01).min(high.0)));
        }
    }
    let mean_a = points.iter().map(|p| p.0).sum::<f64>() / points.len() as f64;
    let mean_r = points.iter().map(|p| p.1).sum::<f64>() / points.len() as f64;
    let denominator = points.iter().map(|p| (p.0 - mean_a).powi(2)).sum::<f64>();
    let slope = points
        .iter()
        .map(|p| (p.0 - mean_a) * (p.1 - mean_r))
        .sum::<f64>()
        / denominator;
    if slope <= 25. {
        return None;
    }
    let mut estimate = (target - (mean_r - slope * mean_a)) / slope;
    let remaining = target - max_r;
    if remaining > 75f64.max(target * 0.25) {
        return None;
    }
    if remaining > 0. && remaining <= 25. {
        estimate = estimate.min(max_a + 0.01);
    }
    if estimate < min_a - 0.25 || estimate > max_a + 0.25 {
        return None;
    }
    Some(result(estimate))
}
