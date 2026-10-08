//! Versioned runtime terrain: native grids, integer offsets and hole flags.
use crate::{
    physics::{Point, ProfilePoint},
    Result, METRES_TO_YARDS,
};
use flate2::read::ZlibDecoder;
use std::io::Read;

pub struct Tile {
    size: usize,
    offset: i32,
    step: i32,
    data: Vec<u16>,
}
pub struct Terrain {
    pub unit: u32,
    sector: u32,
    width: u32,
    side: usize,
    tiles: Vec<Tile>,
}
impl Tile {
    fn raw(&self, x: usize, y: usize) -> u16 {
        self.data[x * self.size + y]
    }
    fn height(&self, x: usize, y: usize) -> f64 {
        (self.offset as f64 + (self.raw(x, y) >> 4) as f64 * self.step as f64) * 0.05
    }
    fn vertex(&self, x: f64, y: f64) -> f64 {
        let ix = (x.floor() as usize).min(self.size - 2);
        let iy = (y.floor() as usize).min(self.size - 2);
        let fx = x - ix as f64;
        let fy = y - iy as f64;
        self.height(ix, iy) * (1. - fx) * (1. - fy)
            + self.height(ix + 1, iy) * fx * (1. - fy)
            + self.height(ix, iy + 1) * (1. - fx) * fy
            + self.height(ix + 1, iy + 1) * fx * fy
    }
}
struct Cursor<'a> {
    bytes: &'a [u8],
    pos: usize,
}
impl Cursor<'_> {
    fn take(&mut self, n: usize) -> Result<&[u8]> {
        let end = self.pos.checked_add(n).ok_or("Terrain length overflow")?;
        let result = self.bytes.get(self.pos..end).ok_or("Truncated terrain")?;
        self.pos = end;
        Ok(result)
    }
    fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
    fn i32(&mut self) -> Result<i32> {
        Ok(i32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
}
impl Terrain {
    pub fn decode(compressed: &[u8]) -> Result<Self> {
        let mut bytes = vec![];
        ZlibDecoder::new(compressed)
            .take(64 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)
            .map_err(|e| e.to_string())?;
        if bytes.len() > 64 * 1024 * 1024 {
            return Err("Terrain exceeds runtime size limit".into());
        }
        let mut cursor = Cursor {
            bytes: &bytes,
            pos: 0,
        };
        if cursor.take(4)? != b"WRT1" {
            return Err("Unsupported terrain format".into());
        }
        let size = cursor.u32()?;
        let unit = cursor.u32()?;
        let sector = cursor.u32()?;
        let count = cursor.u32()? as usize;
        if size == 0
            || size > 16384
            || unit == 0
            || unit > 32
            || sector == 0
            || sector % unit != 0
            || sector / unit < 2
            || sector / unit > 256
        {
            return Err("Invalid terrain dimensions".into());
        }
        let width = size * unit;
        if width % sector != 0 {
            return Err("Invalid terrain coverage".into());
        }
        let side = (width / sector) as usize;
        if count != side * side || count > 65536 {
            return Err("Invalid terrain tile count".into());
        }
        let mut tiles = Vec::with_capacity(count);
        for index in 0..count {
            let x = cursor.i32()?;
            let y = cursor.i32()?;
            let n = cursor.i32()?;
            let offset = cursor.i32()?;
            let step = cursor.i32()?;
            if x != (index / side) as i32
                || y != (index % side) as i32
                || n < 2
                || n as u32 > sector / unit + 1
                || !(n as u32 - 1).is_power_of_two()
                || step <= 0
            {
                return Err("Invalid terrain tile".into());
            }
            let data = cursor
                .take(n as usize * n as usize * 2)?
                .chunks_exact(2)
                .map(|b| u16::from_le_bytes([b[0], b[1]]))
                .collect();
            tiles.push(Tile {
                size: n as usize,
                offset,
                step,
                data,
            });
        }
        if cursor.pos != bytes.len() {
            return Err("Unexpected trailing terrain data".into());
        }
        Ok(Self {
            unit,
            sector,
            width,
            side,
            tiles,
        })
    }
    pub fn elevation(&self, x: f64, y: f64) -> Option<f64> {
        if !x.is_finite()
            || !y.is_finite()
            || x < 0.
            || y < 0.
            || x >= self.width as f64
            || y >= self.width as f64
        {
            return None;
        }
        let sx = (x / self.sector as f64) as usize;
        let sy = (y / self.sector as f64) as usize;
        let tile = &self.tiles[sx * self.side + sy];
        let x = (x - sx as f64 * self.sector as f64) / self.unit as f64;
        let y = (y - sy as f64 * self.sector as f64) / self.unit as f64;
        let ix = x.floor();
        let iy = y.floor();
        let scale = (tile.size - 1) as f64 * self.unit as f64 / self.sector as f64;
        if tile.raw((ix * scale).floor() as usize, (iy * scale).floor() as usize) & 15 == 15 {
            return None;
        }
        let a = tile.vertex(ix * scale, iy * scale);
        let b = tile.vertex((ix + 1.) * scale, iy * scale);
        let c = tile.vertex(ix * scale, (iy + 1.) * scale);
        let d = tile.vertex((ix + 1.) * scale, (iy + 1.) * scale);
        let fx = x - ix;
        let fy = y - iy;
        Some(if fx + fy < 1. {
            a * (1. - fx - fy) + b * fx + c * fy
        } else {
            d * (fx + fy - 1.) + c * (1. - fx) + b * (1. - fy)
        })
    }
    pub fn profile<F: Fn(Point) -> Option<f64>>(
        &self,
        start: Point,
        end: Point,
        yards: f64,
        elevation: F,
    ) -> Vec<ProfilePoint> {
        let count = (yards / (5f64.min(self.unit as f64 * METRES_TO_YARDS / 2.)))
            .ceil()
            .max(1.) as usize;
        let at = |distance: f64| {
            let f = distance / yards;
            elevation(Point {
                x: start.x + (end.x - start.x) * f,
                y: start.y + (end.y - start.y) * f,
            })
            .map(|h| ProfilePoint {
                distance_yards: distance,
                elevation_metres: h,
            })
        };
        let coarse: Option<Vec<_>> = (0..=count)
            .map(|i| at(yards * (i as f64 / count as f64)))
            .collect();
        let Some(coarse) = coarse else {
            return vec![];
        };
        fn refine<F: Fn(f64) -> Option<ProfilePoint>>(
            a: ProfilePoint,
            b: ProfilePoint,
            depth: u8,
            at: &F,
            out: &mut Vec<ProfilePoint>,
        ) -> Option<()> {
            let mid = at((a.distance_yards + b.distance_yards) / 2.)?;
            if depth == 0
                || (mid.elevation_metres - (a.elevation_metres + b.elevation_metres) / 2.).abs()
                    <= 0.05
            {
                return Some(());
            }
            refine(a, mid, depth - 1, at, out)?;
            out.push(mid);
            refine(mid, b, depth - 1, at, out)
        }
        let mut profile = vec![coarse[0]];
        for pair in coarse.windows(2) {
            if refine(pair[0], pair[1], 3, &at, &mut profile).is_none() {
                return vec![];
            }
            profile.push(pair[1]);
        }
        profile
    }
}
