import ctypes, signal, sys

def to(s, f): raise TimeoutError(f'{s} 超时')
signal.signal(signal.SIGALRM, to)

print('===== NNAPI 设备枚举 =====', flush=True)
try:
    nn = ctypes.CDLL('/apex/com.android.neuralnetworks/lib64/libneuralnetworks.so')
    nn.ANeuralNetworks_getDeviceCount.restype = ctypes.c_int
    n = ctypes.c_uint(0)
    r = nn.ANeuralNetworks_getDeviceCount(ctypes.byref(n))
    print(f'getDeviceCount -> {r}, 设备数: {n.value}', flush=True)
    if r == 0 and n.value > 0:
        nn.ANeuralNetworksDevice_getName.restype = ctypes.c_int
        nn.ANeuralNetworksDevice_getName.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        for i in range(n.value):
            buf = ctypes.create_string_buffer(256)
            # 获取 device* (内部实现用句柄, 这里用 createBuffer? 简化: 用 api 遍历)
            # ANeuralNetworks_getDevice(i) 不存在, 通过 getDeviceCount 后的遍历 API:
            # 实际是 ANeuralNetworksDevice 通过 iteration API
            break
    print('NNAPI 枚举完成', flush=True)
except Exception as e:
    print('NNAPI FAIL:', e, flush=True)

print('===== Vulkan 队列族 =====', flush=True)
try:
    vk = ctypes.CDLL('libvulkan.so')
    class AppInfo(ctypes.Structure):
        _fields_ = [('sType', ctypes.c_int), ('pNext', ctypes.c_void_p), ('pApplicationName', ctypes.c_char_p),
                    ('applicationVersion', ctypes.c_uint), ('pEngineName', ctypes.c_char_p),
                    ('engineVersion', ctypes.c_uint), ('apiVersion', ctypes.c_uint)]
    class InstCI(ctypes.Structure):
        _fields_ = [('sType', ctypes.c_int), ('pNext', ctypes.c_void_p), ('flags', ctypes.c_uint),
                    ('pApplicationInfo', ctypes.POINTER(AppInfo)), ('enabledLayerCount', ctypes.c_uint),
                    ('ppEnabledLayerNames', ctypes.c_void_p), ('enabledExtensionCount', ctypes.c_uint),
                    ('ppEnabledExtensionNames', ctypes.c_void_p)]
    ai = AppInfo(1, None, b'p', 1, None, 0, 0x1000000)
    ci = InstCI(1, None, 0, ctypes.pointer(ai), 0, None, 0, None)
    inst = ctypes.c_void_p()
    signal.alarm(8)
    r = vk.vkCreateInstance(ctypes.pointer(ci), None, ctypes.byref(inst))
    signal.alarm(0)
    print(f'vkCreateInstance -> {r}', flush=True)
    if r != 0: sys.exit(1)
    n = ctypes.c_uint(0)
    vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(n), None)
    devs = (ctypes.c_void_p * n.value)()
    vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(n), devs)
    print(f'物理设备: {n.value}', flush=True)
    class QFP(ctypes.Structure):
        _fields_ = [('queueFlags', ctypes.c_uint), ('queueCount', ctypes.c_uint),
                    ('timestampValidBits', ctypes.c_uint), ('minImageTransferGranularity', ctypes.c_uint * 3)]
    nq = ctypes.c_uint(0)
    signal.alarm(8)
    vk.vkGetPhysicalDeviceQueueFamilyProperties(devs[0], ctypes.byref(nq), None)
    signal.alarm(0)
    print(f'队列族数量: {nq.value}', flush=True)
    qf = (QFP * max(nq.value, 1))()
    signal.alarm(8)
    vk.vkGetPhysicalDeviceQueueFamilyProperties(devs[0], ctypes.byref(nq), qf)
    signal.alarm(0)
    for i in range(nq.value):
        f = qf[i].queueFlags
        print(f'  队列族[{i}] flags=0x{f:x} COMPUTE={"是" if f & 0x2 else "否"} GRAPHICS={"是" if f & 0x1 else "否"}', flush=True)
except Exception as e:
    print('VULKAN FAIL:', e, flush=True)
print('DONE', flush=True)
