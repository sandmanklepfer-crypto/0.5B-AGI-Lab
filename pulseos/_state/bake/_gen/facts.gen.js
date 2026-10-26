'use strict';
/* ══════════════════════════════════════════════════════════
 *  由 PulseScript 编译生成 —— 不要手改
 *  源码服务: facts
 *  生成时间: 2026-10-26T06:39:50.483Z
 * ══════════════════════════════════════════════════════════
 */

const $B = {
  /* 未使用内置函数 */
};

const meta =   {
    "name": "facts",
    "fields": [
      {
        "name": "items",
        "type": "list"
      },
      {
        "name": "count",
        "type": "int"
      }
    ],
    "handlers": [
      {
        "op": "add",
        "params": [
          "k",
          "kind"
        ]
      },
      {
        "op": "report",
        "params": []
      }
    ]
  };

function init() {
  return {
      "items": [],
      "count": 0
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
    "add": function ($S, $E, k, kind) {
  "use strict";
  ($S["items"] = $S["items"] || []).push({"k": k, "kind": kind});
  $S["count"] = ($S["count"] + 1);
  $E.push({ op: "fact_added", payload: {"k": k, "kind": kind}, after: 0 });
},
    "report": function ($S, $E) {
  "use strict";
  return {"count": $S["count"], "items": $S["items"]};
}
};

module.exports = { meta, init, run, handlers };
