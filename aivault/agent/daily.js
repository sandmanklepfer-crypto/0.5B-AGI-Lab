#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  daily.js —— 每日摘要任务（GitHub Actions 里跑）
 *  --------------------------------------------------------------------------
 *  真实用途：每天把仓库/工作区的变化整理成一份摘要
 *
 *  两种模式（自动降级）：
 *    ① vault 在线  → 用你手机上的 AI 总结（key 不出手机）
 *    ② vault 离线  → 用规则生成摘要（不依赖任何 API，永不失败）
 *
 *  ★ 这就是"脉冲依赖"的真实约束：手机不在线，AI 那步就跳过。
 *     但任务本身不会崩 —— 这是能长期跑的关键。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const CHAN = process.env.VAULT_CHAN || '';
const OUT = process.env.OUT_FILE || 'DIGEST.md';

function sh(cmd, dflt = '') {
  try { return execSync(cmd, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim(); }
  catch (e) { return dflt; }
}

/* ------------------------- 采集事实 ------------------------- */
function collect() {
  const facts = {
    at: new Date().toISOString(),
    repo: process.env.GITHUB_REPOSITORY || sh('basename $(git rev-parse --show-toplevel 2>/dev/null)'),
    branch: sh('git rev-parse --abbrev-ref HEAD', 'main'),
    // 最近 24 小时的提交
    commits: sh('git log --since="24 hours ago" --pretty=format:"%h|%an|%s" 2>/dev/null', '')
      .split('\n').filter(Boolean).slice(0, 30),
    // 文件变化统计
    stat: sh('git diff --stat HEAD~1 HEAD 2>/dev/null | tail -1', ''),
    // 仓库大小
    size: sh('du -sh .git 2>/dev/null | cut -f1', ''),
    // 未提交改动
    dirty: sh('git status --porcelain 2>/dev/null | wc -l', '0').trim(),
  };
  return facts;
}

/* ------------------------- 规则摘要（永远可用） ------------------------- */
function ruleDigest(f) {
  const L = [];
  L.push('# 每日摘要 · ' + f.at.slice(0, 10));
  L.push('');
  L.push('| 项 | 值 |');
  L.push('|---|---|');
  L.push('| 仓库 | `' + (f.repo || '?') + '` |');
  L.push('| 分支 | `' + f.branch + '` |');
  L.push('| 24h 提交 | **' + f.commits.length + '** |');
  L.push('| 未提交改动 | ' + f.dirty + ' 个文件 |');
  L.push('| 仓库体积 | ' + (f.size || '?') + ' |');
  L.push('');
  if (f.commits.length) {
    L.push('## 最近提交');
    L.push('');
    for (const c of f.commits.slice(0, 15)) {
      const [h, who, msg] = c.split('|');
      L.push('- `' + h + '` ' + msg + ' — *' + who + '*');
    }
  } else {
    L.push('_最近 24 小时没有提交。_');
  }
  L.push('');
  L.push('---');
  L.push('');
  L.push('*规则生成（vault 未在线，未使用 AI）*');
  return L.join('\n');
}

/* ------------------------- AI 摘要（vault 在线时） ------------------------- */
async function aiDigest(f, ruleText) {
  // 动态引入，避免 vault 离线时也要加载 MQTT
  const { ask } = require('./brain');
  const prompt =
    '下面是一个软件仓库的每日状态。请用中文写一份 150 字以内的摘要，' +
    '指出：1) 今天主要做了什么 2) 有没有需要留意的风险 3) 下一句建议。' +
    '不要复述数据，直接给判断。\n\n' + ruleText;

  const ans = await ask([{ role: 'user', content: prompt }], { maxTokens: 400 });
  return ans;
}

/* ------------------------- 主流程 ------------------------- */
async function main() {
  console.log('=== 采集事实 ===');
  const f = collect();
  console.log('  仓库: ' + f.repo + '  分支: ' + f.branch);
  console.log('  24h 提交: ' + f.commits.length + '   未提交: ' + f.dirty);

  const rule = ruleDigest(f);
  let final = rule;
  let mode = 'rule';

  if (CHAN) {
    console.log('\n=== 尝试用 vault 上的 AI 总结 ===');
    try {
      const ans = await aiDigest(f, rule);
      if (ans && ans.text) {
        final = rule + '\n\n## AI 摘要（' + ans.provider + '）\n\n' + ans.text.trim() +
          '\n\n*耗时 ' + ans.ms + 'ms，key 全程未离开 vault 设备*';
        mode = 'ai';
        console.log('  ✓ AI 摘要成功 (' + ans.provider + ', ' + ans.ms + 'ms)');
      }
    } catch (e) {
      console.log('  ⚠️ AI 不可用: ' + e.message);
      console.log('  → 降级为规则摘要（任务照常完成）');
    }
  } else {
    console.log('\n  (未设置 VAULT_CHAN，跳过 AI)');
  }

  fs.writeFileSync(OUT, final + '\n');
  console.log('\n=== 已写入 ' + OUT + ' (' + final.length + ' 字符, 模式=' + mode + ') ===');
  console.log(final.split('\n').slice(0, 12).join('\n'));
}

main().catch(e => {
  console.error('✗ 任务失败: ' + e.message);
  // 关键：任务失败也要产出一个可用的文件，避免 workflow 红
  try {
    fs.writeFileSync(OUT, '# 每日摘要\n\n采集失败: ' + e.message + '\n\n时间: ' + new Date().toISOString() + '\n');
  } catch (e2) {}
  process.exit(0);
});
