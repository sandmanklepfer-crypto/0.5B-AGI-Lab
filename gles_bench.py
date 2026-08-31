import ctypes, time

EGL = ctypes.CDLL('libEGL.so')
GL = ctypes.CDLL('libGLESv3.so')

# EGL 常量
EGL_DEFAULT_DISPLAY = 0
EGL_OPENGL_ES3_BIT = 0x40
EGL_PBUFFER_BIT = 0x0001
EGL_SURFACE_TYPE = 0x3033
EGL_RENDERABLE_TYPE = 0x3040
EGL_WIDTH = 0x3057
EGL_HEIGHT = 0x3058
EGL_CONTEXT_CLIENT_VERSION = 0x3098
EGL_NO_CONTEXT = 0
EGL_NO_SURFACE = 0

EGL.eglGetDisplay.restype = ctypes.c_void_p
EGL.eglGetDisplay.argtypes = [ctypes.c_void_p]
EGL.eglInitialize.restype = ctypes.c_int
EGL.eglChooseConfig.restype = ctypes.c_int
EGL.eglCreatePbufferSurface.restype = ctypes.c_void_p
EGL.eglCreateContext.restype = ctypes.c_void_p
EGL.eglMakeCurrent.restype = ctypes.c_int
EGL.eglGetError.restype = ctypes.c_int

GL.glShaderSource.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_int)]
GL.glCompileShader.argtypes = [ctypes.c_uint]
GL.glCreateShader.restype = ctypes.c_uint
GL.glCreateProgram.restype = ctypes.c_uint
GL.glAttachShader.argtypes = [ctypes.c_uint, ctypes.c_uint]
GL.glLinkProgram.argtypes = [ctypes.c_uint]
GL.glUseProgram.argtypes = [ctypes.c_uint]
GL.glGenBuffers.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
GL.glBindBuffer.argtypes = [ctypes.c_uint, ctypes.c_uint]
GL.glBufferData.argtypes = [ctypes.c_uint, ctypes.c_long, ctypes.c_void_p, ctypes.c_uint]
GL.glBindBufferBase.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
GL.glDispatchCompute.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
GL.glFinish.argtypes = []
GL.glMapBufferRange.restype = ctypes.c_void_p
GL.glMapBufferRange.argtypes = [ctypes.c_uint, ctypes.c_long, ctypes.c_long, ctypes.c_uint]
GL.glUnmapBuffer.argtypes = [ctypes.c_uint]
GL.glGetError.restype = ctypes.c_uint
GL.glGetShaderiv.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_int)]
GL.glGetProgramiv.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_int)]
GL.glGetShaderInfoLog.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.c_char_p]
GL.glGetProgramInfoLog.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.c_char_p]

GL_COMPUTE_SHADER = 0x91B9
GL_SHADER_STORAGE_BUFFER = 0x90D2
GL_STATIC_DRAW = 0x88E4
GL_COMPILE_STATUS = 0x8B81
GL_LINK_STATUS = 0x8B82

# --- EGL 初始化 (pbuffer 无窗口) ---
dpy = EGL.eglGetDisplay(EGL_DEFAULT_DISPLAY)
if not dpy:
    print('FAIL eglGetDisplay'); exit(1)
major, minor = ctypes.c_int(), ctypes.c_int()
if not EGL.eglInitialize(dpy, ctypes.byref(major), ctypes.byref(minor)):
    print('FAIL eglInitialize, err=', EGL.eglGetError()); exit(1)
print(f'EGL {major.value}.{minor.value}', flush=True)

attr = (ctypes.c_int * 11)(EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
                            EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
                            EGL_WIDTH, 64, EGL_HEIGHT, 64,
                            0x3038, 1, 0x3038)  # 0x3038=EGL_NONE, 0x3038 重复无妨
cfg = ctypes.c_void_p()
num = ctypes.c_int()
r = EGL.eglChooseConfig(dpy, attr, ctypes.byref(cfg), 1, ctypes.byref(num))
print('eglChooseConfig ->', r, 'num=', num.value, flush=True)
if num.value == 0:
    print('FAIL no config'); exit(1)
# 重新选择配置 (上面 attr 可能不对, 简化重选)
attr2 = (ctypes.c_int * 9)(EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, 0x3038)
cfgs = (ctypes.c_void_p * 8)()
num2 = ctypes.c_int()
EGL.eglChooseConfig(dpy, attr2, cfgs, 8, ctypes.byref(num2))
print('configs:', num2.value, flush=True)
if num2.value == 0:
    print('FAIL no config2'); exit(1)
