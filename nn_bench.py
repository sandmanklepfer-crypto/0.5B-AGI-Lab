import ctypes, time

nn = ctypes.CDLL('/apex/com.android.neuralnetworks/lib64/libneuralnetworks.so')

# 常量
ANEURALNETWORKS_TENSOR_FLOAT32 = 4
ANEURALNETWORKS_FULLY_CONNECTED = 11
ANEURALNETWORKS_FUSED_NONE = 0
ANEURALNETWORKS_PREFER_FAST_SINGLE_ANSWER = 2

class OperandType(ctypes.Structure):
    _fields_ = [('type', ctypes.c_int32), ('dimensionCount', ctypes.c_uint32),
                ('dimensions', ctypes.POINTER(ctypes.c_uint32)),
                ('scale', ctypes.c_float), ('zeroPoint', ctypes.c_int32)]

D = 896
def make_model():
    model = ctypes.c_void_p()
    nn.ANeuralNetworksModel_create(ctypes.byref(model))
    # operand: input [1,D]
    dims_in = (ctypes.c_uint32 * 2)(1, D)
    t_in = OperandType(ANEURALNETWORKS_TENSOR_FLOAT32, 2, dims_in, 0, 0)
    # weights [D,D]
    dims_w = (ctypes.c_uint32 * 2)(D, D)
    t_w = OperandType(ANEURALNETWORKS_TENSOR_FLOAT32, 2, dims_w, 0, 0)
    # bias [D]
    dims_b = (ctypes.c_uint32 * 1)(D)
    t_b = OperandType(ANEURALNETWORKS_TENSOR_FLOAT32, 1, dims_b, 0, 0)
    nn.ANeuralNetworksModel_addOperand(model, ctypes.byref(t_in))
    nn.ANeuralNetworksModel_addOperand(model, ctypes.byref(t_w))
    nn.ANeuralNetworksModel_addOperand(model, ctypes.byref(t_b))
    nn.ANeuralNetworksModel_addOperand(model, ctypes.byref(t_in))
    # 权重数据
    w = (ctypes.c_float * (D * D))(*([0.01] * (D * D)))
    b = (ctypes.c_float * D)(*([0.0] * D))
    nn.ANeuralNetworksModel_setOperandValue(model, 1, w, D * D * 4)
    nn.ANeuralNetworksModel_setOperandValue(model, 2, b, D * 4)
    # operation FULLY_CONNECTED: in=[0,1,2,3(fused)], out=[3? no out index=3]
    inputs = (ctypes.c_uint32 * 4)(0, 1, 2, 0)  # fused none
    outputs = (ctypes.c_uint32 * 1)(3)
    nn.ANeuralNetworksModel_addOperation(model, ANEURALNETWORKS_FULLY_CONNECTED, 4, inputs, 1, outputs)
    ids_in = (ctypes.c_uint32 * 1)(0)
    ids_out = (ctypes.c_uint32 * 1)(3)
    nn.ANeuralNetworksModel_identifyInputsAndOutputs(model, 1, ids_in, 1, ids_out)
    r = nn.ANeuralNetworksModel_finish(model)
    return model, r

model, r = make_model()
print(f'模型构建 finish -> {r}', flush=True)
if r != 0:
    print('FAIL'); exit(1)

def bench(comp, label, iters=50):
    exec_ = ctypes.c_void_p()
    nn.ANeuralNetworksExecution_create(comp, ctypes.byref(exec_))
    x = (ctypes.c_float * D)(*([1.0] * D))
    y = (ctypes.c_float * D)(*([0.0] * D))
    nn.ANeuralNetworksExecution_setInput(exec_, 0, None, x, D * 4)
    nn.ANeuralNetworksExecution_setOutput(exec_, 0, None, y, D * 4)
    t0 = time.time()
    for _ in range(iters):
        nn.ANeuralNetworksExecution_startCompute(exec_, None)
        nn.ANeuralNetworksExecution_wait(exec_)
    dt = (time.time() - t0) / iters
    print(f'{label}: {dt*1000:.3f} ms/次 ({1/dt:.0f} 次/s) 输出样本={y[0]:.4f}', flush=True)

# compilation A: 默认
comp_a = ctypes.c_void_p()
nn.ANeuralNetworksCompilation_create(model, ctypes.byref(comp_a))
nn.ANeuralNetworksCompilation_setPreference(comp_a, ANEURALNETWORKS_PREFER_FAST_SINGLE_ANSWER)
r = nn.ANeuralNetworksCompilation_finish(comp_a)
print(f'编译A(默认加速) -> {r}', flush=True)
bench(comp_a, 'NNAPI 默认(系统选加速器)', 50)
print('DONE', flush=True)
