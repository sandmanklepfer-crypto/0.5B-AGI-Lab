'use strict';
/* ══════════════════════════════════════════════════════════
 *  由 PulseScript 编译生成 —— 不要手改
 *  源码服务: provider
 *  生成时间: 2026-10-26T06:43:24.744Z
 * ══════════════════════════════════════════════════════════
 */

const $B = {
  get: (o, k, d) => (o != null && o[k] !== undefined ? o[k] : (d === undefined ? null : d)),
  put: (o, k, v) => { const c = Object.assign({}, o || {}); c[k] = v; return c; },
};

const meta =   {
    "name": "provider",
    "fields": [
      {
        "name": "m",
        "type": "map"
      },
      {
        "name": "n",
        "type": "int"
      },
      {
        "name": "hits",
        "type": "int"
      },
      {
        "name": "seq",
        "type": "int"
      }
    ],
    "handlers": [
      {
        "op": "put",
        "params": [
          "k",
          "v",
          "kind"
        ]
      },
      {
        "op": "get",
        "params": [
          "k"
        ]
      },
      {
        "op": "getMany",
        "params": [
          "ks"
        ]
      },
      {
        "op": "stat",
        "params": []
      },
      {
        "op": "dump",
        "params": []
      }
    ]
  };

function init() {
  return {
      "m": {},
      "n": 0,
      "hits": 0,
      "seq": 0
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
    "put": function ($S, $E, k, v, kind) {
  "use strict";
  $S["m"] = $B.put($S["m"], k, {"v": v, "kind": kind});
  $S["n"] = ($S["n"] + 1);
  $S["seq"] = ($S["seq"] + 1);
  $E.push({ op: "put_done", payload: {"k": k, "kind": kind}, after: 0 });
  return $S["seq"];
},
    "get": function ($S, $E, k) {
  "use strict";
  $S["hits"] = ($S["hits"] + 1);
  return $B.get($S["m"], k, null);
},
    "getMany": function ($S, $E, ks) {
  "use strict";
  $S["hits"] = ($S["hits"] + 1);
  return ks;
},
    "stat": function ($S, $E) {
  "use strict";
  return {"n": $S["n"], "seq": $S["seq"], "hits": $S["hits"]};
},
    "dump": function ($S, $E) {
  "use strict";
  return {"n": $S["n"], "m": $S["m"], "seq": $S["seq"], "hits": $S["hits"]};
}
};

module.exports = { meta, init, run, handlers };
