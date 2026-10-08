"""One-shot patch: wire atlas-ui.html upload/progress to AtlasIngest without replacing the UI."""

from pathlib import Path

path = Path(__file__).resolve().parent / "atlas-ui.html"
text = path.read_text(encoding="utf-8")

old_root = '<div id="root"></div>'
new_root = '<div id="root"></div>\n<script src="/atlas-ingest.js"></script>'
if old_root not in text:
    raise SystemExit("root marker missing")
if "/atlas-ingest.js" not in text:
    text = text.replace(old_root, new_root, 1)

old_accept = 'accept:".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.pptx,.ppt"'
new_accept = 'accept:".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.pptx"'
if old_accept in text:
    text = text.replace(old_accept, new_accept, 1)

old_files = "f=p=>{p?.length&&s()}"
new_files = "f=p=>{p?.length&&s(p[0])}"
if old_files in text:
    text = text.replace(old_files, new_files, 1)

old_ea = (
    "function eA({onDone:l}){const[s,r]=X.useState(0);return X.useEffect(()=>{"
    "const o=window.setInterval(()=>r(p=>Math.min(p+1,Ki.length-1)),420),"
    "f=window.setTimeout(l,3400);return()=>{window.clearInterval(o),window.clearTimeout(f)}},[l]),"
)
new_ea = (
    "function eA({onDone:l,ingest:g}){const demo=!g||g.mode===\"demo\";"
    "const[s,r]=X.useState(0);return X.useEffect(()=>{"
    "if(!demo){r(Math.min(Ki.length-1,Math.floor((((g&&g.progress)||0)/100)*Ki.length)));"
    "if(g&&g.status===\"completed\"){const t=window.setTimeout(l,500);return()=>window.clearTimeout(t)}"
    "return}"
    "const o=window.setInterval(()=>r(p=>Math.min(p+1,Ki.length-1)),420),"
    "f=window.setTimeout(l,3400);return()=>{window.clearInterval(o),window.clearTimeout(f)}},"
    "[l,demo,g&&g.progress,g&&g.status]),"
)
if old_ea not in text:
    if "function eA({onDone:l,ingest:g})" not in text:
        raise SystemExit("eA marker missing")
else:
    text = text.replace(old_ea, new_ea, 1)

old_name = 'c.jsx("b",{"data-loc":"client/src/App.tsx:252",children:"Annual_Report.pdf"})'
new_name = 'c.jsx("b",{"data-loc":"client/src/App.tsx:252",children:(g&&g.filename)||"Annual_Report.pdf"})'
if old_name in text:
    text = text.replace(old_name, new_name, 1)

old_pill = 'c.jsx(Je,{"data-loc":"client/src/App.tsx:252",tone:"cyan",children:"PROCESSING"})'
new_pill = (
    'c.jsx(Je,{"data-loc":"client/src/App.tsx:252",tone:(g&&g.error)?"amber":"cyan",'
    'children:(g&&g.error)?"FAILED":"PROCESSING"})'
)
if old_pill in text:
    text = text.replace(old_pill, new_pill, 1)

old_pct = "Math.min(99,Math.round((s+1)/Ki.length*100))"
new_pct = "(!demo&&g?Math.max(0,Math.min(100,g.progress||0)):Math.min(99,Math.round((s+1)/Ki.length*100)))"
if old_pct in text:
    text = text.replace(old_pct, new_pct, 1)

old_width = "width:`${Math.min(100,(s+1)/Ki.length*100)}%`"
new_width = "width:`${!demo&&g?Math.max(0,Math.min(100,g.progress||0)):Math.min(100,(s+1)/Ki.length*100)}%`"
if old_width in text:
    text = text.replace(old_width, new_width, 1)

old_foot = '" Running deep layout analysis"'
new_foot = '(g&&g.error)?(" "+g.error):" Running deep layout analysis"'
if old_foot in text:
    text = text.replace(old_foot, new_foot, 1)

old_xa = (
    'l==="landing"?c.jsx(tA,{"data-loc":"client/src/App.tsx:423",onDemo:()=>s("processing"),'
    'onUpload:()=>s("processing")}):l==="processing"?c.jsx(eA,{"data-loc":"client/src/App.tsx:423",'
    'onDone:()=>s("workspace")}):'
)
new_xa = (
    'const[ingest,setIngest]=X.useState(null);'
    'const startDemo=()=>{setIngest({mode:"demo",filename:"Annual_Report.pdf"});s("processing")};'
    'const startUpload=file=>{'
    'if(!file)return;'
    'if(!window.AtlasIngest){s("processing");return}'
    'setIngest({mode:"live",filename:file.name,progress:5,status:"queued",stage:"uploading"});'
    's("processing");'
    'window.AtlasIngest.upload(file).then(accepted=>{'
    'setIngest(prev=>({...(prev||{}),document_id:accepted.document_id,job_id:accepted.job_id,status:accepted.status,stage:"queued"}));'
    'return window.AtlasIngest.pollJob(accepted.job_id,job=>{'
    'setIngest(prev=>({...(prev||{}),mode:"live",filename:file.name,progress:job.progress,status:job.status,stage:job.stage,'
    'error:job.error_code?(job.error_code+": "+(job.error_message||"")):null}))})'
    '}).then(()=>{}).catch(err=>{'
    'setIngest(prev=>({...(prev||{}),mode:"live",filename:file.name,status:"failed",progress:100,error:err.message||String(err)}))'
    '})};'
    'return X.useEffect(()=>{window.localStorage.setItem("atlas-theme",r);const f=window.matchMedia("(prefers-color-scheme: light)"),p=()=>{document.documentElement.dataset.theme=r==="light"||r==="system"&&f.matches?"light":"dark"};return p(),f.addEventListener?.("change",p),()=>f.removeEventListener?.("change",p)},[r]),'
    'l==="landing"?c.jsx(tA,{"data-loc":"client/src/App.tsx:423",onDemo:startDemo,onUpload:startUpload}):'
    'l==="processing"?c.jsx(eA,{"data-loc":"client/src/App.tsx:423",ingest:ingest,'
    'onDone:()=>{if(ingest&&ingest.error)return;s("workspace")}}):'
)

# Original xA uses `return X.useEffect(...)` after the two useStates.
old_xa_full = (
    "function xA(){const[l,s]=X.useState(\"landing\"),[r,o]=X.useState(()=>{const f=window.localStorage.getItem(\"atlas-theme\");"
    "return f===\"light\"||f===\"system\"||f===\"dark\"?f:\"system\"});return X.useEffect(()=>{window.localStorage.setItem(\"atlas-theme\",r);"
    "const f=window.matchMedia(\"(prefers-color-scheme: light)\"),p=()=>{document.documentElement.dataset.theme=r===\"light\"||r===\"system\"&&f.matches?\"light\":\"dark\"};"
    "return p(),f.addEventListener?.(\"change\",p),()=>f.removeEventListener?.(\"change\",p)},[r]),"
    + old_xa
)
new_xa_full = (
    "function xA(){const[l,s]=X.useState(\"landing\"),[r,o]=X.useState(()=>{const f=window.localStorage.getItem(\"atlas-theme\");"
    "return f===\"light\"||f===\"system\"||f===\"dark\"?f:\"system\"});"
    + new_xa
)

if old_xa_full in text:
    text = text.replace(old_xa_full, new_xa_full, 1)
elif "startUpload=file=>" not in text:
    raise SystemExit("xA marker missing")

path.write_text(text, encoding="utf-8")
print("patched atlas-ui.html")
