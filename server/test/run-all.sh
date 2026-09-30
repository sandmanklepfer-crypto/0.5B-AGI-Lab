#!/usr/bin/env bash
# 一键跑完所有测试
#   bash test/run-all.sh
set -u
cd "$(dirname "$0")/.."

PASS=0
FAIL=0

run() {
  echo ""
  echo "════════════════════════════════════════"
  echo "  $1"
  echo "════════════════════════════════════════"
  if node "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi
}

# 1. 离线测试（不需要起服务）
run "GitHub 订单存储后端（离线）" test/store-github.test.js
run "微信回调整链路（离线，真实签名+AES）" test/notify-e2e.test.js

# 2. 冒烟测试（需起服务）
echo ""
echo "════════════════════════════════════════"
echo "  启动演示模式服务..."
echo "════════════════════════════════════════"
MOCK=1 PORT=8787 node index.js > /tmp/luhuo-test-server.log 2>&1 &
SRV=$!
for i in $(seq 1 30); do
  curl -sf http://localhost:8787/api/health >/dev/null 2>&1 && break
  sleep 0.3
done

echo ""
echo "════════════════════════════════════════"
echo "  HTTP 冒烟测试（21 项）"
echo "════════════════════════════════════════"
if node test/smoke.js; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi

kill $SRV 2>/dev/null
wait $SRV 2>/dev/null
rm -f data/orders.json

echo ""
echo "════════════════════════════════════════"
if [ $FAIL -eq 0 ]; then
  echo "  ✅ 全部通过（$PASS 个测试套件）"
else
  echo "  ❌ 有 $FAIL 个测试套件失败"
fi
echo "════════════════════════════════════════"
exit $FAIL
