"""Build data/routes.csv and data/stops.csv from OC Transpo's published GTFS
Schedule feed (TR4; WBS 1.7.1).

    python -m trfd.gtfs                          # download the current feed
    python -m trfd.gtfs path/to/GTFSExport.zip   # use a file already downloaded

Every route is kept: the bus routes and O-Train Lines 1, 2 and 4. Every
station is kept, with its coordinates for the map and, when exactly one train
line serves it, that line (so "stuck at Pimisi" counts against Line 1).
Individual bus stops, about 5,800 street corners such as "BANK / SOMERSET",
are left out: riders rarely name them, and matching them would tag posts to
the wrong place. Aliases already in the CSV files are kept, so hand-written
colloquial names survive when the files are rebuilt from a newer feed.
"""
import argparse
import csv
import io
import shutil
import tempfile
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

FEED_URL = ("https://oct-gtfs-emasagcnfmcgeham.z01.azurefd.net/public-access/"
            "GTFSExport.zip")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAIL_TYPES = {"0", "1", "2"}  # GTFS route_type: light rail, subway, rail
ROUTE_FIELDS = ("route_id", "name", "aliases", "description", "mode")
STOP_FIELDS = ("stop_name", "route_id", "aliases", "lat", "lon", "lines")

LINE_ALIASES = {
    "1": ["Line 1", "O-Train Line 1", "Confederation Line", "LRT"],
    "2": ["Line 2", "O-Train Line 2", "Trillium Line", "Trillium"],
    "4": ["Line 4", "O-Train Line 4", "Airport Line", "Airport Link"],
}
# Station names that rarely mean anything else, so they match on their own.
# Others (Baseline, Airport, Queensway, Trim, ...) need "station" after them.
DISTINCTIVE = {"Tunney's Pasture", "Pimisi", "Hurdman", "Cyrville", "Bayview",
               "Corso Italia", "Lincoln Fields", "Billings Bridge", "Barrhaven Centre",
               "Place d'Orléans", "Mackenzie King"}
SPECIAL_NAMES = {"UOTTAWA": "uOttawa", "PLACE D'ORLEANS": "Place d'Orléans"}


def display_name(gtfs_name):
    """'TUNNEY'S PASTURE' -> "Tunney's Pasture"; 'PARLIAMENT ~ PARLEMENT' -> 'Parliament'."""
    english = gtfs_name.split("~")[0].strip()
    if english.upper() in SPECIAL_NAMES:
        return SPECIAL_NAMES[english.upper()]

    def cap(part):
        if part.startswith("d'") and len(part) > 2:
            return "d'" + part[2].upper() + part[3:]
        return part[:1].upper() + part[1:]

    return " ".join("-".join(cap(p) for p in word.split("-"))
                    for word in english.lower().split())


def _unique(items):
    seen, out = set(), []
    for item in (i.strip() for i in items):
        if item and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out


def _variants(name):
    """Spellings riders use: without accents or apostrophes, spaces for hyphens,
    and St / St. / Saint."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", name)
                    if not unicodedata.combining(c))
    out = [name, plain]
    out += [v.replace("'", "") for v in out if "'" in v]
    out += [v.replace("-", " ") for v in out if "-" in v]
    for v in list(out):
        if v[:3] in ("St-", "St "):
            out += [f"St. {v[3:]}", f"Saint-{v[3:]}", f"Saint {v[3:]}"]
    return _unique(out)


def station_aliases(name, french=None, rail=False, curated=()):
    aliases = list(curated)
    for v in _variants(name):
        aliases.append(f"{v} station")
        if rail:
            aliases.append(f"{v} O-Train")
    for v in _variants(french) if french else []:
        aliases += [f"{v} station", f"station {v}"]
    if name in DISTINCTIVE:
        aliases += _variants(name)
    return _unique(aliases)


def _route_key(route_id):
    return (0, int(route_id), "") if route_id.isdigit() else (1, 0, route_id)


def _rows(z, name):
    return csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig"))


def _curated(path, key):
    """Aliases already in a CSV file, keyed by route_id or lower-case stop name."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        return {(r[key].lower() if key == "stop_name" else r[key]):
                [a for a in (r.get("aliases") or "").split("|") if a.strip()]
                for r in csv.DictReader(f)}


