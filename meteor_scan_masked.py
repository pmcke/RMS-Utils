#!/usr/bin/env python3
"""
meteor_scan.py

Scan MKV/MP4/AVI videos for brief meteor-like transients.

Features
--------
- Accepts either:
    * a directory containing videos, or
    * a ZIP archive containing videos
- Examines every frame
- If mask.bmp is present in the input folder, ignores black mask areas
- Uses temporal background subtraction and contour analysis
- Looks for short-lived bright, elongated, moving objects
- Rejects:
    * stationary stars
    * most compression noise
    * detections touching the image border
    * large whole-frame brightness changes
- Saves:
    * CSV report
    * HTML report
    * annotated candidate PNGs
    * optional short candidate clips

This is a candidate finder, not a definitive scientific classifier.
Manual review of saved candidates is still recommended.
"""

from __future__ import annotations

import argparse
import csv
import html
import math
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np


VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".mpeg", ".mpg", ".m4v"}


@dataclass
class Detection:
    video: str
    frame_number: int
    time_seconds: float
    x: int
    y: int
    width: int
    height: int
    area: float
    length: float
    aspect_ratio: float
    angle_degrees: float
    brightness: float
    score: float
    classification: str
    image_file: str = ""
    clip_file: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan videos for meteor-like transient events."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Directory containing videos, a single video, or a ZIP archive.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("meteor_scan_output"),
        help="Output directory (default: meteor_scan_output).",
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
        help="Minimum score to save as a possible candidate (default: 16).",
    )
    parser.add_argument(
        "--likely-score",
        type=float,
        default=28.0,
        help="Minimum score to classify as likely meteor (default: 28).",
    )
    parser.add_argument(
        "--max-global-change",
        type=float,
        default=0.10,
        help="Skip frames where more than this fraction changed (default: 0.10).",
    )
    parser.add_argument(
        "--save-clips",
        action="store_true",
        help="Save a short annotated clip around each candidate.",
    )
    parser.add_argument(
        "--clip-seconds",
        type=float,
        default=1.0,
        help="Seconds before and after a candidate in saved clips (default: 1.0).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search subdirectories recursively.",
    )
    parser.add_argument(
        "--keep-extracted",
        action="store_true",
        help="Keep extracted ZIP contents inside the output directory.",
    )
    return parser.parse_args()


def list_videos(path: Path, recursive: bool = False) -> list[Path]:
    if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
        return [path]

    if not path.is_dir():
        return []

    iterator: Iterable[Path]
    iterator = path.rglob("*") if recursive else path.glob("*")
    videos = [
        p for p in iterator
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    ]
    return sorted(videos)


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            member_path = (destination / member.filename).resolve()
            if destination not in member_path.parents and member_path != destination:
                raise RuntimeError(f"Unsafe path in ZIP: {member.filename}")
        zf.extractall(destination)


def odd_kernel(value: int) -> int:
    return value if value % 2 == 1 else value + 1


def calculate_orientation(contour: np.ndarray) -> tuple[float, float, float, float]:
    """
    Return:
        length, width, aspect_ratio, angle_degrees
    using cv2.minAreaRect.
    """
    (_, _), (w, h), angle = cv2.minAreaRect(contour)
    length = float(max(w, h))
    width = float(max(1e-6, min(w, h)))
    aspect = length / width

    if w < h:
        angle += 90.0

    return length, width, aspect, float(angle)


def score_detection(
    area: float,
    length: float,
    aspect: float,
    brightness: float,
    persistence_frames: int,
) -> float:
    """
    Heuristic score. Higher is more meteor-like.
    """
    area_term = min(10.0, math.log1p(max(area, 0.0)) * 2.0)
    length_term = min(12.0, length / 3.0)
    aspect_term = min(10.0, max(0.0, aspect - 1.0) * 3.0)
    brightness_term = min(10.0, brightness / 25.0)

    # Meteors are usually brief. Reward 1-4 frames, penalise long persistence.
    if persistence_frames <= 1:
        persistence_term = 4.0
    elif persistence_frames <= 4:
        persistence_term = 7.0
    elif persistence_frames <= 8:
        persistence_term = 2.0
    else:
        persistence_term = -8.0

    return area_term + length_term + aspect_term + brightness_term + persistence_term


def overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int], margin: int = 8) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b

    return not (
        ax + aw + margin < bx
        or bx + bw + margin < ax
        or ay + ah + margin < by
        or by + bh + margin < ay
    )


def annotate_frame(
    frame: np.ndarray,
    det: Detection,
    label: str,
) -> np.ndarray:
    image = frame.copy()
    x, y, w, h = det.x, det.y, det.width, det.height

    cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 255), 2)

    text = (
        f"{label}  frame={det.frame_number}  "
        f"t={det.time_seconds:.3f}s  score={det.score:.1f}"
    )
    cv2.putText(
        image,
        text,
        (10, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 0, 255),
        2,
        cv2.LINE_AA,
    )
    return image


def save_candidate_clip(
    video_path: Path,
    detection: Detection,
    output_path: Path,
    clip_seconds: float,
) -> bool:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return False

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 25.0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    start_frame = max(0, int(detection.frame_number - clip_seconds * fps))
    end_frame = min(total_frames - 1, int(detection.frame_number + clip_seconds * fps))

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    ok, frame = cap.read()
    if not ok:
        cap.release()
        return False

    height, width = frame.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    current = start_frame
    while ok and current <= end_frame:
        shown = frame.copy()

        if abs(current - detection.frame_number) <= 2:
            cv2.rectangle(
                shown,
                (detection.x, detection.y),
                (detection.x + detection.width, detection.y + detection.height),
                (0, 0, 255),
                2,
            )

        cv2.putText(
            shown,
            f"frame={current}  t={current / fps:.3f}s",
            (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        writer.write(shown)

        current += 1
        ok, frame = cap.read()

    writer.release()
    cap.release()
    return output_path.exists() and output_path.stat().st_size > 0



def load_exclusion_mask(mask_path: Path) -> Optional[np.ndarray]:
    """
    Load mask.bmp as an 8-bit binary mask.

    White pixels (255) are searched for candidates.
    Black pixels (0) are ignored.
    """
    if not mask_path.is_file():
        return None

    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise RuntimeError(f"Could not read mask file: {mask_path}")

    # Force a clean black/white mask even if the BMP contains intermediate values.
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    return mask


def scan_video(
    video_path: Path,
    image_dir: Path,
    clip_dir: Path,
    args: argparse.Namespace,
    exclusion_mask: Optional[np.ndarray] = None,
) -> tuple[list[Detection], dict[str, object]]:
    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        return [], {
            "video": video_path.name,
            "status": "unreadable",
            "frames": 0,
            "fps": 0.0,
            "duration_seconds": 0.0,
            "candidates": 0,
        }

    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not fps or fps <= 0 or fps > 1000:
        fps = 25.0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_area = max(1, width * height)

    if exclusion_mask is not None and exclusion_mask.shape != (height, width):
        cap.release()
        raise RuntimeError(
            f"mask.bmp is {exclusion_mask.shape[1]}x{exclusion_mask.shape[0]}, "
            f"but {video_path.name} is {width}x{height}. "
            "The mask must have the same dimensions as the video."
        )

    ok, first_frame = cap.read()
    if not ok:
        cap.release()
        return [], {
            "video": video_path.name,
            "status": "empty",
            "frames": 0,
            "fps": fps,
            "duration_seconds": 0.0,
            "candidates": 0,
        }

    previous_gray = cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY)
    previous_gray = cv2.GaussianBlur(previous_gray, (5, 5), 0)
    background = previous_gray.astype(np.float32)

    # Active tracks are used only to estimate persistence.
    active_tracks: list[dict[str, object]] = []
    detections: list[Detection] = []

    frame_number = 0
    processed_frames = 1
    max_contour_area = frame_area * args.max_area_fraction

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame_number += 1
        processed_frames += 1

        gray_raw = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray_raw, (5, 5), 0)

        background_u8 = cv2.convertScaleAbs(background)

        diff_prev = cv2.absdiff(gray, previous_gray)
        diff_bg = cv2.absdiff(gray, background_u8)

        # Require change relative to both previous frame and running background.
        _, mask_prev = cv2.threshold(
            diff_prev, args.threshold, 255, cv2.THRESH_BINARY
        )
        _, mask_bg = cv2.threshold(
            diff_bg, args.threshold, 255, cv2.THRESH_BINARY
        )
        mask = cv2.bitwise_and(mask_prev, mask_bg)

        # If mask.bmp is present, white pixels are searchable and black pixels
        # are excluded.  Apply it before global-change measurement, morphology,
        # contour finding, scoring, and candidate saving.
        if exclusion_mask is not None:
            mask = cv2.bitwise_and(mask, exclusion_mask)

        # Ignore frames dominated by global brightness/exposure changes.
        global_change_fraction = cv2.countNonZero(mask) / frame_area
        if global_change_fraction <= args.max_global_change:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.dilate(mask, kernel, iterations=1)

            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            frame_boxes: list[tuple[int, int, int, int]] = []

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

                length, obj_width, aspect, angle = calculate_orientation(contour)

                if length < args.min_length:
                    continue

                # Allow compact bright point-like meteors, but require stronger
                # brightness when the aspect ratio is low.
                roi_mask = mask[y:y+h, x:x+w]
                roi_diff = diff_bg[y:y+h, x:x+w]
                nonzero = roi_mask > 0
                if not np.any(nonzero):
                    continue

                brightness = float(np.mean(roi_diff[nonzero]))

                if aspect < args.min_aspect and brightness < 55:
                    continue

                box = (x, y, w, h)
                frame_boxes.append(box)

                persistence = 1
                for track in active_tracks:
                    track_box = track["box"]
                    last_frame = int(track["last_frame"])
                    if frame_number - last_frame <= 2 and overlaps(box, track_box):
                        track["box"] = box
                        track["last_frame"] = frame_number
                        track["count"] = int(track["count"]) + 1
                        persistence = int(track["count"])
                        break
                else:
                    active_tracks.append({
                        "box": box,
                        "last_frame": frame_number,
                        "count": 1,
                    })

                score = score_detection(
                    area=area,
                    length=length,
                    aspect=aspect,
                    brightness=brightness,
                    persistence_frames=persistence,
                )

                if score < args.candidate_score:
                    continue

                classification = (
                    "likely meteor"
                    if score >= args.likely_score
                    else "possible meteor"
                )

                det = Detection(
                    video=video_path.name,
                    frame_number=frame_number,
                    time_seconds=frame_number / fps,
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    area=area,
                    length=length,
                    aspect_ratio=aspect,
                    angle_degrees=angle,
                    brightness=brightness,
                    score=score,
                    classification=classification,
                )

                stem = video_path.stem
                image_name = (
                    f"{stem}_frame_{frame_number:06d}_"
                    f"score_{score:.1f}.png"
                )
                image_path = image_dir / image_name
                annotated = annotate_frame(frame, det, classification)
                cv2.imwrite(str(image_path), annotated)
                det.image_file = str(image_path.name)

                if args.save_clips:
                    clip_name = (
                        f"{stem}_frame_{frame_number:06d}_"
                        f"score_{score:.1f}.mp4"
                    )
                    clip_path = clip_dir / clip_name
                    if save_candidate_clip(
                        video_path, det, clip_path, args.clip_seconds
                    ):
                        det.clip_file = str(clip_path.name)

                detections.append(det)

            # Expire inactive tracks.
            active_tracks = [
                t for t in active_tracks
                if frame_number - int(t["last_frame"]) <= 3
            ]

        # Update background more slowly where transient pixels are present.
        cv2.accumulateWeighted(gray, background, args.background_alpha)
        previous_gray = gray

        if frame_number % 500 == 0:
            print(
                f"    {video_path.name}: "
                f"{frame_number}/{total_frames or '?'} frames, "
                f"{len(detections)} candidate(s)",
                flush=True,
            )

    cap.release()

    # Merge near-duplicate detections from adjacent frames.
    merged: list[Detection] = []
    for det in sorted(detections, key=lambda d: (d.frame_number, -d.score)):
        duplicate = False
        for existing in merged:
            if (
                det.video == existing.video
                and abs(det.frame_number - existing.frame_number) <= 3
                and overlaps(
                    (det.x, det.y, det.width, det.height),
                    (existing.x, existing.y, existing.width, existing.height),
                    margin=12,
                )
            ):
                duplicate = True
                if det.score > existing.score:
                    existing.frame_number = det.frame_number
                    existing.time_seconds = det.time_seconds
                    existing.x = det.x
                    existing.y = det.y
                    existing.width = det.width
                    existing.height = det.height
                    existing.area = det.area
                    existing.length = det.length
                    existing.aspect_ratio = det.aspect_ratio
                    existing.angle_degrees = det.angle_degrees
                    existing.brightness = det.brightness
                    existing.score = det.score
                    existing.classification = det.classification
                    existing.image_file = det.image_file
                    existing.clip_file = det.clip_file
                break

        if not duplicate:
            merged.append(det)

    summary = {
        "video": video_path.name,
        "status": "ok",
        "frames": processed_frames,
        "fps": fps,
        "duration_seconds": processed_frames / fps,
        "candidates": len(merged),
    }
    return merged, summary