surf = EGL.eglCreatePbufferSurface(dpy, cfgs[0], attr2)
ctx = EGL.eglCreateContext(dpy, cfgs[0], EGL_NO_CONTEXT, (ctypes.c_int * 3)(EGL_CONTEXT_CLIENT_VERSION, 3, 0x3038))
r = EGL.eglMakeCurrent(dpy, surf, surf, ctx)
print('eglMakeCurrent ->', r, 'err=', EGL.eglGetError(), flush=True)
if not r:
    print('FAIL makecurrent'); exit(1)
print('EGL+GLES3 上下文 OK', flush=True)

# --- compute shader: 矩阵乘 896x896x896 ---
D = 896
shader_src = f"""#version 310 es
layout(local_size_x = 16, local_size_y = 16) in;
layout(std430, binding = 0) buffer BufA {{ float a[]; }};
layout(std430, binding = 1) buffer BufB {{ float b[]; }};
layout(std430, binding = 2) buffer BufC {{ float c[]; }};
const uint D = {D}u;
void main() {{
    uint row = gl_GlobalInvocationID.y;
    uint col = gl_GlobalInvocationID.x;
    if (row >= D || col >= D) return;
    float sum = 0.0;
    for (uint k = 0u; k < D; k++) sum += a[row * D + k] * b[k * D + col];
    c[row * D + col] = sum;
}}
"""
src = ctypes.c_char_p(shader_src.encode())
sh = GL.glCreateShader(GL_COMPUTE_SHADER)
GL.glShaderSource(sh, 1, ctypes.byref(src), None)
GL.glCompileShader(sh)
st = ctypes.c_int()
GL.glGetShaderiv(sh, GL_COMPILE_STATUS, ctypes.byref(st))
if not st.value:
    log = ctypes.create_string_buffer(2048)
    GL.glGetShaderInfoLog(sh, 2048, None, log)
    print('SHADER FAIL:', log.value.decode()); exit(1)
prog = GL.glCreateProgram()
GL.glAttachShader(prog, sh)
GL.glLinkProgram(prog)
lt = ctypes.c_int()
GL.glGetProgramiv(prog, GL_LINK_STATUS, ctypes.byref(lt))
if not lt.value:
    log = ctypes.create_string_buffer(2048)
    GL.glGetProgramInfoLog(prog, 2048, None, log)
    print('LINK FAIL:', log.value.decode()); exit(1)
print('compute shader 编译+链接 OK', flush=True)

# --- buffers ---
a = (ctypes.c_float * (D * D))(*([0.01] * (D * D)))
b = (ctypes.c_float * (D * D))(*([0.02] * (D * D)))
c = (ctypes.c_float * (D * D))(*([0.0] * (D * D)))
bufs = (ctypes.c_uint * 3)()
GL.glGenBuffers(3, bufs)
GL.glBindBuffer(GL_SHADER_STORAGE_BUFFER, bufs[0])
GL.glBufferData(GL_SHADER_STORAGE_BUFFER, D * D * 4, a, GL_STATIC_DRAW)
GL.glBindBuffer(GL_SHADER_STORAGE_BUFFER, bufs[1])
GL.glBufferData(GL_SHADER_STORAGE_BUFFER, D * D * 4, b, GL_STATIC_DRAW)
GL.glBindBuffer(GL_SHADER_STORAGE_BUFFER, bufs[2])
GL.glBufferData(GL_SHADER_STORAGE_BUFFER, D * D * 4, None, GL_STATIC_DRAW)
GL.glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, bufs[0])
GL.glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 1, bufs[1])
GL.glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 2, bufs[2])
GL.glUseProgram(prog)

# --- 执行 + 计时 ---
groups = (D + 15) // 16
# 预热
GL.glDispatchCompute(groups, groups, 1)
GL.glFinish()
t0 = time.time()
ITER = 50
for _ in range(ITER):
    GL.glDispatchCompute(groups, groups, 1)
GL.glFinish()
dt = (time.time() - t0) / ITER
gflops = 2.0 * D * D * D / (dt / 1000.0) / 1e9
err = GL.glGetError()
# 读回验证
GL.glBindBuffer(GL_SHADER_STORAGE_BUFFER, bufs[2])
ptr = GL.glMapBufferRange(GL_SHADER_STORAGE_BUFFER, 0, D * D * 4, 0x1)
c = (ctypes.c_float * (D * D)).from_address(ptr)
GL.glUnmapBuffer(GL_SHADER_STORAGE_BUFFER)
print(f'GPU(GLES compute) 矩阵乘 {D}^3: {dt*1000:.3f} ms/次 | {gflops:.1f} GFLOPS | glError={err}', flush=True)
print(f'验证: c[0]={c[0]:.4f} (期望 0.01*0.02*{D}={0.01*0.02*D:.4f})', flush=True)
print('GPU_BENCH_DONE', flush=True)
