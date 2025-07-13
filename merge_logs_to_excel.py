import argparse
import os
import re
import pandas as pd
from collections import defaultdict

# Match lines that begin with date and time: 2025/07/09 03:01:02
log_line_pattern = re.compile(r'^(\d{4}/\d{2}/\d{2})\s+(\d{2}:\d{2}:\d{2})[-\s]+(.*)$')

def parse_line(line):
    match = log_line_pattern.match(line.strip())
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None, None, None

def process_log_file(file_path):
    data = defaultdict(str)
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            date_str, time_str, message = parse_line(line)
            if date_str and time_str:
                key = f"{date_str} {time_str}"
                data[key] = message
    return data

def main():
    parser = argparse.ArgumentParser(
        description="Merge multiple log files into an Excel file, aligned by timestamp.",
        add_help=False
    )
    parser.add_argument('log_files', metavar='logfile', nargs='+', help='Path to log files')
    parser.add_argument('-o', '--output', default='merged_logs.xlsx', help='Output Excel file name')
    parser.add_argument('-?', '--help', action='help', help='Show this help message and exit')
    args = parser.parse_args()

    all_keys = set()
    logs_data = {}
    for log_path in args.log_files:
        file_key = os.path.basename(log_path)
        logs_data[file_key] = process_log_file(log_path)
        all_keys.update(logs_data[file_key].keys())

    sorted_keys = sorted(all_keys)
    records = []
    for timestamp in sorted_keys:
        date_str, time_str = timestamp.split(' ')
        row = {'Date': date_str, 'Time': time_str}
        for file_key in logs_data:
            row[file_key] = logs_data[file_key].get(timestamp, '')
        records.append(row)

    if not records:
        print("⚠️ No valid log entries found. Make sure your log lines start with 'YYYY/MM/DD HH:MM:SS'")
    else:
        df = pd.DataFrame(records)
        df.to_excel(args.output, index=False)
        print(f"✅ Excel file created: {args.output}")

if __name__ == '__main__':
    main()
