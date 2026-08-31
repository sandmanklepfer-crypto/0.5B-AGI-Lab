import re, json, glob
texts = []
for fp in ["/root/autodl-tmp/corpus_identity.txt", "/root/autodl-tmp/corpus_mix.txt", "/root/autodl-tmp/distill_prompts.txt", "/root/probes.txt"]:
    try:
        for line in open(fp, encoding="utf-8", errors="replace"):
            line = line.strip()
            if 8 <= len(line) <= 150 and "```" not in line: texts.append(line)
    except: pass
for line in open("/root/rag_data.jsonl", encoding="utf-8", errors="replace"):
    try:
        r = json.loads(line)
        c = str(r.get("context",""))[:200]; q = str(r.get("query",""))
        if 8 <= len(c) <= 150: texts.append(c)
        if 8 <= len(q) <= 150: texts.append(q)
    except: pass
for fp in glob.glob("/root/ai_geometry_textbook/*.md"):
    try:
        txt = open(fp, encoding="utf-8").read()
        txt = re.sub(r"```.*?```", " ", txt, flags=re.S)
        sents = re.split(r"(?<=[。！？；;])|\n+", txt)
        buf = ""
        for s in sents:
            s = s.strip()
            if not s or len(s) > 150: continue
            buf += s
            if len(buf) >= 50:
                texts.append(buf[:150]); buf = ""
        if len(buf) >= 20: texts.append(buf[:150])
    except: pass
seen = set(); out = []
for t in texts:
    t = t.strip()
    if not t or t in seen or len(t) > 150: continue
    seen.add(t)
    out.append(t)
    if len(out) >= 900: break
with open("/root/corpus_900.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
maxlen = max(len(t) for t in out)
print("CORPUS2", len(out), "maxlen", maxlen)
