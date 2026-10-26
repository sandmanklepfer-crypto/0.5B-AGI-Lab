'use strict';
/* ★ 安全遮盖：即使编译器被绕过，也不让宿主对象可见 */
const require = undefined;
const module = undefined;
const exports = undefined;
const process = undefined;
const global = undefined;
const globalThis = undefined;
const __dirname = undefined;
const __filename = undefined;
const Buffer = undefined;
const eval = undefined;
const Function = undefined;
const setTimeout = undefined;
const setInterval = undefined;

/* ══════════════════════════════════════════════════════════
 *  由 PulseScript 编译生成 —— 不要手改
 *  源码服务: build
 *  生成时间: 2026-10-26T07:17:52.825Z
 * ══════════════════════════════════════════════════════════
 */

const $B = {
  /* 未使用内置函数 */
};

const meta =   {
    "name": "build",
    "fields": [
      {
        "name": "pages",
        "type": "list"
      },
      {
        "name": "n",
        "type": "int"
      }
    ],
    "handlers": [
      {
        "op": "page",
        "params": [
          "name"
        ]
      },
      {
        "op": "stat",
        "params": []
      }
    ]
  };

function init() {
  return {
      "pages": [],
      "n": 0
  };
}

/* 一次脉冲：返回 { result, emits, state } */
function run(op, args, state) {
  const $S = Object.assign({}, state);
  const $E = [];
  const H = handlers[op];
  if (!H) return { ok: false, error: "没有 on \"" + op + "\"" };
  let result = null;
  try {
    result = H.apply(null, [$S, $E].concat(args || []));
  } catch (e) {
    return { ok: false, error: String(e && e.message || e) };
  }
  return { ok: true, result: result, emits: $E, state: $S };
}

const handlers = {
    "page": function ($S, $E, name) {
  "use strict";
  ($S["pages"] = $S["pages"] || []).push(name);
  $S["n"] = ($S["n"] + 1);
  return $S["n"];
},
    "stat": function ($S, $E) {
  "use strict";
  return {"pages": $S["pages"], "n": $S["n"]};
}
};

module.exports = { meta, init, run, handlers };
