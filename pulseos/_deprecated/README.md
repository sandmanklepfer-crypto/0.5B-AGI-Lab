# 已弃用的 bake 脚本

这些脚本被 `bake_all.js` 全面替代。

## 为什么弃用

它们每个都直接 `execFileSync('python3')` 算完写死进 HTML，
**PulseOS 完全没参与**。页面上看到的所有状态数字（序号、归档计数、
环形 slot、因果分类）都是脚本自己拼的字符串，不是 OS 算的。

## 替代方案

`bake_all.js` 里对应 6 个微内核（`services/site.pulse`）：

| 旧脚本 | 现在由谁算 |
|---|---|
| bake_chain.js | `chain` 微内核（seq / prev / 归档） |
| bake_pool.js | `pool` 微内核（环形 slot） |
| bake_evolve.js | `evolve` 微内核（每步吃上一步） |
| bake_answers.js | `facts` 微内核 |
| bake_toolapi.js | `facts` 微内核 |
| bake_directive.js | `facts` 微内核 |
| bake_entry.js | 全部微内核汇总 |
| bake_via_os.js | 并入 entry.html |

## 保留原因

作为对照：**走 OS** 和 **不走 OS** 的页面，数据来源可核对。
走 OS 的页面页头有「数据来源：PulseOS X 微内核」+ OS 自算的状态值。
