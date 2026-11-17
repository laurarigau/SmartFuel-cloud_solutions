// Geohash encoding: same algorithm (and precision 5) as scripts/seed_stations.py
const BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz";

function geohashEncode(lat, lon, precision = 5) {
  let latRange = [-90, 90];
  let lonRange = [-180, 180];
  let hash = "";
  let bits = 0;
  let ch = 0;
  let even = true;

  while (hash.length < precision) {
    const range = even ? lonRange : latRange;
    const value = even ? lon : lat;
    const mid = (range[0] + range[1]) / 2;
    if (value >= mid) {
      ch = (ch << 1) | 1;
      range[0] = mid;
    } else {
      ch = ch << 1;
      range[1] = mid;
    }
    even = !even;
    bits += 1;
    if (bits === 5) {
      hash += BASE32[ch];
      bits = 0;
      ch = 0;
    }
  }
  return hash;
}

// All precision-5 cells (~4.9 x 4.9 km) that cover a map rectangle
function geohashCellsForBounds(south, west, north, east) {
  const step = 0.04; // a bit smaller than one cell, so none is skipped
  const cells = new Set();
  for (let lat = south; lat <= north + step; lat += step) {
    for (let lon = west; lon <= east + step; lon += step) {
      cells.add(geohashEncode(Math.min(lat, north), Math.min(lon, east)));
    }
  }
  return [...cells];
}
