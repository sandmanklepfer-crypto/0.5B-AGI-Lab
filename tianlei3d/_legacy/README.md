# 旧版渲染链路备份（回退用）

快照时间：2026-10-31
来源：gh-pages @ 56c925d（画质发灰黑的那一版）

## 内容
- `index.html`        130KB，含 hearth/wildlands/sky/rewards/pwa 全部增量引用
- `js/`               15 个脚本，含 arena3d.js 66KB、shooter.js 250KB
- 图标/manifest       PWA 所需

## 说明
assets / assets3d / css 未复制（36MB 重复），路径已改为 `../` 指向上级目录。

## 回退方法
```bash
cd tianlei3d
cp _legacy/index.html index.html
cp _legacy/js/*.js js/
git add -A && git commit -m "rollback" && git push origin gh-pages
```

## 访问
https://sandmanklepfer-crypto.github.io/0.5B-AGI-Lab/tianlei3d/_legacy/index.html
