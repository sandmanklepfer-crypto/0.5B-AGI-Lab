# ★ 好版本备份（APK 渲染管线）— 画面正常的那一版

快照时间：2026-10-31 21:1x
来源：APK `com.tianlei.game` 解包 `assets/www/`

## 这份是什么
**画面正常、色彩鲜艳的那一版**（湿润沥青地面、绿色植被、紫色环境光、暖色高光）。

md5 校验（与 APK 内文件逐字节一致）：
```
index.html      115,017 字节  8b1678b5d361
js/arena3d.js    44,334 字节  d3b3f9d94e84
js/shooter.js   226,972 字节  0d325f0c746e
```

## 它和 _legacy/ 的区别
| | _baseline_apk/（好） | _legacy/（坏） |
|---|---|---|
| 画面 | 亮、有色彩 | 灰黑死沉 |
| sky.js | 无 | 有（正午蓝天配雨夜，冲突） |
| arena3d.js | 44KB / 701行 | 66KB / 1125行 |
| shooter.js | 227KB / 3683行 | 251KB / 4164行 |
| 原因 | 光线自洽 | 天空球拖帧 → Perf 降到 394×667 |

## 恢复成"好版本"（如果被改坏）
```bash
cd tianlei3d
cp _baseline_apk/index.html index.html
cp _baseline_apk/js/*.js js/
git add -A && git commit -m "restore good render" && git push origin gh-pages
```

## 完整版备份（79MB，含全部素材）
在沙箱本地：`/workspace/_backup_GOOD_APK渲染版/`
- `www/` 315 个文件完整解包
- `apk源文件/` 原始 3 个 APK
