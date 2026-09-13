#!/bin/bash
# 母体兜底：每次改 C/编译前调用，自动备份当前状态
cd /workspace
LAST=$(ls backups/ 2>/dev/null | grep -oP '^v\K\d+' | sort -n | tail -1)
NEXT=$((LAST + 1))
DIR="backups/v${NEXT}_$(date +%H%M%S)"
mkdir -p "$DIR"
cp minigpt_core.c minigpt_kv.wasm "$DIR/" 2>/dev/null
echo "✅ 母体已备份: $DIR"
