'use strict';
/* ══════════════════════════════════════════════════════════
 *  由 PulseScript 编译生成 —— 不要手改
 *  源码服务: index
 *  生成时间: 2026-10-26T06:49:11.313Z
 * ══════════════════════════════════════════════════════════
 */

const $B = {
  /* 未使用内置函数 */
};

const meta =   {
    "name": "index",
    "fields": [
      {
        "name": "time",
        "type": "list"
      },
      {
        "name": "hash",
        "type": "list"
      },
      {
        "name": "math",
        "type": "list"
      },
      {
        "name": "other",
        "type": "list"
      },
      {
        "name": "total",
        "type": "int"
      }
    ],
    "handlers": [
      {
        "op": "put_done",
        "params": [
          "e"
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
      "time": [],
      "hash": [],
      "math": [],
      "other": [],
      "total": 0
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
    "put_done": function ($S, $E, e) {
  "use strict";
  $S["total"] = ($S["total"] + 1);
  if (((e)[ "kind" ] === "time")) {
    ($S["time"] = $S["time"] || []).push((e)[ "k" ]);
  }
  if (((e)[ "kind" ] === "hash")) {
    ($S["hash"] = $S["hash"] || []).push((e)[ "k" ]);
  }
  if (((e)[ "kind" ] === "math")) {
    ($S["math"] = $S["math"] || []).push((e)[ "k" ]);
  }
  if (((e)[ "kind" ] === "other")) {
    ($S["other"] = $S["other"] || []).push((e)[ "k" ]);
  }
},
    "stat": function ($S, $E) {
  "use strict";
  return {"time": $S["time"], "hash": $S["hash"], "math": $S["math"], "total": $S["total"]};
}
};

module.exports = { meta, init, run, handlers };
