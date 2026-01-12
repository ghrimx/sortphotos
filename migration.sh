#!/bin/bash
set -euo pipefail

test_flag=""
copy_flag=""
sort_format=""

# Short options
while getopts ":tc" opt; do
  case "$opt" in
    t) test_flag="-t" ;;
    c) copy_flag="-c" ;;
    \?) echo "Invalid option: -$OPTARG" >&2; exit 1 ;;
  esac
done
shift $((OPTIND - 1))

# Long option --sort
if [[ "${1:-}" == "--sort" ]]; then
  [[ $# -lt 3 ]] && { echo "Error: --sort requires a format"; exit 1; }
  sort_format="$2"
  shift 2
fi

# If next arg looks like a date format, treat it as sort format
if [[ "${1:-}" == %* ]]; then
  sort_format="$1"
  shift
fi

# Now must have source and destination
if [[ $# -lt 2 ]]; then
  echo "Usage: $0 [-t] [-c] [<date_format> | --sort <date_format>] <source> <destination>"
  echo "Examples:"
  echo "  $0 /src /dest"
  echo "  $0 \"%Y/%Y_%m_%d\" /src /dest"
  echo "  $0 -t \"%Y/%m\" /src /dest"
  echo "  $0 -t -c --sort \"%Y/%d\" /src /dest"
  exit 1
fi

SOURCE_PATH=$1
DESTINATION_PATH=$2

PYTHON_SCRIPT="/home/usr2046/Github/sortphotos/src/sortphotos.py"

echo "RUN: $(date)"
echo "Test mode: ${test_flag:+true}"
echo "Copy mode: ${copy_flag:+true}"
echo "Sort format: ${sort_format:-<python default>}"
echo "Source=$SOURCE_PATH"
echo "Destination=$DESTINATION_PATH"

source_count=$(find "$SOURCE_PATH" -type f 2>/dev/null | wc -l)
echo "Files in source (to migrate): $source_count"

destination_count=$(find "$DESTINATION_PATH" -type f 2>/dev/null | wc -l)
echo "Destination file count PRIOR migration: $destination_count"

# Build python command safely
cmd=(python3 "$PYTHON_SCRIPT")
[[ -n "$test_flag" ]] && cmd+=("$test_flag")
[[ -n "$copy_flag" ]] && cmd+=("$copy_flag")
[[ -n "$sort_format" ]] && cmd+=(--sort "$sort_format")
cmd+=("$SOURCE_PATH" "$DESTINATION_PATH")

echo "Running: ${cmd[*]}"
"${cmd[@]}"

final_count=$(find "$DESTINATION_PATH" -type f 2>/dev/null | wc -l)
echo "Destination file count AFTER migration: $final_count"

declare -i delta=$final_count-$destination_count
echo "Files migrated (AFTER - PRIOR) =" $final_count-$destination_count = $delta