def route_rows(z, curated):
    rows = []
    for r in _rows(z, "routes.txt"):
        short, rail = r["route_short_name"].strip(), r["route_type"] in RAIL_TYPES
        aliases = list(curated.get(short, []))
        if rail:
            aliases += LINE_ALIASES.get(short, [f"Line {short}", f"O-Train Line {short}"])
        elif not short.isdigit():
            aliases.append(short)  # lettered routes, such as the R1 replacement bus
        rows.append({"route_id": short,
                     "name": f"O-Train Line {short}" if rail else f"Route {short}",
                     "aliases": "|".join(_unique(aliases)),
                     "description": r["route_long_name"].strip(),
                     "mode": "train" if rail else "bus"})
    return sorted(rows, key=lambda r: (r["mode"] != "train", _route_key(r["route_id"])))


def station_rows(z, curated):
    stops = list(_rows(z, "stops.txt"))
    station_of = {}  # platform or station stop_id -> station stop_id
    for s in stops:
        if s["location_type"] == "1":
            station_of[s["stop_id"]] = s["stop_id"]
        elif s["parent_station"]:
            station_of[s["stop_id"]] = s["parent_station"]
    rail_routes = {r["route_id"]: r["route_short_name"]
                   for r in _rows(z, "routes.txt") if r["route_type"] in RAIL_TYPES}
    rail_trips = {t["trip_id"]: rail_routes[t["route_id"]]
                  for t in _rows(z, "trips.txt") if t["route_id"] in rail_routes}

    # stop_times.txt is large (about 145 MB), so read it with a plain reader.
    lines = defaultdict(set)
    reader = csv.reader(io.TextIOWrapper(z.open("stop_times.txt"), encoding="utf-8-sig"))
    header = next(reader)
    trip_col, stop_col = header.index("trip_id"), header.index("stop_id")
    for row in reader:
        line = rail_trips.get(row[trip_col])
        if line and row[stop_col] in station_of:
            lines[station_of[row[stop_col]]].add(line)

    rows = []
    for s in stops:
        if s["location_type"] != "1":
            continue
        name = display_name(s["stop_name"])
        french = s["stop_name"].partition("~")[2].strip()
        served = sorted(lines[s["stop_id"]], key=_route_key)
        rows.append({
            "stop_name": name,
            "route_id": served[0] if len(served) == 1 else "",
            "aliases": "|".join(station_aliases(
                name, display_name(french) if french else None, bool(served),
                curated.get(name.lower(), []))),
            "lat": f"{float(s['stop_lat']):.5f}",
            "lon": f"{float(s['stop_lon']):.5f}",
            "lines": " ".join(served),
        })
    return sorted(rows, key=lambda r: r["stop_name"].lower())


def _write(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(zip_path, data_dir=DATA_DIR):
    data_dir = Path(data_dir)
    with zipfile.ZipFile(zip_path) as z:
        routes = route_rows(z, _curated(data_dir / "routes.csv", "route_id"))
        stations = station_rows(z, _curated(data_dir / "stops.csv", "stop_name"))
    _write(data_dir / "routes.csv", ROUTE_FIELDS, routes)
    _write(data_dir / "stops.csv", STOP_FIELDS, stations)
    return routes, stations


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rebuild routes and stations from GTFS")
    parser.add_argument("feed", nargs="?", default=FEED_URL,
                        help="GTFS zip file or URL (default: OC Transpo's public feed)")
    feed = parser.parse_args(argv).feed
    if feed.startswith(("http://", "https://")):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gtfs.zip"
            print(f"Downloading {feed} ...", flush=True)
            request = urllib.request.Request(feed, headers={"User-Agent": "trfd-gtfs-loader"})
            with urllib.request.urlopen(request, timeout=300) as response, \
                    open(path, "wb") as out:
                shutil.copyfileobj(response, out)
            routes, stations = build(path)
    else:
        routes, stations = build(Path(feed))
    trains = sum(r["mode"] == "train" for r in routes)
    print(f"Wrote {len(routes)} routes ({trains} O-Train lines) and {len(stations)}"
          f" stations to {DATA_DIR}.")


if __name__ == "__main__":
    main()
