import sys
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime
import argparse

def load_and_plot(filepath, label, ax, stats, start_time, end_time):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return False

    try:
        df = pd.read_csv(filepath, delim_whitespace=True, header=None)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return False

    if df.shape[1] < 3:
        print(f"{label}: Unexpected format (less than 3 columns)")
        return False

    df['timestamp'] = pd.to_datetime(df[0] + ' ' + df[1], errors='coerce')
    df['value'] = pd.to_numeric(df[2], errors='coerce')
    df = df.dropna(subset=['timestamp', 'value'])

    if start_time and end_time:
        df = df[df['timestamp'].dt.time.between(start_time, end_time)]

    if df.empty:
        print(f"{label}: No data in selected time range")
        return False

    ax.plot(df['timestamp'], df['value'], label=label)

    min_val = df['value'].min()
    max_val = df['value'].max()
    stats.append({
        "label": label,
        "min_value": min_val,
        "max_value": max_val
    })
    print(f"{label} - Min: {min_val:.3f}, Max: {max_val:.3f}")
    return True

def parse_time(timestr):
    try:
        return datetime.strptime(timestr, "%H:%M").time()
    except Exception:
        print(f"Invalid time format: {timestr}. Use HH:MM.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Plot R Gain data for a given date.")
    parser.add_argument("date", help="Date in format YYYYMMDD")
    parser.add_argument("--start", help="Start time in HH:MM", default=None)
    parser.add_argument("--end", help="End time in HH:MM", default=None)
    parser.add_argument("--path", help="Path to directory containing data files", default=".")
    parser.add_argument("--skip", nargs="+", help="Labels to skip (e.g. RAW MAX)", default=[])
    args = parser.parse_args()

    # Normalize skip keywords
    skip_keywords = [kw.lower() for kw in args.skip]

    start_time = parse_time(args.start) if args.start else None
    end_time = parse_time(args.end) if args.end else None

    files = {
        "LOW GAIN": os.path.join(args.path, f"R_GAIN_LOW_{args.date}.csv"),
        "MED GAIN": os.path.join(args.path, f"R_GAIN_MED_{args.date}.csv"),
        "MAX GAIN": os.path.join(args.path, f"R_GAIN_MAX_{args.date}.csv"),
        "RAW":      os.path.join(args.path, f"R{args.date}.csv")
    }

    stats = []
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.set_title(f"R Gain Readings for {args.date}")
    ax.set_xlabel("Timestamp")
    ax.set_ylabel("Measurement (Column 2)")

    any_plotted = False
    for label, filepath in files.items():
        if any(skip_kw in label.lower() for skip_kw in skip_keywords):
            print(f"Skipping {label}")
            continue
        success = load_and_plot(filepath, label, ax, stats, start_time, end_time)
        any_plotted = any_plotted or success

    if any_plotted:
        ax.legend()
        ax.grid(True)
        plt.tight_layout()

        # Save plot
        plot_filename = f"r_gain_plot_{args.date}.png"
        plt.savefig(plot_filename)
        print(f"Plot saved to: {plot_filename}")
        plt.close()

        # Save stats
        stats_df = pd.DataFrame(stats)
        stats_filename = f"r_gain_stats_{args.date}.csv"
        stats_df.to_csv(stats_filename, index=False)
        print(f"Stats saved to: {stats_filename}")
    else:
        print("No data plotted.")

if __name__ == "__main__":
    main()