def write_csv(path: Path, detections: list[Detection]) -> None:
    fields = list(Detection.__dataclass_fields__.keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for det in detections:
            writer.writerow(asdict(det))


def write_video_summary_csv(path: Path, summaries: list[dict[str, object]]) -> None:
    fields = [
        "video",
        "status",
        "frames",
        "fps",
        "duration_seconds",
        "candidates",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summaries)


def write_html_report(
    path: Path,
    detections: list[Detection],
    summaries: list[dict[str, object]],
    image_dir_name: str,
    clip_dir_name: str,
) -> None:
    likely_count = sum(d.classification == "likely meteor" for d in detections)
    possible_count = sum(d.classification == "possible meteor" for d in detections)
    ok_count = sum(s["status"] == "ok" for s in summaries)
    failed_count = len(summaries) - ok_count

    rows = []
    for det in sorted(detections, key=lambda d: (-d.score, d.video)):
        image_link = (
            f'<a href="{html.escape(image_dir_name)}/{html.escape(det.image_file)}">'
            f'<img src="{html.escape(image_dir_name)}/{html.escape(det.image_file)}" '
            f'loading="lazy" style="max-width:360px;height:auto"></a>'
            if det.image_file
            else ""
        )
        clip_link = (
            f'<a href="{html.escape(clip_dir_name)}/{html.escape(det.clip_file)}">'
            "clip</a>"
            if det.clip_file
            else ""
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(det.video)}</td>"
            f"<td>{det.frame_number}</td>"
            f"<td>{det.time_seconds:.3f}</td>"
            f"<td>{html.escape(det.classification)}</td>"
            f"<td>{det.score:.1f}</td>"
            f"<td>{det.length:.1f}</td>"
            f"<td>{det.aspect_ratio:.2f}</td>"
            f"<td>{det.brightness:.1f}</td>"
            f"<td>{image_link}</td>"
            f"<td>{clip_link}</td>"
            "</tr>"
        )

    if not rows:
        rows.append(
            '<tr><td colspan="10">No meteor candidates met the selected threshold.</td></tr>'
        )

    report = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Meteor scan report</title>
