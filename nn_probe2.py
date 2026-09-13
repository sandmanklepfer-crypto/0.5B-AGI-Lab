import ctypes

nn = ctypes.CDLL('/apex/com.android.neuralnetworks/lib64/libneuralnetworks.so')
nn.ANeuralNetworks_getDeviceCount.restype = ctypes.c_int
nn.ANeuralNetworks_getDeviceCount.argtypes = [ctypes.POINTER(ctypes.c_uint)]
n = ctypes.c_uint(0)
r = nn.ANeuralNetworks_getDeviceCount(ctypes.byref(n))
print(f'设备数: {n.value}', flush=True)

nn.ANeuralNetworks_getDevice.restype = ctypes.c_int
nn.ANeuralNetworks_getDevice.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
nn.ANeuralNetworksDevice_getName.restype = ctypes.c_int
nn.ANeuralNetworksDevice_getName.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
nn.ANeuralNetworksDevice_getVersion.restype = ctypes.c_int
nn.ANeuralNetworksDevice_getVersion.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

for i in range(n.value):
    dev = ctypes.c_void_p()
    r2 = nn.ANeuralNetworks_getDevice(i, ctypes.byref(dev))
    name = ctypes.create_string_buffer(256)
    ver = ctypes.create_string_buffer(256)
    r3 = nn.ANeuralNetworksDevice_getName(dev, name)
    r4 = nn.ANeuralNetworksDevice_getVersion(dev, ver)
    print(f'设备[{i}]: name="{name.value.decode()}" ver="{ver.value.decode()}"', flush=True)
print('DONE', flush=True)
