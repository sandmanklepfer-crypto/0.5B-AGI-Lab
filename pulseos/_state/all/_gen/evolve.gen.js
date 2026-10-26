'use strict';
/* ══════════════════════════════════════════════════════════
 *  由 PulseScript 编译生成 —— 不要手改
 *  源码服务: evolve
 *  生成时间: 2026-10-26T06:53:17.590Z
 * ══════════════════════════════════════════════════════════
 */

const $B = {
  /* 未使用内置函数 */
};

const meta =   {
    "name": "evolve",
    "fields": [
      {
        "name": "step",
        "type": "int"
      },
      {
        "name": "value",
        "type": "str"
      },
      {
        "name": "max",
        "type": "int"
      },
      {
        "name": "steps",
        "type": "list"
      }
    ],
    "handlers": [
      {
        "op": "step",
        "params": [
          "out",
          "at",
          "task"
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
      "step": 0,
      "value": "GENESIS",
      "max": 10,
      "steps": []
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
    "step": function ($S, $E, out, at, task) {
  "use strict";
  $S["step"] = ($S["step"] + 1);
  ($S["steps"] = $S["steps"] || []).push({"step": $S["step"], "input": $S["value"], "output": out, "at": at, "task": task});
  $S["value"] = out;
  $E.push({ op: "stepped", payload: {"step": $S["step"]}, after: 0 });
  return $S["step"];
},
    "stat": function ($S, $E) {
  "use strict";
  return {"step": $S["step"], "value": $S["value"], "max": $S["max"], "steps": $S["steps"]};
}
};

module.exports = { meta, init, run, handlers };
