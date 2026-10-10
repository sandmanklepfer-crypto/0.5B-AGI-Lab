#!/usr/bin/env bash
# ==========================================================
#  一键把 web/ 打进 APK 并签名（复用原壳，不动 dex/manifest）
#  用法:  bash build_apk.sh
#  依赖:  zip / zipalign / apksigner / keytool
# ==========================================================
set -e
HERE=$(cd "$(dirname "$0")" && pwd)

BASE_APK="${BASE_APK:-/workspace/tianlei_base.apk}"     # 原版 APK（壳）
OUT_DIR="$HERE/build"
KEYSTORE="${KEYSTORE:-/workspace/keys/tianlei.jks}"      # 签名文件（不提交仓库）
KS_PASS="${KS_PASS:-tianlei2024}"
KS_ALIAS="${KS_ALIAS:-tianlei}"
OUT="$OUT_DIR/tianlei_online.apk"

mkdir -p "$OUT_DIR"

# 首次运行自动生成签名（仅本地使用，切勿提交）
if [ ! -f "$KEYSTORE" ]; then
  mkdir -p "$(dirname "$KEYSTORE")"
  keytool -genkeypair -keystore "$KEYSTORE" -alias "$KS_ALIAS" \
    -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass "$KS_PASS" -keypass "$KS_PASS" \
    -dname "CN=Tianlei Online,O=Tianlei,C=CN" >/dev/null 2>&1
  echo "[build] 已生成签名: $KEYSTORE"
fi

# 1) 用新的 assets/www 覆盖到 APK 副本
rm -rf /tmp/tl_repack && mkdir -p /tmp/tl_repack/assets/www
cp -r "$HERE/web/." /tmp/tl_repack/assets/www/
cp "$BASE_APK" /tmp/tl_repack/base.apk
(cd /tmp/tl_repack && zip -q -r base.apk assets)
echo "[build] assets 已替换"

# 2) 对齐 + 签名
zipalign -f -p 4 /tmp/tl_repack/base.apk "$OUT_DIR/tianlei_unsigned.apk"
apksigner sign --ks "$KEYSTORE" --ks-key-alias "$KS_ALIAS" \
  --ks-pass "pass:$KS_PASS" --key-pass "pass:$KS_PASS" \
  --out "$OUT" "$OUT_DIR/tianlei_unsigned.apk"
apksigner verify "$OUT" && echo "[build] 签名校验通过"

echo "[build] 完成 -> $OUT"
