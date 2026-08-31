import struct, sys, glob
import numpy as np
def peek(path):
    data = open(path, "rb").read()
    off = 0
    magic, k, np_, ng = struct.unpack_from("<IIII", data, off); off += 16
    assert magic == 0x54444344
    prompt = np.frombuffer(data, dtype=np.int32, count=np_, offset=off); off += np_*4
    gen = np.frombuffer(data, dtype=np.int32, count=ng, offset=off); off += ng*4
    top_ids = np.frombuffer(data, dtype=np.uint32, count=ng*k, offset=off); off += ng*k*4
    top_logits = np.frombuffer(data, dtype=np.float32, count=ng*k, offset=off); off += ng*k*4
    pieces = []
    if off < len(data):
        try:
            for j in range(ng):
                (pl,) = struct.unpack_from("<I", data, off); off += 4
                pieces.append(data[off:off+pl].decode("utf-8", "replace")); off += pl
        except Exception as e:
            pieces = []
    return prompt, gen, pieces
for fp in sorted(glob.glob("/root/autodl-tmp/distill_data_full_a/p*.bin"))[:3]:
    prompt, gen, pieces = peek(fp)
    print("FILE", fp, "prompt_tok", len(prompt), "gen_tok", len(gen), "pieces", len(pieces))
    if pieces:
        print("GEN_TEXT:", "".join(pieces)[:400])
        print("---")
