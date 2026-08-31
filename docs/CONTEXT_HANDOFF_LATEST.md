# 交接 (2026-08-25 01:3x) — 本会话状态,新对话先读这个

## 视频生成闭环 (2026-08-25 已提取, 一键复跑)
- `bash /workspace/video_loop.sh` — Godot渲染 → ffmpeg合成 → ComfyUI Wan2.1 视频模型 → 增强输出
- 全链路记录: `/workspace/VIDEO_PIPELINE.md` (04:50 已跑通一轮: fox_run.mp4 → fox_enhanced.mp4)
- ComfyUI 不在跑时脚本自动拉起; 磁盘<1.5G 拒绝执行

## 一句话
3B 模型已修复 + 视频模型三件套下载完成 + ComfyUI 搭建进行中(卡在依赖 patch)。

## 1. 3B 自进化主线 (✅ 模型已修好,可直接推进)
- 根因:旧 3B 文件**内容损坏**(大小一致但 sha256 不匹配)→ 推理乱码、dump 全零
- 已重新下载: `/workspace/qwen2.5-coder-3b-instruct-q4_k_m.gguf` (2.1G)
- **sha256 = 724fb256bec1ff062b2f65e4569e871ad2e95ab2a3989723d1769c54294730b7 ✅ 匹配官方**
- 生成测试正常(之前乱码已消失)
- **工具**: `dump_layers4_v3` (动态宽度版,已编译,在 /workspace/) — 用它重跑 3B dump
- 流程: dump → layer_sep.py 找层 → make_svd_3b.py 流形 → lda_direction.py 方向 → make_control_vector.py → 注入
- ⏭️ 下一步: `./dump_layers4_v3 qwen2.5-coder-3b-instruct-q4_k_m.gguf /tmp/code3b_pos.txt /tmp/c3b_pos` (+neg)

## 2. 视频模型 (✅ 三件套已下载,ComfyUI 搭建中)
- 目录: `/workspace/models/wan/`
  - `diffusion_pytorch_model.safetensors` 5.68G (Wan2.1-T2V-1.3B, sha256=96b6b242... ✅)
  - `umt5-xxl-encoder-Q3_K_M.gguf` 3.05G (city96)
  - `Wan2.1_VAE.pth` 507M
- **ComfyUI** 在 `/workspace/ComfyUI` (master zip 方式装的), WanVideoWrapper 已放 custom_nodes/
- **模型软链接已配好**: models/diffusion_models, text_encoders, vae
- **依赖状态**: torch 2.13.0+cpu (清华源) ✅, transformers 5.15 ✅, einops ✅
- ⚠️ **坑 (别重复踩)**:
  - 清华源 torch 2.13.0+cpu 与官方 torchvision 0.27/0.28 **ABI 不匹配** (torchvision::nms does not exist)
  - 对策: 已 patch ComfyUI 8 处 torchvision import + 6 处 torchaudio import 为 try/except
  - torchaudio 已卸载 (它是 CUDA 版, 加载要 libcudart)
  - ⏭️ **当前卡点**: `comfy/ldm/ace/vae/music_dcae_pipeline.py` 第 6-8 行 try 缩进坏了 (patch 导致 IndentationError), 手修成:
    ```
    try:
        import torchaudio
    except Exception:
        torchaudio = None
    ```
    然后 `python3 main.py --cpu --port 8188` 启动验证 (API: /system_stats)
- ⏭️ 跑通后: 用 WanVideoWrapper 的 T2V workflow (prompt → umt5 GGUF → 1.3B DiT → VAE → 视频)

## 3. Bootloader 逆向 (挂起,不删)
- 发现全在 `/workspace/BOOTLOCKER_PROGRESS.md` (TCSR/LCS 机制已明,fastboot 命令字符串已找到)
- fastboot 代码在 abl.elf → FV → LZMA → 代码区 0x10000-0x4b000, 字符串区 0x87000+
- 实机: device_state=locked, oem_unlock_allowed=1 (官方路前置已满足)

## 4. 待办队列 (按序)
1. 修 music_dcae_pipeline.py 缩进 → ComfyUI 启动 → 测 Wan 视频生成
2. 3B 自进化: dump_layers4_v3 重跑 dump → 方向提取 → 注入 (方法全现成)
3. **llama.cpp 更新编译** (支持 gemma4/qwen3_5/qwen3_5_moe 新架构, 当前 b1-1719747 太老) — 所有 2026 新模型的前提
4. 下载 Gemma-4-12B agentic (Q4 ~7G) — 手机 agent 底座 (用户已倾向)
5. 备选: Qwen3.6-35B-A3B Q3 (13G, 内存极限) / Qwen3.5-9B

## 5. 用户偏好 (重要)
- **清理/删除必须确认**; 0.5B 成果模型群 (qwen_code/v2/unlocked/evolved) **不许删**
- 要成果不要过程; 边做边对照实机; 安全第一 (备份)
- 讨厌纯静态堆分析, 要"边做边背"
- 感兴趣: 手机端"世界模型/视频模型"、流形方法压缩+纠偏、agent 融合 (方向迁移)

## 6. 环境现状
- 磁盘: ~4.5G 可用 (已删 onyx_firmware.tgz 10G, ghidra 1.4G, MiniGPT zip)
- 固件镜像保留在 fw_extract/images/ (13 个, bootloader 逆向需要)
- adb 保活: bg_14 在跑 (adb_keepalive.sh)
- 网络: github 不稳 (用镜像/重试), hf-mirror 稳定 10-20MB/s, pypi 用清华源
- 3B 修复后旧 corrupt 文件已删
