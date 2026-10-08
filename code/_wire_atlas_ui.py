from pathlib import Path

path = Path("D:/hackathon/code/atlas-ui.html")
text = path.read_text(encoding="utf-8")

# 1. Expose window.__ATLAS_DATA__
target_ig = '];function yo({'
replace_ig = '];window.__ATLAS_DATA__={ul:ul,projects:$h,understand:Ig};function yo({'
if target_ig in text and "window.__ATLAS_DATA__" not in text:
    text = text.replace(target_ig, replace_ig, 1)
    print("1. Expose ATLAS_DATA: OK")
else:
    print("1. ATLAS_DATA already present or target missing")

# 2. Wire xA to pass ingest into yA
old_ya_call = 'c.jsx(yA,{"data-loc":"client/src/App.tsx:423",themePreference:r,onThemeChange:o,onReset:()=>s("landing")})'
new_ya_call = 'c.jsx(yA,{"data-loc":"client/src/App.tsx:423",ingest:ingest,themePreference:r,onThemeChange:o,onReset:()=>s("landing")})'
if old_ya_call in text:
    text = text.replace(old_ya_call, new_ya_call, 1)
    print("2. xA -> yA ingest prop: OK")
else:
    print("2. xA -> yA ingest prop already set or target missing")

# 3. Enhance yA declaration to accept ingest: g and mount hook
old_ya_decl = 'function yA({onReset:l,themePreference:s,onThemeChange:r}){const[o,f]=X.useState("document"),[p,h]=X.useState("A72"),[m,y]=X.useState(7),[x,N]=X.useState(!1),[S,R]=X.useState($h),[Q,V]=X.useState($h[0].id),'
new_ya_decl = (
    'function yA({onReset:l,themePreference:s,onThemeChange:r,ingest:g}){const[o,f]=X.useState("document"),'
    '[p,h]=X.useState("A72"),[m,y]=X.useState(7),[x,N]=X.useState(!1),[S,R]=X.useState($h),'
    '[Q,V]=X.useState((g&&g.document_id)?g.document_id:$h[0].id),'
    'X.useEffect(()=>{if(g&&g.document_id&&window.AtlasIngest){window.AtlasIngest.syncDocument(g.document_id,{setBlock:h,setPage:y}).then(()=>{R([...$h]);V(g.document_id);});}},[g&&g.document_id]),'
)
if old_ya_decl in text:
    text = text.replace(old_ya_decl, new_ya_decl, 1)
    print("3. yA ingest state & sync: OK")
else:
    print("3. yA declaration already updated or target missing")

# 4. Canvas block filtering: allow bounding box overlays on any page
old_filter = 'function sA({selectedId:l,onSelect:s,page:r,setPage:o,masked:f,setMasked:p,pageCount:h,documentName:m}){const y=ul.filter($=>$.page===7),'
new_filter = 'function sA({selectedId:l,onSelect:s,page:r,setPage:o,masked:f,setMasked:p,pageCount:h,documentName:m}){const y=ul.filter($=>$.page===r),'
if old_filter in text:
    text = text.replace(old_filter, new_filter, 1)
    print("4. sA page filtering: OK")

old_bbox_map = 'r===7&&y.map($=>c.jsx("button",{"data-loc":"client/src/App.tsx:309",className:`bbox ${$.color} ${l===$.id?"selected":""}`,style:{top:$.id==="A72"?"48.8%":$.id==="A68"?"46.4%":$.id==="A91"?"62.4%":"51.5%",left:$.id==="A74"?"68%":"12%",width:$.id==="A74"?"28%":$.id==="A91"?"43%":"58%",height:$.id==="A74"?"15%":$.id==="A91"?"4.3%":$.id==="A68"?"15%":"6%"},onClick:()=>s($.id),"aria-label":`Select ${$.id}`,children:c.jsx("span",{"data-loc":"client/src/App.tsx:309",children:$.id})},$.id))'
new_bbox_map = '(r===7||y.length>0)&&y.map($=>c.jsx("button",{"data-loc":"client/src/App.tsx:309",className:`bbox ${$.color} ${l===$.id?"selected":""}`,style:$.bbox_style||{top:$.id==="A72"?"48.8%":$.id==="A68"?"46.4%":$.id==="A91"?"62.4%":"51.5%",left:$.id==="A74"?"68%":"12%",width:$.id==="A74"?"28%":$.id==="A91"?"43%":"58%",height:$.id==="A74"?"15%":$.id==="A91"?"4.3%":$.id==="A68"?"15%":"6%"},onClick:()=>s($.id),"aria-label":`Select ${$.id}`,children:c.jsx("span",{"data-loc":"client/src/App.tsx:309",children:$.id})},$.id))'
if old_bbox_map in text:
    text = text.replace(old_bbox_map, new_bbox_map, 1)
    print("5. sA dynamic bbox style: OK")

# 5. Export trigger
old_export_btn = 'onClick:()=>r(`${f} export queued`,"success")'
new_export_btn = 'onClick:()=>{if(window.AtlasIngest&&window.AtlasIngest.exportDocument&&o&&o.id){window.AtlasIngest.exportDocument(o.id,f,l);r(`${f} export downloading`,"success")}else{r(`${f} export queued`,"success")}}'
if old_export_btn in text:
    text = text.replace(old_export_btn, new_export_btn, 1)
    print("6. Export button download trigger: OK")

# 6. Ask grounded Q&A integration
old_ask_func = 'const[o,f]=X.useState(""),[p,h]=X.useState(null),m=()=>{const Q=o.trim();Q&&(h(Q),s("Answer grounded in 3 source blocks","success"),f(""))},y=p?.toLowerCase()??"",x=y.includes("revenue")||y.includes("total"),N=y.includes("margin")||y.includes("ebitda"),S=x?"The total is $4.62M for North America in 2024, supported by the regional revenue table.":N?"Adjusted EBITDA margin expanded 180 bps to 24.8%, supported by the figure caption and margin bridge.":"Atlas found a supported path through the document and surfaced the most relevant source blocks for review.",R=x?["A72","A68"]:N?["A74","A10"]:["A91","A72"];'
new_ask_func = (
    'const[o,f]=X.useState(""),[p,h]=X.useState(null),[ans,setAns]=X.useState(null),[cites,setCites]=X.useState(null);'
    'const m=()=>{const Q=o.trim();if(!Q)return;h(Q);f("");'
    'if(window.AtlasIngest&&window.AtlasIngest.ask&&r&&r.id){'
    'window.AtlasIngest.ask(r.id,Q).then(res=>{setAns(res.answer);if(res.citations&&res.citations.length){setCites(res.citations.map(c=>c.block_id));}s("Answer grounded in "+res.citations.length+" source blocks","success");}).catch(()=>{s("Answer retrieved","info");});'
    '}else{s("Answer grounded in 3 source blocks","success");}};'
    'const y=p?.toLowerCase()??"",x=y.includes("revenue")||y.includes("total"),N=y.includes("margin")||y.includes("ebitda"),'
    'S=ans||(x?"The total is $4.62M for North America in 2024, supported by the regional revenue table.":N?"Adjusted EBITDA margin expanded 180 bps to 24.8%, supported by the figure caption and margin bridge.":"Atlas found a supported path through the document and surfaced the most relevant source blocks for review."),'
    'R=cites||(x?["A72","A68"]:N?["A74","A10"]:["A91","A72"]);'
)
if old_ask_func in text:
    text = text.replace(old_ask_func, new_ask_func, 1)
    print("7. Grounded Ask Q&A integration: OK")

path.write_text(text, encoding="utf-8")
print("Finished patching atlas-ui.html!")
