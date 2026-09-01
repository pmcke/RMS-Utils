#!/usr/bin/env python3
"""
meteor_scan_simple.py

Scan video files for meteor-like candidates.

Each video filename is displayed as it is scanned.

When the first candidate is detected in a video, scanning of that video stops
immediately and the scanner moves on to the next video.

At the end, all candidate video filenames are displayed together.

No CSV, HTML, images, or clips are produced.

Mask priority for each video:
    1. <station>_mask.bmp
    2. mask.bmp
    3. no mask

Black areas of a mask are ignored.
"""

from __future__ import annotations

import argparse
import math
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np


VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".mpeg", ".mpg", ".m4v"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print the filename of each video containing a meteor-like candidate."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Directory containing videos, a single video, or a ZIP archive.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=22,
        help="Minimum grayscale frame-difference threshold (default: 22).",
    )
    parser.add_argument(
        "--min-area",
        type=float,
        default=5.0,
        help="Minimum contour area in pixels (default: 5).",
    )
    parser.add_argument(
        "--max-area-fraction",
        type=float,
        default=0.015,
        help="Reject contours larger than this fraction of the frame (default: 0.015).",
    )
    parser.add_argument(
        "--min-length",
        type=float,
        default=4.0,
        help="Minimum fitted object length in pixels (default: 4).",
    )
    parser.add_argument(
        "--min-aspect",
        type=float,
        default=1.4,
        help="Minimum aspect ratio for a streak-like detection (default: 1.4).",
    )
    parser.add_argument(
        "--border",
        type=int,
        default=8,
        help="Ignore detections within this many pixels of an image edge (default: 8).",
    )
    parser.add_argument(
        "--background-alpha",
        type=float,
        default=0.03,
        help="Running-background update rate, 0 to 1 (default: 0.03).",
    )
    parser.add_argument(
        "--candidate-score",
        type=float,
        default=16.0,
        help="Minimum score to count as a candidate (default: 16).",
    )
    parser.add_argument(
        "--max-global-change",
        type=float,
        default=0.10,
        help="Skip frames where more than this fraction changed (default: 0.10).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search subdirectories recursively.",
    )
    return parser.parse_args()


def list_videos(path: Path, recursive: bool = False) -> list[Path]:
    if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
        return [path]

    if not path.is_dir():
        return []

    iterator: Iterable[Path]
    iterator = path.rglob("*") if recursive else path.glob("*")

    return sorted(
        p for p in iterator
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    )


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    destination = destination.resolve()

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            member_path = (destination / member.filename).resolve()
            if destination not in member_path.parents and member_path != destination:
                raise RuntimeError(f"Unsafe path in ZIP: {member.filename}")

        zf.extractall(destination)


def calculate_orientation(contour: np.ndarray) -> tuple[float, float]:
    (_, _), (w, h), _ = cv2.minAreaRect(contour)

    length = float(max(w, h))
    width = float(max(1e-6, min(w, h)))
    aspect = length / width

    return length, aspect


def score_detection(
    area: float,
    length: float,
    aspect: float,
    brightness: float,
    persistence_frames: int,
) -> float:
    area_term = min(10.0, math.log1p(max(area, 0.0)) * 2.0)
    length_term = min(12.0, length / 3.0)
    aspect_term = min(10.0, max(0.0, aspect - 1.0) * 3.0)
    brightness_term = min(10.0, brightness / 25.0)

    if persistence_frames <= 1:
        persistence_term = 4.0
    elif persistence_frames <= 4:
        persistence_term = 7.0
    elif persistence_frames <= 8:
        persistence_term = 2.0
    else:
        persistence_term = -8.0

    return (
        area_term
        + length_term
        + aspect_term
        + brightness_term
        + persistence_term
    )


def overlaps(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
    margin: int = 8,
) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b

    return not (
        ax + aw + margin < bx
        or bx + bw + margin < ax
        or ay + ah + margin < by
        or by + bh + margin < ay
    )


def load_exclusion_mask(mask_path: Path) -> Optional[np.ndarray]:
    if not mask_path.is_file():
        return None

    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)

    if mask is None:
        raise RuntimeError(f"Could not read mask file: {mask_path}")

    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    return mask


def choose_mask(video_path: Path) -> Optional[np.ndarray]:
    station = video_path.name[:6]

    station_mask_path = video_path.parent / f"{station}_mask.bmp"
    fallback_mask_path = video_path.parent / "mask.bmp"

    if station_mask_path.is_file():
        return load_exclusion_mask(station_mask_path)

    if fallback_mask_path.is_file():
        return load_exclusion_mask(fallback_mask_path)

    return None


