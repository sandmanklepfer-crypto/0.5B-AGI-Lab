# Godot 4.6 在手机 proot 沙盒内的运行记录（2026-08-17）

## 环境
- 手机 arm64 (aarch64)，Ubuntu 24.04 proot rootfs
- 引擎：Godot_v4.6-stable_linux.arm64（官方构建，`--version` 正常）

## 结论
- ✅ 游戏模式（`--headless --path <proj>`）可正常运行：主循环 60s+、城市生成/存档/读档均正常（user:// = ~/.local/share/godot/app_userdata/新建游戏项目/）
- ❌ 编辑器模式（`--headless --import` 等）在本沙盒必崩：`double free or corruption (out)`，崩在 "Regenerating editor help cache" 之后。装 fontconfig、dejavu 字体均无效。疑似 proot 环境堆问题，真机 Linux 不受影响。游戏模式不受影响。
- ⚠️ 首次生成城市时段错误一次，读缓存路径未复现 —— 待观察

## 工具链坑
- busybox wget 的 TLS 太旧，GitHub 拒连（bad MAC / connection reset）→ 必须装 curl
- 该 rootfs 的 apt 源列表原本是空的，`apt-get update` 后才能装 curl（ubuntu.sources 配置本身是全的）
- 首次 apt install 需要 --allow-unauthenticated（busybox）

## 回汐项目问题
- character_body_3d.gd:40 `@onready var juese_node = $juese`：juese 在 player.tscn 里是 CollisionShape3D 的子节点，$juese（直接子节点）找不到。有 `if juese_node:` 保护，不致命，但模型显隐/旋转逻辑失效。修复：`$CollisionShape3D/juese` 或移动节点。
- 项目 features = "4.6"，与 4.6-stable 匹配；导出预设为 Android → 水蓝星.apk

## 天泪纪元项目档案（2026-08-17 归档）
- 项目 = 《天泪纪元0：灾变离歌》（孤儿院生存管理，玩家齐伯都，16 男孩）+《天泪纪元：学院篇》（魔法学院世界观，鹤允/竹阳）
- 工作区归档位置：/workspace/tianlei/（README.md 是索引）
- 上传目录 /upload 有 167 个文件、大量重复，去重后约 20 份实际内容
- 已知问题：力量体系.md 为空；美术.txt 实为 React 组件；纯流动化经济论与游戏无关；生存危机系统有两版
- 策划会待办：背包系统、任务系统、战斗系统第二版丢失、装备拖拽说明、角色设定先文案后策划

## M1 对话系统落地（2026-08-17）
- 新增 dialogue_data.gd（20 节点对话数据，来源=上传的策划文案）+ dialogue_manager.gd（纯代码 UI）
- 关键坑：headless 游戏模式没有全局 class_name 缓存（本沙盒编辑器崩），跨脚本引用必须 preload 常量，不能依赖 class_name
- Godot 4.6：StandardMaterial3D.specular 已改名 metallic_specular（两处修复）
- 测试入口：node_3d.gd _unhandled_input 按 E / 触屏右上角
