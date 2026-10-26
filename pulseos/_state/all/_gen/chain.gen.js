'use strict';
/* ══════════════════════════════════════════════════════════
 *  由 PulseScript 编译生成 —— 不要手改
 *  源码服务: chain
 *  生成时间: 2026-10-26T06:49:51.732Z
 * ══════════════════════════════════════════════════════════
 */

const $B = {
  len: (x) => (x == null ? 0 : (Array.isArray(x) ? x.length : (typeof x === 'string' ? x.length : Object.keys(x).length))),
  slice: (a, s, e) => (a || []).slice(s, e),
};

const meta =   {
    "name": "chain",
    "fields": [
      {
        "name": "seq",
        "type": "int"
      },
      {
        "name": "head",
        "type": "str"
      },
      {
        "name": "n",
        "type": "int"
      },
      {
        "name": "archive",
        "type": "int"
      },
      {
        "name": "keep",
        "type": "int"
      },
      {
        "name": "list",
        "type": "list"
      }
    ],
    "handlers": [
      {
        "op": "append",
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
      "head": "GENESIS",
      "n": 0,
      "archive": 0,
      "keep": 15,
      "list": []
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
    "append": function ($S, $E, hash, at, task) {
  "use strict";
  $S["seq"] = ($S["seq"] + 1);
  ($S["list"] = $S["list"] || []).push({"seq": $S["seq"], "prev": $S["head"], "hash": hash, "at": at, "task": task});
  $S["head"] = hash;
  $S["n"] = ($S["n"] + 1);
  if (($B.len($S["list"]) > $S["keep"])) {
    $S["list"] = $B.slice($S["list"], ($B.len($S["list"]) - $S["keep"]), $B.len($S["list"]));
    $S["archive"] = ($S["archive"] + 1);
  }
  $E.push({ op: "appended", payload: {"seq": $S["seq"]}, after: 0 });
  return $S["seq"];
},
    "stat": function ($S, $E) {
  "use strict";
  return {"seq": $S["seq"], "head": $S["head"], "n": $S["n"], "archive": $S["archive"], "keep": $S["keep"], "list": $S["list"]};
}
};

module.exports = { meta, init, run, handlers };
