#!/bin/bash
cd /root/qwen15b || exit 1
BASE=https://hf-mirror.com/Qwen/Qwen2.5-1.5B-Instruct/resolve/main
for f in model-00001-of-00002.safetensors model-00002-of-00002.safetensors; do
  echo "DL $f ..."
  wget -c -q --tries=0 --timeout=30 --waitretry=5 -O "$f" "$BASE/$f"
  echo "DONE $f"
done
echo ALL_SAFETENSORS_DONE
