import struct
f=open('/workspace/w.gguf','rb')
d=f.read(64)
magic,ver,nt,nk=struct.unpack('<IIQQ',d[:24])
print(f"magic={hex(magic)} ver={ver} tensors={nt} kvs={nk}")
# 读前若干 KV, 找词表
o=24
def rds(o):
    l,=struct.unpack('<Q',d2[o:o+8]); return d2[o+8:o+8+l].decode('utf8','ignore'), o+8+l
import io
d2=f.read(3_000_000)
for i in range(min(nk,8)):
    try:
        kl,=struct.unpack('<Q',d2[o:o+8]); k=d2[o+8:o+8+kl].decode('utf8','ignore'); o+=8+kl
        vt,=struct.unpack('<I',d2[o:o+4]); o+=4
        if vt==8:
            l,=struct.unpack('<Q',d2[o:o+8]); v=d2[o+8:o+8+l].decode('utf8','ignore'); o+=8+l
            print(f"  {k} = {v[:60]}")
        elif vt==9:
            et,=struct.unpack('<I',d2[o:o+4]); n,=struct.unpack('<Q',d2[o+4:o+12]); o+=12
            print(f"  {k} = [数组 type={et} n={n}]"); o+= n*(8 if et==8 else 4) if et!=8 else 0
            if et==8:
                for _ in range(min(n,3)):
                    l,=struct.unpack('<Q',d2[o:o+8]); s=d2[o+8:o+8+l].decode('utf8','ignore'); o+=8+l
                    print(f"      '{s}'")
        else:
            sz={0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}.get(vt,4)
            v,=struct.unpack('<'+( {0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}[vt]), d2[o:o+sz]); o+=sz
            print(f"  {k} = {v}")
    except Exception as e:
        print(f"  (读取停止: {e})"); break
