import json, urllib.request
Q="什么是人工智能？"
for port,tag in [(8082,"BASE (qwen05b_q4km)"),(8081,"calc_v1 (计算蒸馏)")]:
    U=f"http://127.0.0.1:{port}/v1/chat/completions"
    print(f"\n{'='*66}\n### {tag}  (port {port})\n{'='*66}", flush=True)
    for q in [Q, "12加34等于多少？", "水的沸点是多少度？"]:
        body=json.dumps({"messages":[{"role":"user","content":q}],
                         "max_tokens":60,"temperature":0.7}).encode()
        req=urllib.request.Request(U,data=body,headers={"Content-Type":"application/json"})
        try:
            r=json.loads(urllib.request.urlopen(req,timeout=90).read())
            a=r["choices"][0]["message"]["content"].strip().replace("\n"," ")
        except Exception as e:
            a=f"ERR {str(e)[:70]}"
        print(f"  Q: {q}\n     A: {a[:150]}\n", flush=True)
print("BT_DONE")