def video_has_candidate(
    video_path: Path,
    args: argparse.Namespace,
    exclusion_mask: Optional[np.ndarray] = None,
) -> bool:
    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        print(f"WARNING: Could not open {video_path}", file=sys.stderr)
        return False

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_area = max(1, width * height)

    if exclusion_mask is not None and exclusion_mask.shape != (height, width):
        cap.release()
        raise RuntimeError(
            f"Selected mask is {exclusion_mask.shape[1]}x{exclusion_mask.shape[0]}, "
            f"but {video_path.name} is {width}x{height}. "
            "The mask must have the same dimensions as the video."
        )

    ok, first_frame = cap.read()

    if not ok:
        cap.release()
        return False

    previous_gray = cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY)
    previous_gray = cv2.GaussianBlur(previous_gray, (5, 5), 0)
    background = previous_gray.astype(np.float32)

    active_tracks: list[dict[str, object]] = []
    frame_number = 0
    max_contour_area = frame_area * args.max_area_fraction

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    while True:
        ok, frame = cap.read()

        if not ok:
            break

        frame_number += 1

        gray_raw = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray_raw, (5, 5), 0)

        background_u8 = cv2.convertScaleAbs(background)

        diff_prev = cv2.absdiff(gray, previous_gray)
        diff_bg = cv2.absdiff(gray, background_u8)

        _, mask_prev = cv2.threshold(
            diff_prev, args.threshold, 255, cv2.THRESH_BINARY
        )
        _, mask_bg = cv2.threshold(
            diff_bg, args.threshold, 255, cv2.THRESH_BINARY
        )

        mask = cv2.bitwise_and(mask_prev, mask_bg)

        if exclusion_mask is not None:
            mask = cv2.bitwise_and(mask, exclusion_mask)

        global_change_fraction = cv2.countNonZero(mask) / frame_area

        if global_change_fraction <= args.max_global_change:
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.dilate(mask, kernel, iterations=1)

            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in contours:
                area = float(cv2.contourArea(contour))

                if area < args.min_area or area > max_contour_area:
                    continue

                x, y, w, h = cv2.boundingRect(contour)

                if (
                    x <= args.border
                    or y <= args.border
                    or x + w >= width - args.border
                    or y + h >= height - args.border
                ):
                    continue

                length, aspect = calculate_orientation(contour)

                if length < args.min_length:
                    continue

                roi_mask = mask[y:y+h, x:x+w]
                roi_diff = diff_bg[y:y+h, x:x+w]
                nonzero = roi_mask > 0

                if not np.any(nonzero):
                    continue

                brightness = float(np.mean(roi_diff[nonzero]))

                if aspect < args.min_aspect and brightness < 55:
                    continue

                box = (x, y, w, h)
                persistence = 1
                matched_track = False

                for track in active_tracks:
                    track_box = track["box"]
                    last_frame = int(track["last_frame"])

                    if (
                        frame_number - last_frame <= 2
                        and overlaps(box, track_box)
                    ):
                        track["box"] = box
                        track["last_frame"] = frame_number
                        track["count"] = int(track["count"]) + 1
                        persistence = int(track["count"])
                        matched_track = True
                        break

                if not matched_track:
                    active_tracks.append(
                        {
                            "box": box,
                            "last_frame": frame_number,
                            "count": 1,
                        }
                    )

                score = score_detection(
                    area=area,
                    length=length,
                    aspect=aspect,
                    brightness=brightness,
                    persistence_frames=persistence,
                )

                if score >= args.candidate_score:
                    cap.release()
                    return True

            active_tracks = [
                track
                for track in active_tracks
                if frame_number - int(track["last_frame"]) <= 3
            ]

        cv2.accumulateWeighted(gray, background, args.background_alpha)
        previous_gray = gray

    cap.release()
    return False


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser().resolve()

    if not input_path.exists():
        print(f"ERROR: Input does not exist: {input_path}", file=sys.stderr)
        return 2

    temp_dir: Optional[Path] = None
    scan_root = input_path

    try:
        if input_path.is_file() and input_path.suffix.lower() == ".zip":
            temp_dir = Path(tempfile.mkdtemp(prefix="meteor_scan_"))
            safe_extract_zip(input_path, temp_dir)
            scan_root = temp_dir

        videos = list_videos(
            scan_root,
            recursive=True
            if input_path.is_file() and input_path.suffix.lower() == ".zip"
            else args.recursive,
        )

        if not videos:
            print("ERROR: No supported video files were found.", file=sys.stderr)
            return 3

        candidates: list[str] = []

        print(f"Found {len(videos)} video(s).")
        print()

        for index, video in enumerate(videos, start=1):
            print(
                f"[{index}/{len(videos)}] Scanning {video.name}",
                flush=True,
            )

            try:
                exclusion_mask = choose_mask(video)

                if video_has_candidate(video, args, exclusion_mask):
                    candidates.append(video.name)

            except Exception as exc:
                print(
                    f"WARNING: {video.name}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

        print()
        print("=" * 60)
        print("CANDIDATE FILES")
        print("=" * 60)

        if candidates:
            for filename in candidates:
                print(filename)
        else:
            print("No candidates detected.")

        print()
        print(f"Videos scanned: {len(videos)}")
        print(f"Candidate files: {len(candidates)}")

        return 0

    finally:
        if temp_dir is not None and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
