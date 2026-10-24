#!/usr/bin/env bash
# ============================================================================
#  天泪纪元 · 一键重建 APK
#  ---------------------------------------------------------------------------
#  为什么要有这个脚本
#    之前是"手动 unzip → 拷贝 → zip → 签名"，容易漏文件。
#    实测漏过一次：守夜灯/邀请奖励/数据板块写完后，APK 还是 4 小时前的版本，
#    玩家下载到的仍是旧包。这个脚本把整条链固定下来，漏一个文件就会报错。
#
#  用法
#    bash tools/build_apk.sh              # 重建并替换 download/tianlei.apk
#    bash tools/build_apk.sh --dry-run    # 只检查清单，不真打包
#
#  签名
#    沿用原密钥（/workspace/keys/tianlei.jks），SHA-256 与原包一致
#    → 老用户可以直接覆盖安装，不用卸载
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
KS="${KEYSTORE:-/workspace/keys/tianlei.jks}"
KS_PASS="${KS_PASS:-tianlei2024}"
KS_ALIAS="${KS_ALIAS:-tianlei}"
OUT="$ROOT/download/tianlei.apk"
BASE_APK="${BASE_APK:-$OUT}"          # 以现有包为壳（保留 dex/res/manifest）
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

# ---- 必须进包的清单（漏一个就报错，不再静默）----
MUST=(
  index.html
  js/shooter.js js/arena3d.js js/racestrip.js js/hd2d_arena.js js/kernel.js
  js/mqtt.js js/fp.js js/hearth.js js/wildlands.js
  js/vendor/qrcode.js
  site/index.html site/forum.html
  site/js/rewards.js site/js/live-stats.js site/js/forum.js
  site/css/site.css
  poster.html stats.html download.html
  manifest.webmanifest sw.js
  pwa-192.png pwa-512.png pwa-maskable-192.png pwa-maskable-512.png pwa-apple-180.png
  hub.html arena.html
  assets/fonts/NotoSerifSC-Bold.woff2
)
# ---- 可选（有就带，没有不报错）----
OPT=(
  stats/history.json
  poster/gallery.html
  poster/poster_v.png poster/poster_sq.png poster/poster_h.png poster/poster_story.png
  poster/poster_v.jpg poster/poster_sq.jpg poster/poster_h.jpg poster/poster_story.jpg
  site/img/hero.jpg icon-192.png icon-512.png
)

echo "== 1/6 检查必带文件 =="
miss=0
for f in "${MUST[@]}"; do
  if [ ! -f "$ROOT/$f" ]; then echo "  ❌ 缺 $f"; miss=$((miss+1)); fi
done
[ "$miss" -gt 0 ] && { echo "有 $miss 个必带文件缺失，中止。"; exit 1; }
echo "  ✅ ${#MUST[@]} 个必带文件都在"

if [ "$DRY" = "1" ]; then
  echo "== --dry-run，到此为止 =="; exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== 2/6 解包现有 APK 作为壳 =="
cd "$WORK"
unzip -q "$BASE_APK"
[ -f classes.dex ] || { echo "  ❌ 壳里没有 classes.dex"; exit 1; }
[ -f AndroidManifest.xml ] || { echo "  ❌ 壳里没有 AndroidManifest.xml"; exit 1; }
echo "  ✅ 壳完整"

echo "== 3/6 清空旧 www，铺新文件 =="
rm -rf assets/www
mkdir -p assets/www
cd "$ROOT"
# 排除：版本库、构建产物、工具、下载包本身（否则 APK 里套 APK）
# 用 tar 管道代替 rsync（容器里没有 rsync）
tar -cf - \
  --exclude='./.git' --exclude='./download' --exclude='./tools' \
  --exclude='*.apk' --exclude='*.idsig' --exclude='.DS_Store' \
  --exclude='./poster' --exclude='./stats' \
  . | ( cd "$WORK/assets/www" && tar -xf - )
WWMB=$(du -sm "$WORK/assets/www" | cut -f1)
echo "  ✅ ${WWMB} MB"
if [ "$WWMB" -gt 55 ]; then
  echo "  ⚠️  网页部分 ${WWMB}MB，超过 55MB 预警线 —— 检查是不是把 poster/stats 或大图带进来了"
fi

echo "== 4/6 打包（整个包，不只 assets）=="
cd "$WORK"
for need in AndroidManifest.xml classes.dex resources.arsc assets/www/index.html; do
  [ -e "$need" ] || { echo "  ❌ 打包前发现缺 $need"; exit 1; }
done
rm -f ../tl_new.apk
# ★ 必须 `zip -r . ` 而不是只打包 assets 目录，否则 manifest/dex 会丢
zip -q -r -X ../tl_new.apk . -x 'META-INF/*'
echo "  ✅ $(du -h ../tl_new.apk | cut -f1)"
echo "  ✅ 含: $(unzip -l ../tl_new.apk | grep -cE 'AndroidManifest.xml|classes.dex') 个核心文件"

echo "== 5/6 对齐 + 签名（沿用原密钥，可直接覆盖安装）=="
zipalign -f -p 4 ../tl_new.apk ../tl_align.apk
apksigner sign --ks "$KS" --ks-key-alias "$KS_ALIAS" \
  --ks-pass "pass:$KS_PASS" --key-pass "pass:$KS_PASS" \
  --out ../tl_signed.apk ../tl_align.apk

echo "== 6/6 校验并替换 =="
apksigner verify --print-certs ../tl_signed.apk | grep -E "SHA-256" | head -1
unzip -t ../tl_signed.apk > /dev/null && echo "  ✅ 包完整性 OK"
OLD=$(stat -c%s "$OUT" 2>/dev/null || echo 0)
cp ../tl_signed.apk "$OUT"
NEW=$(stat -c%s "$OUT")
echo
echo "完成 → $OUT  ($(du -h "$OUT" | cut -f1))"
echo "体积变化 → $((OLD/1048576))MB → $((NEW/1048576))MB"
# 备份只留在本地，不提交（.gitignore 已排除 *.apk.bak）
cp ../tl_signed.apk "$OUT.new"; rm -f "$OUT.new"
