#!/usr/bin/env bash
# Run BEFORE making the repo public: scans every blob in the full git history
# for media/data/model files outside docs/synthetic/ and for files over 2 MB.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

MAX_BYTES=$((2 * 1024 * 1024))
MEDIA_RE='\.(mp4|mov|avi|mkv|webm|m4v|mpg|mpeg|jpg|jpeg|png|gif|bmp|tif|tiff|webp)$'
DATA_RE='\.(npy|npz|pkl|pickle|jsonl|parquet|h5|hdf5|task|pth|pt|ckpt|onnx|tflite|safetensors)$'

found=0
while read -r sha type size path; do
  [[ "$type" == "blob" ]] || continue
  lower=$(printf '%s' "$path" | tr '[:upper:]' '[:lower:]')
  if { [[ "$lower" =~ $MEDIA_RE ]] && [[ "$path" != docs/synthetic/* ]]; } || [[ "$lower" =~ $DATA_RE ]]; then
    echo "HISTORY HAS: $path ($size bytes, blob $sha)"; found=1
  elif (( size > MAX_BYTES )); then
    echo "HISTORY HAS LARGE FILE: $path ($size bytes, blob $sha)"; found=1
  fi
done < <(git rev-list --objects --all \
          | git cat-file --batch-check='%(objectname) %(objecttype) %(objectsize) %(rest)')

if (( found )); then
  echo; echo "NOT safe to publish. Rewrite history (e.g. git filter-repo) before making the repo public."
  exit 1
fi
echo "History clean: no media/data/model files and nothing over 2 MB."
