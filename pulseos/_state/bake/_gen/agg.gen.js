'use strict';
/* ══════════════════════════════════════════════════════════
 *  由 PulseScript 编译生成 —— 不要手改
 *  源码服务: agg
 *  生成时间: 2026-10-26T06:39:50.489Z
 * ══════════════════════════════════════════════════════════
 */

const $B = {
  contains: (a, v) => (Array.isArray(a) ? a.indexOf(v) >= 0 : String(a == null ? '' : a).indexOf(String(v)) >= 0),
  len: (x) => (x == null ? 0 : (Array.isArray(x) ? x.length : (typeof x === 'string' ? x.length : Object.keys(x).length))),
};

const meta =   {
    "name": "agg",
    "fields": [
      {
        "name": "n",
        "type": "int"
      },
      {
        "name": "kinds",
        "type": "list"
      },
      {
        "name": "keylen",
        "type": "int"
      }
    ],
    "handlers": [
      {
        "op": "fact_added",
        "params": [
          "e"
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
      "n": 0,
      "kinds": [],
      "keylen": 0
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
    "fact_added": function ($S, $E, e) {
  "use strict";
  $S["n"] = ($S["n"] + 1);
  if (($B.contains($S["kinds"], (e)[ "kind" ]) === false)) {
    ($S["kinds"] = $S["kinds"] || []).push((e)[ "kind" ]);
  }
  $S["keylen"] = ($S["keylen"] + $B.len((e)[ "k" ]));
},
    "report": function ($S, $E) {
  "use strict";
  return {"n": $S["n"], "kinds": $S["kinds"], "keylen": $S["keylen"]};
}
};

module.exports = { meta, init, run, handlers };
