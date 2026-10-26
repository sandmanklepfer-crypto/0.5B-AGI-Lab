'use strict';
/* ══════════════════════════════════════════════════════════
 *  由 PulseScript 编译生成 —— 不要手改
 *  源码服务: build
 *  生成时间: 2026-10-26T06:49:11.318Z
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
