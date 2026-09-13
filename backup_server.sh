#!/bin/bash
# 服务器端 GitHub 备份: 实验脚本/数据/日志/文档 (排除模型大文件)
cd /root/backup || exit 1
git pull --rebase 2>/dev/null | tail -1
mkdir -p scripts data logs docs
# 脚本
cp /root/*.py scripts/ 2>/dev/null
cp /root/autodl-tmp/*.py scripts/ 2>/dev/null
cp /root/*.c scripts/ 2>/dev/null
cp /root/autodl-tmp/minigpu/*.c scripts/ 2>/dev/null
# 数据 (jsonl/txt/npz)
cp /root/*.jsonl data/ 2>/dev/null
cp /root/probes.txt /root/probe_geom_t.npz data/ 2>/dev/null
cp /root/autodl-tmp/distill_prompts.txt data/ 2>/dev/null
cp /root/teacher_vocab.txt data/ 2>/dev/null
# 日志 (只留 <5MB)
cp /root/*.log logs/ 2>/dev/null
cp /root/autodl-tmp/*.log logs/ 2>/dev/null
find logs/ -size +5M -delete 2>/dev/null
# 文档
cp /root/CONTEXT_HANDOFF*.md docs/ 2>/dev/null
cp /root/autodl-tmp/CONTEXT_HANDOFF*.md docs/ 2>/dev/null
# 清理 git 里的大文件
find . -path ./.git -prune -o -type f -size +10M -print -delete 2>/dev/null | head -5
git add -A
git commit -m "backup $(date +%F_%H%M)" 2>&1 | tail -1
git push 2>&1 | tail -1
echo BACKUP_SERVER_DONE
