from pathlib import Path

t = Path("atlas-ui.html").read_text(encoding="utf-8")
needles = [
    "startUpload=file=>",
    "AtlasIngest.upload",
    "function eA({onDone:l,ingest:g})",
    "s(p[0])",
    'accept:".pdf,.png,.jpg,.jpeg,.docx',
]
for needle in needles:
    print(needle, needle in t)
i = t.find("function xA()")
print("xA snippet:\n", t[i : i + 1800])
print("\n---eA---\n")
j = t.find("function eA(")
print(t[j : j + 800])
