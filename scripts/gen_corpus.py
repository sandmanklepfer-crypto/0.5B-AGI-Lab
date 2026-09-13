import re, json, glob
texts = []
for fp in ["/root/autodl-tmp/corpus_identity.txt", "/root/autodl-tmp/corpus_mix.txt", "/root/autodl-tmp/distill_prompts.txt", "/root/probes.txt"]:
    try:
        for line in open(fp, encoding="utf-8", errors="replace"):
            line = line.strip()
            if len(line) >= 8: texts.append(line)
    except: pass
for line in open("/root/rag_data.jsonl", encoding="utf-8", errors="replace"):
    try:
        r = json.loads(line)
        texts.append(str(r.get("context",""))[:400]); texts.append(str(r.get("query","")))
    except: pass
for fp in glob.glob("/root/ai_geometry_textbook/*.md"):
    try:
        txt = open(fp, encoding="utf-8").read()
        sents = re.split(r"(?<=[。！？；;])|\n+", txt)
        buf = ""
        for s in sents:
            s = s.strip()
            if not s: continue
            buf += s
            if len(buf) >= 60: texts.append(buf); buf = ""
        if len(buf) >= 20: texts.append(buf)
    except: pass
seen = set(); out = []
for t in texts:
    t = t.strip()
    if not t or t in seen: continue
    seen.add(t)
    out.append(t)
    if len(out) >= 900: break
with open("/root/corpus_900.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("CORPUS_900", len(out))
