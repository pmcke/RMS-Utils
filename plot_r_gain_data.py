import sys
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import argparse

def load_and_plot(filepath, label, ax, stats, start_time, end_time, hide_lines):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return False

    try:
        df = pd.read_csv(filepath, delim_whitespace=True, header=None)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return False

    if df.shape[1] < 5:
        print(f"{label}: Unexpected format (less than 5 columns)")
        return False

    df['timestamp'] = pd.to_datetime(df[0] + ' ' + df[1], errors='coerce')
    df['lux'] = pd.to_numeric(df[2], errors='coerce')
    df['visible'] = pd.to_numeric(df[3], errors='coerce')
    df['infrared'] = pd.to_numeric(df[4], errors='coerce')
    df = df.dropna(subset=['timestamp', 'lux', 'visible', 'infrared'])

    if start_time and end_time:
        df = df[df['timestamp'].dt.time.between(start_time, end_time)]

    if df.empty:
        print(f"{label}: No data in selected time range")
        return False

    if 'lux' not in hide_lines:
        ax.plot(df['timestamp'], df['lux'], label=f"{label} - Lux Data")
    if 'visible' not in hide_lines:
        ax.plot(df['timestamp'], df['visible'], label=f"{label} - Visible Light")
    if 'infrared' not in hide_lines:
        ax.plot(df['timestamp'], df['infrared'], label=f"{label} - Infrared Light")

    def extract_stats(column):
        min_val = df[column].min()
        max_val = df[column].max()
        min_time = df.loc[df[column].idxmin(), 'timestamp']
        max_time = df.loc[df[column].idxmax(), 'timestamp']
        return min_val, min_time, max_val, max_time

    lux_min, lux_min_time, lux_max, lux_max_time = extract_stats('lux')
    vis_min, vis_min_time, vis_max, vis_max_time = extract_stats('visible')
    ir_min, ir_min_time, ir_max, ir_max_time = extract_stats('infrared')

    stats.append({
        "label": label,
        "lux_min": lux_min, "lux_min_time": lux_min_time,
        "lux_max": lux_max, "lux_max_time": lux_max_time,
        "visible_min": vis_min, "visible_min_time": vis_min_time,
        "visible_max": vis_max, "visible_max_time": vis_max_time,
        "infrared_min": ir_min, "infrared_min_time": ir_min_time,
        "infrared_max": ir_max, "infrared_max_time": ir_max_time
    })

    print(f"{label} - Lux: {lux_min:.2f} at {lux_min_time}, {lux_max:.2f} at {lux_max_time}")
    print(f"{label} - Visible: {vis_min} at {vis_min_time}, {vis_max} at {vis_max_time}")
    print(f"{label} - Infrared: {ir_min} at {ir_min_time}, {ir_max} at {ir_max_time}")

    return True


def parse_time(timestr):
    try:
        return datetime.strptime(timestr, "%H:%M").time()
    except Exception:
        print(f"Invalid time format: {timestr}. Use HH:MM.")
        sys.exit(1)

def clean_label(label):
    return label.replace(" ", "_").upper()

def main():
    parser = argparse.ArgumentParser(description="Plot R Gain data for a given date.")
    parser.add_argument("date", help="Date in format YYYYMMDD")
    parser.add_argument("--start", help="Start time in HH:MM", default=None)
    parser.add_argument("--end", help="End time in HH:MM", default=None)
    parser.add_argument("--input", help="Path to directory containing input data files", default=".")
    parser.add_argument("--output", help="Path to directory for output files", default=".")
    parser.add_argument("--skip", nargs="+", help="Labels to skip (e.g. RAW MAX)", default=[])
    parser.add_argument("--hide", nargs="+", help="Data lines to hide: lux, visible, infrared", default=[])

    args = parser.parse_args()

    input_dir = args.input
    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    hide_lines = [h.lower() for h in args.hide]
    skip_keywords = [kw.lower() for kw in args.skip]
    start_time = parse_time(args.start) if args.start else None
    end_time = parse_time(args.end) if args.end else None

    files = {
        "LOW GAIN": os.path.join(input_dir, f"R_GAIN_LOW_{args.date}.csv"),
        "MED GAIN": os.path.join(input_dir, f"R_GAIN_MED_{args.date}.csv"),
        "MAX GAIN": os.path.join(input_dir, f"R_GAIN_MAX_{args.date}.csv"),
        "RAW":      os.path.join(input_dir, f"R{args.date}.csv")
    }

    all_stats = []

    for label, filepath in files.items():
        if any(skip_kw in label.lower() for skip_kw in skip_keywords):
            print(f"Skipping {label}")
            continue

        stats = []
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.set_title(f"{label} Readings for {args.date}")
        ax.set_xlabel("Timestamp")
        ax.set_ylabel("Lux Data")

        success = load_and_plot(filepath, label, ax, stats, start_time, end_time, hide_lines)

        if success:
            ax.legend()
            ax.grid(True)
            plt.tight_layout()

            label_clean = clean_label(label)
            plot_filename = os.path.join(
                output_dir,
                f"r_gain_plot_{args.date}_{label_clean}.png"
            )
            plt.savefig(plot_filename)
            plt.close()
            print(f"Plot saved to: {plot_filename}")

            all_stats.extend(stats)
        else:
            print(f"No data plotted for {label}")

    if all_stats:
        stats_df = pd.DataFrame(all_stats)
        stats_filename = os.path.join(
            output_dir,
            f"r_gain_stats_{args.date}.csv"
        )
        stats_df.to_csv(stats_filename, index=False)
        print(f"Combined stats saved to: {stats_filename}")
    else:
        print("No stats collected.")

if __name__ == "__main__":
    main()
