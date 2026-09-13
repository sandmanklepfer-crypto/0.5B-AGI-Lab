import ctypes, signal, sys

def to(s, f): raise TimeoutError(f'{s} 超时')
signal.signal(signal.SIGALRM, to)

vk = ctypes.CDLL('libvulkan.so')
print('libvulkan loaded', flush=True)

class AppInfo(ctypes.Structure):
    _fields_ = [('sType', ctypes.c_int), ('pNext', ctypes.c_void_p), ('pApplicationName', ctypes.c_char_p),
                ('applicationVersion', ctypes.c_uint), ('pEngineName', ctypes.c_char_p),
                ('engineVersion', ctypes.c_uint), ('apiVersion', ctypes.c_uint)]
class InstCI(ctypes.Structure):
    _fields_ = [('sType', ctypes.c_int), ('pNext', ctypes.c_void_p), ('flags', ctypes.c_uint),
                ('pApplicationInfo', ctypes.POINTER(AppInfo)), ('enabledLayerCount', ctypes.c_uint),
                ('ppEnabledLayerNames', ctypes.c_void_p), ('enabledExtensionCount', ctypes.c_uint),
                ('ppEnabledExtensionNames', ctypes.c_void_p)]
class Props(ctypes.Structure):
    _fields_ = [('apiVersion', ctypes.c_uint), ('driverVersion', ctypes.c_uint), ('vendorID', ctypes.c_uint),
                ('deviceID', ctypes.c_uint), ('deviceType', ctypes.c_int),
                ('deviceName', ctypes.c_char * 256), ('pipelineCacheUUID', ctypes.c_ubyte * 16)]

ai = AppInfo(1, None, b'probe', 1, None, 0, 0x1000000)
ci = InstCI(1, None, 0, ctypes.pointer(ai), 0, None, 0, None)
inst = ctypes.c_void_p()
signal.alarm(10)
r = vk.vkCreateInstance(ctypes.pointer(ci), None, ctypes.byref(inst))
signal.alarm(0)
print('vkCreateInstance:', r, flush=True)
if r != 0: sys.exit(1)

n = ctypes.c_uint(0)
vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(n), None)
print('GPU 数量:', n.value, flush=True)
if n.value == 0: sys.exit(1)
devs = (ctypes.c_void_p * n.value)()
vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(n), devs)
p = Props()
signal.alarm(10)
vk.vkGetPhysicalDeviceProperties(devs[0], ctypes.byref(p))
signal.alarm(0)
print('GPU 名称:', p.deviceName.decode(), flush=True)
print('API 版本:', hex(p.apiVersion), '驱动:', hex(p.driverVersion), flush=True)
print('vendor:', hex(p.vendorID), 'device:', hex(p.deviceID), flush=True)
print('PROBE_DONE', flush=True)
