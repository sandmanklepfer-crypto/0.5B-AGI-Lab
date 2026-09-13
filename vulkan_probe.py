import ctypes

vk = ctypes.CDLL('libvulkan.so')

class VkApplicationInfo(ctypes.Structure):
    _fields_ = [('sType', ctypes.c_int), ('pNext', ctypes.c_void_p),
                ('pApplicationName', ctypes.c_char_p), ('applicationVersion', ctypes.c_uint),
                ('pEngineName', ctypes.c_char_p), ('engineVersion', ctypes.c_uint),
                ('apiVersion', ctypes.c_uint)]

class VkInstanceCreateInfo(ctypes.Structure):
    _fields_ = [('sType', ctypes.c_int), ('pNext', ctypes.c_void_p), ('flags', ctypes.c_uint),
                ('pApplicationInfo', ctypes.POINTER(VkApplicationInfo)),
                ('enabledLayerCount', ctypes.c_uint), ('ppEnabledLayerNames', ctypes.c_void_p),
                ('enabledExtensionCount', ctypes.c_uint), ('ppEnabledExtensionNames', ctypes.c_void_p)]

class VkPhysicalDeviceProperties(ctypes.Structure):
    _fields_ = [('apiVersion', ctypes.c_uint), ('driverVersion', ctypes.c_uint),
                ('vendorID', ctypes.c_uint), ('deviceID', ctypes.c_uint),
                ('deviceType', ctypes.c_int), ('deviceName', ctypes.c_char * 256),
                ('pipelineCacheUUID', ctypes.c_ubyte * 16)]

vk.vkEnumerateInstanceVersion.restype = ctypes.c_int
ver = ctypes.c_uint(0)
vk.vkEnumerateInstanceVersion(ctypes.byref(ver))
print('Vulkan API 版本:', hex(ver.value))

app_info = VkApplicationInfo(1, None, b'gpu_probe', 1, None, 0, 0x1000000)
create_info = VkInstanceCreateInfo(1, None, 0, ctypes.pointer(app_info), 0, None, 0, None)
inst = ctypes.c_void_p()
r = vk.vkCreateInstance(ctypes.pointer(create_info), None, ctypes.byref(inst))
print('vkCreateInstance:', r)
if r != 0:
    exit(1)

vk.vkEnumeratePhysicalDevices.restype = ctypes.c_int
n = ctypes.c_uint(0)
vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(n), None)
print('物理 GPU 数量:', n.value)
if n.value == 0:
    exit(1)

devs = (ctypes.c_void_p * n.value)()
vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(n), devs)
for i in range(n.value):
    props = VkPhysicalDeviceProperties()
    vk.vkGetPhysicalDeviceProperties(devs[i], ctypes.byref(props))
    print(f'GPU[{i}]: {props.deviceName.decode()} | vendor=0x{props.vendorID:x} device=0x{props.deviceID:x} type={props.deviceType}')

# 查询设备扩展(确认 compute 能力)
print('PROBE_DONE')
