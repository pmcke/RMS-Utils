#!/usr/bin/env python3
"""Scan locally stored RMS videos in a date/time range for meteor candidates.

Examples:
    python3 meteor_scan_local.py NZ005A 20260913_210000 20260913_220000
    python3 meteor_scan_local.py NZ005A,NZ005B 20260913_210000 20260913_220000
    python3 meteor_scan_local.py 20260913_210000 20260913_220000

When STATION is omitted, every stationID found in ~/source/Stations/*/.config is
scanned sequentially.  On a single-camera installation, ~/source/RMS/.config
and ~/RMS_data/VideoFiles are used.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


VIDEO_NAME_RE = re.compile(
    r"^(?P<station>[A-Za-z0-9]{6})_(?P<date>\d{8})_(?P<time>\d{6})(?:_|\.).*\.mkv$",
    re.IGNORECASE,
)
STATION_CONFIG_RE = re.compile(
    # RMS normally uses "stationID:".  Also accept "station_id:" for
    # compatibility with installations that use the alternative spelling.
    r"^\s*station_?id\s*:\s*['\"]?([^\s#;'\"]+)",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class StationPaths:
    station_id: str
    video_root: Path
    config_dir: Path


def parse_timestamp(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y%m%d_%H%M%S")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid date/time {value!r}; use YYYYMMDD_HHMMSS"
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recursively scan RMS MKV files within an inclusive date/time range."
    )
    parser.add_argument(
        "values", nargs="+", metavar="ARG",
        help="[STATION[,STATION...]] START END; times use YYYYMMDD_HHMMSS",
    )
    parser.add_argument("--threshold", type=int, default=22)
    parser.add_argument("--min-area", type=float, default=5.0)
    parser.add_argument("--max-area-fraction", type=float, default=0.015)
    parser.add_argument("--min-length", type=float, default=4.0)
    parser.add_argument("--min-aspect", type=float, default=1.4)
    parser.add_argument("--border", type=int, default=8)
    parser.add_argument("--background-alpha", type=float, default=0.03)
    parser.add_argument("--candidate-score", type=float, default=16.0)
    parser.add_argument("--max-global-change", type=float, default=0.10)
    args = parser.parse_args()

    if len(args.values) == 2:
        args.stations = None
        start_text, end_text = args.values
    elif len(args.values) == 3:
        args.stations = [
            station.strip().upper()
            for station in args.values[0].split(",")
            if station.strip()
        ]
        if not args.stations:
            parser.error("the station list is empty")
        if len(args.stations) != len(set(args.stations)):
            parser.error("the station list contains duplicate station IDs")
        start_text, end_text = args.values[1:]
    else:
        parser.error("supply START END, or STATION[,STATION...] START END")

    args.start = parse_timestamp(start_text)
    args.end = parse_timestamp(end_text)
    if args.end < args.start:
        parser.error("END must not be earlier than START")
    return args


def station_id_from_config(config_path: Path) -> Optional[str]:
    try:
        text = config_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = STATION_CONFIG_RE.search(text)
    return match.group(1).upper() if match else None


def discover_stations(home: Path) -> list[StationPaths]:
    stations_root = home / "source" / "Stations"
    discovered: dict[str, StationPaths] = {}

    if stations_root.is_dir():
        for config_path in sorted(stations_root.glob("*/.config")):
            station_id = station_id_from_config(config_path)
            if station_id:
                discovered[station_id] = StationPaths(
                    station_id,
                    home / "RMS_data" / station_id / "VideoFiles",
                    config_path.parent,
                )

    single_config = home / "source" / "RMS" / ".config"
    single_id = station_id_from_config(single_config)
    if single_id and single_id not in discovered:
        discovered[single_id] = StationPaths(
            single_id, home / "RMS_data" / "VideoFiles", single_config.parent
        )

    return [discovered[key] for key in sorted(discovered)]


def resolve_requested_station(home: Path, station_id: str) -> StationPaths:
    station_dir = home / "source" / "Stations" / station_id
    multi_video_root = home / "RMS_data" / station_id / "VideoFiles"
    if multi_video_root.is_dir() or station_dir.is_dir():
        return StationPaths(station_id, multi_video_root, station_dir)

    single_dir = home / "source" / "RMS"
    single_video_root = home / "RMS_data" / "VideoFiles"
    configured_id = station_id_from_config(single_dir / ".config")
    if configured_id == station_id or single_video_root.is_dir():
        return StationPaths(station_id, single_video_root, single_dir)

    return StationPaths(station_id, multi_video_root, station_dir)


def videos_in_range(station: StationPaths, start: datetime, end: datetime) -> list[Path]:
    videos: list[tuple[datetime, Path]] = []
    if not station.video_root.is_dir():
        return []
    for path in station.video_root.rglob("*.mkv"):
        match = VIDEO_NAME_RE.match(path.name)
        if not match or match.group("station").upper() != station.station_id:
            continue
        try:
            timestamp = datetime.strptime(
                match.group("date") + "_" + match.group("time"), "%Y%m%d_%H%M%S"
            )
        except ValueError:
            continue
        if start <= timestamp <= end:
            videos.append((timestamp, path))
    return [path for _, path in sorted(videos, key=lambda item: (item[0], str(item[1])))]


def find_mask(config_dir: Path, station_id: str) -> Optional[Path]:
    # Prefer the normal RMS mask.bmp name, but also accept a station-named mask.
    for name in ("mask.bmp", f"{station_id}_mask.bmp"):
        path = config_dir / name
        if path.is_file():
            return path
    return None


def load_mask(path: Optional[Path]) -> Optional[np.ndarray]:
    if path is None:
        return None
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise RuntimeError(f"could not read mask: {path}")
    return cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)[1]


def orientation(contour: np.ndarray) -> tuple[float, float]:
    (_, _), (width, height), _ = cv2.minAreaRect(contour)
    length = float(max(width, height))
    aspect = length / float(max(1e-6, min(width, height)))
    return length, aspect


def overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int], margin: int = 8) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        ax + aw + margin < bx or bx + bw + margin < ax
        or ay + ah + margin < by or by + bh + margin < ay
    )


def detection_score(area: float, length: float, aspect: float,
                    brightness: float, persistence: int) -> float:
    persistence_term = 4.0 if persistence <= 1 else 7.0 if persistence <= 4 else 2.0 if persistence <= 8 else -8.0
    return (
        min(10.0, math.log1p(max(area, 0.0)) * 2.0)
        + min(12.0, length / 3.0)
        + min(10.0, max(0.0, aspect - 1.0) * 3.0)
        + min(10.0, brightness / 25.0)
        + persistence_term
    )


def contains_candidate(video_path: Path, args: argparse.Namespace,
                       exclusion_mask: Optional[np.ndarray]) -> tuple[bool, str]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return False, "unreadable"

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_area = max(1, width * height)
    if exclusion_mask is not None and exclusion_mask.shape != (height, width):
        cap.release()
        return False, f"mask is {exclusion_mask.shape[1]}x{exclusion_mask.shape[0]}, video is {width}x{height}"

    ok, frame = cap.read()
    if not ok:
        cap.release()
        return False, "empty"
    previous = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    background = previous.astype(np.float32)
    active_tracks: list[dict[str, object]] = []
    frame_number = 0
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_number += 1
        gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        diff_previous = cv2.absdiff(gray, previous)
        diff_background = cv2.absdiff(gray, cv2.convertScaleAbs(background))
        changed_previous = cv2.threshold(diff_previous, args.threshold, 255, cv2.THRESH_BINARY)[1]
        changed_background = cv2.threshold(diff_background, args.threshold, 255, cv2.THRESH_BINARY)[1]
        changed = cv2.bitwise_and(changed_previous, changed_background)
        if exclusion_mask is not None:
            changed = cv2.bitwise_and(changed, exclusion_mask)

        if cv2.countNonZero(changed) / frame_area <= args.max_global_change:
            changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, kernel)
            changed = cv2.dilate(changed, kernel, iterations=1)
            contours, _ = cv2.findContours(changed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                area = float(cv2.contourArea(contour))
                if area < args.min_area or area > frame_area * args.max_area_fraction:
                    continue
                x, y, w, h = cv2.boundingRect(contour)
                if x <= args.border or y <= args.border or x + w >= width - args.border or y + h >= height - args.border:
                    continue
                length, aspect = orientation(contour)
                if length < args.min_length:
                    continue
                roi_changed = changed[y:y + h, x:x + w] > 0
                if not np.any(roi_changed):
                    continue
                brightness = float(np.mean(diff_background[y:y + h, x:x + w][roi_changed]))
                if aspect < args.min_aspect and brightness < 55:
                    continue
                box = (x, y, w, h)
                persistence = 1
                for track in active_tracks:
                    if frame_number - int(track["last_frame"]) <= 2 and overlaps(box, track["box"]):
                        track.update(box=box, last_frame=frame_number, count=int(track["count"]) + 1)
                        persistence = int(track["count"])
                        break
                else:
                    active_tracks.append({"box": box, "last_frame": frame_number, "count": 1})
                if detection_score(area, length, aspect, brightness, persistence) >= args.candidate_score:
                    cap.release()
                    return True, "candidate"
            active_tracks = [t for t in active_tracks if frame_number - int(t["last_frame"]) <= 3]

        cv2.accumulateWeighted(gray, background, args.background_alpha)
        previous = gray

    cap.release()
    return False, "ok"


def create_candidate_archive(candidates: list[Path], start: datetime,
                             output_dir: Path) -> Path:
    archive_path = output_dir / f"candidates_{start.strftime('%Y%m%d_%H%M%S')}.zip"
    # MKV video is already compressed, so storing it without recompression is
    # substantially faster and normally produces nearly the same size.
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for video in candidates:
            archive.write(video, arcname=video.name)
    return archive_path


def main() -> int:
    args = parse_args()
    home = Path.home()
    if args.stations:
        stations = [
            resolve_requested_station(home, station_id)
            for station_id in args.stations
        ]
    else:
        stations = discover_stations(home)
        if not stations:
            print("ERROR: No stationID entry found in ~/source/Stations/*/.config or ~/source/RMS/.config", file=sys.stderr)
            return 2

    all_candidates: list[Path] = []
    errors = 0
    for station_index, station in enumerate(stations, start=1):
        print(f"\nStation {station.station_id} [{station_index}/{len(stations)}]")
        print(f"Video path: {station.video_root}")
        if not station.video_root.is_dir():
            print("  WARNING: Video path does not exist; skipping.")
            errors += 1
            continue

        mask_path = find_mask(station.config_dir, station.station_id)
        try:
            mask = load_mask(mask_path)
        except RuntimeError as exc:
            print(f"  ERROR: {exc}; skipping station.", file=sys.stderr)
            errors += 1
            continue
        print(f"Mask: {mask_path if mask_path else 'none (full frame)'}")
        videos = videos_in_range(station, args.start, args.end)
        print(f"Found {len(videos)} video(s) in range.")

        for index, video in enumerate(videos, start=1):
            print(f"[{index}/{len(videos)}] Scanning {video.name}", flush=True)
            candidate, status = contains_candidate(video, args, mask)
            if candidate:
                all_candidates.append(video)
            elif status != "ok":
                print(f"    WARNING: {status}", file=sys.stderr)
                errors += 1

    print("\n" + "=" * 60)
    print("CANDIDATE FILES")
    print("=" * 60)
    if all_candidates:
        for video in all_candidates:
            print(video)
    else:
        print("No candidate files found.")
    print(f"\nCandidate files: {len(all_candidates)}")

    try:
        archive_path = create_candidate_archive(all_candidates, args.start, Path.cwd())
        print(f"Archive: {archive_path}")
    except OSError as exc:
        print(f"ERROR: Could not create candidate archive: {exc}", file=sys.stderr)
        errors += 1

    if errors:
        print(f"Warnings/errors: {errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
