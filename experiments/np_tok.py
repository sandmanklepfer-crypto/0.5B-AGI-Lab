# -*- coding: utf-8 -*-
"""np_tok.py — 从 GGUF 读词表, 实现 Qwen2 的 encode/decode (byte-level BPE)"""
import re, json
from gguf import GGUFReader

def bytes_to_unicode():
    bs = list(range(ord("!"), ord("~")+1)) + list(range(ord("¡"), ord("¬")+1)) + list(range(ord("®"), ord("ÿ")+1))
    cs = bs[:]; n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b); cs.append(256+n); n += 1
    return dict(zip(bs, [chr(c) for c in cs]))

class Tok:
    def __init__(self, gguf_path, verbose=True):
        r = GGUFReader(gguf_path)
        self.toks = r.fields["tokenizer.ggml.tokens"].contents()
        try:
            merges = r.fields["tokenizer.ggml.merges"].contents()
        except Exception:
            merges = []
        self.types = None
        try: self.types = list(r.fields["tokenizer.ggml.token_type"].contents())
        except Exception: pass
        self.token2id = {}
        for i, t in enumerate(self.toks):
            if t not in self.token2id: self.token2id[t] = i
        # BPE merges 优先级
        self.bpe_ranks = {}
        for i, m in enumerate(merges):
            parts = m.split(" ")
            if len(parts) == 2:
                self.bpe_ranks[(parts[0], parts[1])] = i
        self.b2u = bytes_to_unicode()
        self.u2b = {v: k for k, v in self.b2u.items()}
        self.special = {"<|im_start|>":151644, "<|im_end|>":151645,
                        "<|endoftext|>":151643, "<|endofprompt|>":151646}
        # GPT2 风格预分词正则(Qwen 用类似)
        self.pat = re.compile(r"""'(?:[sdmt]|ll|ve|re)| ?[^\s\w]+|\s?[\w]+|\s+|\S+""", re.UNICODE)
        if verbose:
            print("词表 %d 条 merges %d 条" % (len(self.toks), len(merges)))

    # ---------- encode ----------
    def _bpe(self, token):
        if not token: return []
        word = tuple(token)
        if len(word) == 1: return list(word)
        while True:
            pairs = [(word[i], word[i+1]) for i in range(len(word)-1)]
            best = None; bi = None
            for p in pairs:
                if p in self.bpe_ranks:
                    r = self.bpe_ranks[p]
                    if best is None or r < best: best = r; bi = p
            if bi is None: break
            a, b = bi; new = []; i = 0
            while i < len(word):
                if i < len(word)-1 and word[i] == a and word[i+1] == b:
                    new.append(a+b); i += 2
                else:
                    new.append(word[i]); i += 1
            word = tuple(new)
            if len(word) == 1: break
        return list(word)

    def encode(self, text, add_special=False):
        ids = []
        # 先切出特殊 token
        pat = re.compile("(" + "|".join(re.escape(k) for k in self.special) + ")")
        for chunk in pat.split(text):
            if not chunk: continue
            if chunk in self.special:
                ids.append(self.special[chunk]); continue
            for piece in self.pat.findall(chunk):
                b = piece.encode("utf-8")
                s = "".join(self.b2u[x] for x in b)
                for sub in self._bpe(s):
                    ids.append(self.token2id.get(sub, 0))
        return ids

    # ---------- decode ----------
    def decode(self, ids):
        out = b""
        for i in ids:
            if i < 0 or i >= len(self.toks): continue
            s = self.toks[i]
            if s in self.special: continue
            for ch in s:
                out += bytes([self.u2b.get(ch, 0)])
        try: return out.decode("utf-8", "ignore")
        except Exception: return out.decode("latin1")
