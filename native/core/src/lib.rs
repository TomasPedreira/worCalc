pub mod empirical;
pub mod engine;
pub mod physics;
pub mod terrain;
pub use engine::{AssetStore, Engine};
pub type Result<T> = std::result::Result<T, String>;
pub const METRES_TO_YARDS: f64 = 1.0936132983377078;
