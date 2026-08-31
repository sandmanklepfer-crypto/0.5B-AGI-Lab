# ERRORS

## [ERR-20260822-001] opencl_probe_dlopen

**Logged**: 2026-08-22T03:35:00Z
**Priority**: high
**Status**: pending
**Area**: infra

### Summary
容器静态 glibc 二进制无法 dlopen 手机 Android 的 /vendor/lib64/libOpenCL.so（依赖 liblog.so 解析失败，SELinux 未测到就挂在链接器层）

### Error
`FAIL dlopen: liblog.so: cannot open shared object file`（即使手动 preload liblog/libcutils/libc++）

### Context
- 目标: shell 权限下用 Adreno 825 GPU 的 OpenCL
- 硬件已确认: Qualcomm Adreno 825, /dev/kgsl-3d0 存在, libOpenCL.so 存在
- 环境: 容器 aarch64 Debian(glibc), 手机 bionic libc
- 已试: 静态 glibc + dlopen、LD_LIBRARY_PATH、手动 preload

### Suggested Fix
- 用 bionic 环境: Termux (app 上下文有 GPU SELinux 权限 + bionic linker) 或 Android NDK 交叉编译
- 或检查 SELinux: shell domain 是否允许访问 kgsl (可能还需 allow 规则, 大概率被挡)

### Metadata
- Reproducible: yes
- Related Files: /workspace/opencl_probe.c
---

## [ERR-20260822-002] vulkan_getPhysicalDeviceProperties_hang

**Logged**: 2026-08-22T03:50:00Z
**Priority**: medium
**Status**: in_progress
**Area**: infra

### Summary
Termux(uid 10479, untrusted_app) 里 Vulkan vkCreateInstance/vkEnumeratePhysicalDevices 成功(GPU=1)，但 vkGetPhysicalDeviceProperties 挂起(超时无返回)

### Context
- 设备: SM8735 Adreno 825, Android 15
- 通道: Termux SSH (bionic + app domain)
- OpenCL 被 linker namespace 挡(default ns 拒 /vendor/lib64/libOpenCL.so 的 dlopen, 虽在 public.libraries.txt)
- Vulkan: libvulkan.so 可加载, instance OK, device 枚举 OK, properties 查询挂

### Suggested Fix
- 尝试完整 compute pipeline 直接跑矩阵乘(绕开 properties 查询, 用 QueueFamily 扩展函数)
- 或用 app_process/完整 Activity 环境验证(非 ssh 会话)
- 备用: NNAPI(/apex 里的 libneuralnetworks, app 可用) 走 HAL 加速推理

### Metadata
- Reproducible: yes
- Related Files: /workspace/vulkan_probe2.py
---

## [ERR-20260822-003] NNAPI_ctypes_model_BAD_DATA

**Logged**: 2026-08-22T04:10:00Z
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
Termux 里 python ctypes 构建 NNAPI 模型(ADD/FC) 一直 BAD_DATA(4)，addOperand 成功但 addOperation 失败；NNAPI 设备枚举正常(getDeviceCount=1)

### Context
- 设备: SM8735, Android 15, /apex/com.android.neuralnetworks/lib64/libneuralnetworks.so
- 已试: ADD(2in/3in), FC(带activation operand), 各种维度
- onnxruntime 无 aarch64 Android wheel(pypi/清华源都没有)

### Suggested Fix
- 用 onnxruntime-android 的 release aar 提取 .so 用
- 或用完整 app(带窗口/Activity) 调 NNAPI
- 或 MNN/NCNN 的 NNAPI 后端(Termux pkg install mnn?)

### Metadata
- Reproducible: yes
- Related Files: /workspace/nn_bench.py
---

## [ERR-20260822-004] EGL_display_no_window_ssh

**Logged**: 2026-08-22T04:40:00Z
**Priority**: high
**Status**: in_progress
**Area**: infra

### Summary
Termux ssh 会话(无窗口 app 进程)里 eglInitialize 失败 EGL_BAD_DISPLAY(0x3008)，Vulkan 查询挂起同理——无窗口环境连不上 SurfaceFlinger 显示服务

### Context
- gles_bench.py: eglGetDisplay(EGL_DEFAULT_DISPLAY) 成功但 eglInitialize 返回 0x3008
- 结论: 命令行(ssh)下 EGL/Vulkan 全堵死, 只有 Godot headless 的 local RenderingDevice 独立于 display 可用

### Suggested Fix
- Godot headless (Termux pkg godot 安装中): --headless --path 跑 local RD compute
- 或完整 Activity app(带窗口) 调 GLES/Vulkan

### Metadata
- Reproducible: yes
- Related Files: /workspace/gles_bench.py
---

## [ERR-20260824-001] proot_curl_slow
**Logged**: 2026-08-24T15:15:00+08
**Priority**: medium
**Status**: in_progress
**Area**: infra

### Summary
proot 环境里 curl 下载极慢: 单连接 ~100-200KB/s (曾更低至105 B/s), 而 Android 原生"并行下载器"APP 同源 16 段能全速下 2GB (几分钟)。

### Error
- 单连接 10MB 测速: 105-144 B/s (2026-08-24 15:10)
- 16 段 curl 并发: ~150KB/s (无并发增益, 反而劣化)
- TLS 握手/DNS/代理均正常 (TLS1.3 秒连, 无代理, resolv.conf 正常)

### Context
- 环境: 手机 Termux proot (RikkaHub workspace)
- 源: hf-mirror.com (CDN)
- 对比: APP (com.example.paralleldl, 16段 Range 并行) 下载 2GB 3B 模型几分钟完成, adb pull 2GB 仅 20 秒 (~100MB/s, 局域网)

### Suggested Fix
- 大文件下载走 APP (adb UI 驱动 + adb pull 回传) 而非 proot curl
- 或排查: hf-mirror 是否对该出口限速; 测试其他源 (modelscope/cloudflare) 对比 (未完成, 用户叫停)
- fastdl (tools/fastdl) 已写好 16段并行, 但 proot 并发无增益, 待网络问题定位后再用

### Metadata
- Reproducible: yes
- Related Files: /workspace/tools/fastdl, /workspace/paralleldl.apk
---

## [ERR-20260828-003] evolve_v5 启动失败 (nohup 找不到 python3)

**Logged**: 2026-08-28T05:33+08:00
**Priority**: high
**Status**: resolved
**Area**: infra

### Summary
ssh 非交互 shell 中 setsid nohup python3 启动 evolve_v5 失败: PATH 不含 /root/miniconda3/bin

### Error
nohup: failed to run command 'python3': No such file or directory

### Context
- ssh 非交互 shell PATH=/usr/local/sbin:... 无 conda
- 之前 04:02 那次 v5 启动可能同样原因直接退出 (stdout.log 0 字节, log 停在 04:07)
- 另一坑: pkill -f "evolve_v5.py" / pgrep -f 会自匹配 ssh 命令行, 把 ssh 会话杀掉或误判 if 分支

### Suggested Fix
- 用绝对路径 /root/miniconda3/bin/python3 启动
- pkill/pgrep 用 [e]volve_v5 技巧避开自匹配
- v5 启动方式: cd /root/autodl-tmp && setsid nohup /root/miniconda3/bin/python3 -u evolve_v5.py > evolve_v5_stdout.log 2>&1 < /dev/null &

### Resolution
- **Resolved**: 2026-08-28T05:35
- **Notes**: 绝对路径启动成功 (PID 3685), GPU 占 10.6GB, log 正常更新 (r1l0/r1l1 已过, ~30s/步)

### Metadata
- Reproducible: yes
- Related Files: /workspace/evolve_v5.py
