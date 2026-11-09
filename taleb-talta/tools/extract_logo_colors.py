from PIL import Image
from collections import Counter
import colorsys, json, os

src = "/home/user/moodle/taleb-talta/docs/logo.png"
im = Image.open(src).convert("RGBA")
# downscale for speed but keep colour fidelity
im2 = im.resize((256,256))
px = list(im2.getdata())
# Keep opaque, non-near-black, non-near-white pixels (the artwork, not the black bg)
def keep(r,g,b,a):
    if a < 200: return False
    mx,mn = max(r,g,b), min(r,g,b)
    if mx < 28: return False          # black background
    if mn > 235: return False         # near-white
    return True
art = [(r,g,b) for (r,g,b,a) in px if keep(r,g,b,a)]
# Quantize the artwork to dominant colours
q = im2.convert("RGB").quantize(colors=24, method=Image.MEDIANCUT)
pal = q.getpalette()
counts = Counter(q.getdata())
# map palette index -> rgb, weight by count, filter bg/white
fam = []
for idx,cnt in counts.most_common():
    r,g,b = pal[idx*3:idx*3+3]
    if not keep(r,g,b,255): continue
    h,s,v = colorsys.rgb_to_hsv(r/255,g/255,b/255)
    fam.append((cnt, (r,g,b), round(h*360), round(s*100), round(v*100)))
print("Total opaque artwork pixels sampled:", len(art))
print("\nDominant saturated colours (weight, hex, H, S%, V%):")
seen=[]
for cnt,(r,g,b),h,s,v in fam:
    hexv="#%02X%02X%02X"%(r,g,b)
    print(f"  {cnt:6d}  {hexv}  H={h:3d} S={s:3d} V={v:3d}")
    seen.append({"hex":hexv,"weight":cnt,"h":h,"s":s,"v":v})
# Bucket into families by hue
def bucket(h,s,v):
    if s<18: return "neutral"
    if 190<=h<=210: return "cyan"
    if 210<h<=250: return "blue"
    if 250<h<=280: return "navy/indigo"
    if 30<=h<=55: return "amber"
    return "other"
buckets={}
for cnt,(r,g,b),h,s,v in fam:
    buckets.setdefault(bucket(h,s,v),[]).append(("#%02X%02X%02X"%(r,g,b),cnt))
print("\nBy family:")
for k,vv in buckets.items():
    vv.sort(key=lambda x:-x[1])
    print(f"  {k:12s}: "+", ".join(f"{h}({c})" for h,c in vv[:4]))
json.dump(seen, open("/home/user/moodle/taleb-talta/docs/logo-colors.json","w"), indent=2)
