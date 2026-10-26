'use strict';
/* ══════════════════════════════════════════════════════════
 *  由 PulseScript 编译生成 —— 不要手改
 *  源码服务: pool
 *  生成时间: 2026-10-26T06:49:11.297Z
 * ══════════════════════════════════════════════════════════
 */

const $B = {
  len: (x) => (x == null ? 0 : (Array.isArray(x) ? x.length : (typeof x === 'string' ? x.length : Object.keys(x).length))),
  slice: (a, s, e) => (a || []).slice(s, e),
};

const meta =   {
    "name": "pool",
    "fields": [
      {
        "name": "seq",
        "type": "int"
      },
      {
        "name": "slot",
        "type": "int"
      },
      {
        "name": "slots",
        "type": "int"
      },
      {
        "name": "total",
        "type": "int"
      },
      {
        "name": "ring",
        "type": "list"
      }
    ],
    "handlers": [
      {
        "op": "write",
        "params": [
          "hash",
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
      "seq": 0,
      "slot": 0,
      "slots": 10,
      "total": 0,
      "ring": []
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
    "write": function ($S, $E, hash, at, task) {
  "use strict";
  $S["seq"] = ($S["seq"] + 1);
  $S["total"] = ($S["total"] + 1);
  ($S["ring"] = $S["ring"] || []).push({"seq": $S["seq"], "slot": $S["slot"], "hash": hash, "at": at, "task": task});
  $S["slot"] = ($S["slot"] + 1);
  if (($S["slot"] >= $S["slots"])) {
    $S["slot"] = 0;
  }
  if (($B.len($S["ring"]) > $S["slots"])) {
    $S["ring"] = $B.slice($S["ring"], ($B.len($S["ring"]) - $S["slots"]), $B.len($S["ring"]));
  }
  $E.push({ op: "written", payload: {"seq": $S["seq"]}, after: 0 });
  return $S["seq"];
},
    "stat": function ($S, $E) {
  "use strict";
  return {"seq": $S["seq"], "total": $S["total"], "nextSlot": $S["slot"], "slots": $S["slots"], "ring": $S["ring"]};
}
};

module.exports = { meta, init, run, handlers };