<style>
body {{
    font-family: Arial, sans-serif;
    margin: 2rem;
    line-height: 1.4;
}}
table {{
    border-collapse: collapse;
    width: 100%;
}}
th, td {{
    border: 1px solid #bbb;
    padding: 0.45rem;
    text-align: left;
    vertical-align: top;
}}
th {{
    background: #eee;
}}
.summary {{
    padding: 1rem;
    border: 1px solid #bbb;
    margin-bottom: 1.5rem;
}}
code {{
    background: #eee;
    padding: 0.1rem 0.25rem;
}}
</style>
</head>
<body>
<h1>Meteor scan report</h1>

<div class="summary">
<p><strong>Videos supplied:</strong> {len(summaries)}</p>
<p><strong>Videos scanned successfully:</strong> {ok_count}</p>
<p><strong>Unreadable or failed videos:</strong> {failed_count}</p>
<p><strong>Likely meteor candidates:</strong> {likely_count}</p>
<p><strong>Possible meteor candidates:</strong> {possible_count}</p>
<p><strong>Total saved candidates:</strong> {len(detections)}</p>
</div>

<p>
This is an automated candidate report. Bright aircraft, insects, camera noise,
cloud edges, and compression artefacts can still produce false positives.
Review the candidate images and clips before accepting an event as a meteor.
</p>

<table>
<thead>
<tr>
<th>Video</th>
<th>Frame</th>
<th>Time (s)</th>
<th>Classification</th>
<th>Score</th>
<th>Length</th>
<th>Aspect</th>
<th>Brightness</th>
<th>Image</th>
<th>Clip</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</body>
</html>
"""
    path.write_text(report, encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    output_dir = args.output.expanduser().resolve()

    if not input_path.exists():
        print(f"ERROR: Input does not exist: {input_path}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "candidate_images"
    clip_dir = output_dir / "candidate_clips"
    image_dir.mkdir(exist_ok=True)
    clip_dir.mkdir(exist_ok=True)

    temp_dir: Optional[Path] = None
    scan_root = input_path

    try:
        if input_path.is_file() and input_path.suffix.lower() == ".zip":
            if args.keep_extracted:
                extraction_dir = output_dir / "extracted_videos"
                if extraction_dir.exists():
                    shutil.rmtree(extraction_dir)
                extraction_dir.mkdir(parents=True)
            else:
                temp_dir = Path(tempfile.mkdtemp(prefix="meteor_scan_"))
                extraction_dir = temp_dir

            print(f"Extracting ZIP: {input_path}")
            safe_extract_zip(input_path, extraction_dir)
            scan_root = extraction_dir

        videos = list_videos(
            scan_root,
            recursive=True if input_path.suffix.lower() == ".zip" else args.recursive,
        )

        if not videos:
            print("ERROR: No supported video files were found.", file=sys.stderr)
            return 3

        print(f"Found {len(videos)} video(s).")
        print(f"Output directory: {output_dir}")

        # A file named mask.bmp in the input folder is optional.
        # White = search normally; black = ignore candidate pixels.
        mask_path = scan_root / "mask.bmp" if scan_root.is_dir() else scan_root.parent / "mask.bmp"
        exclusion_mask = load_exclusion_mask(mask_path)
        if exclusion_mask is not None:
            print(
                f"Using exclusion mask: {mask_path} "
                f"({exclusion_mask.shape[1]}x{exclusion_mask.shape[0]}; black areas ignored)"
            )
        else:
            print("No mask.bmp found; scanning the full frame.")

        all_detections: list[Detection] = []
        summaries: list[dict[str, object]] = []

        for index, video in enumerate(videos, start=1):
            print(f"[{index}/{len(videos)}] Scanning {video.name}", flush=True)
            detections, summary = scan_video(
                video,
                image_dir,
                clip_dir,
                args,
                exclusion_mask,
            )
            all_detections.extend(detections)
            summaries.append(summary)

            print(
                f"    status={summary['status']}, "
                f"frames={summary['frames']}, "
                f"candidates={summary['candidates']}",
                flush=True,
            )

        candidate_csv = output_dir / "meteor_candidates.csv"
        summary_csv = output_dir / "video_scan_summary.csv"
        html_report = output_dir / "meteor_report.html"

        write_csv(candidate_csv, all_detections)
        write_video_summary_csv(summary_csv, summaries)
        write_html_report(
            html_report,
            all_detections,
            summaries,
            image_dir.name,
            clip_dir.name,
        )

        likely_count = sum(
            d.classification == "likely meteor" for d in all_detections
        )
        possible_count = sum(
            d.classification == "possible meteor" for d in all_detections
        )

        print()
        print("Scan complete.")
        print(f"Videos scanned: {len(summaries)}")
        print(f"Likely meteor candidates: {likely_count}")
        print(f"Possible meteor candidates: {possible_count}")
        print(f"CSV:  {candidate_csv}")
        print(f"HTML: {html_report}")
        return 0

    finally:
        if temp_dir is not None and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
