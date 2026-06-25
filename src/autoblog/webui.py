"""글쓰기 유저 화면 — 로컬 웹(표준 http.server, npm/node 0).

스티커 검수에서 검증한 "로컬 서버 + 브라우저" 패턴을 앱 전체로 확장한 유저 화면.
탭: 글쓰기(메모/수집/사진/서식 → 생성 → 미리보기 → 임시저장) · 스티커(즐겨찾기 보기) · 설정(글쓰기 규칙).
`autoblog ui` 한 줄이 서버 기동 + 브라우저 자동 오픈. 최종 유저용은 이후 PyInstaller 더블클릭 앱.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from autoblog.config import REPO_ROOT

PHOTO_DIR = REPO_ROOT / "test"  # 유저 사진 폴더(테스트용)
_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
FONTS_DIR = REPO_ROOT / "config" / "fonts"  # 에디터 웹폰트(로컬 서빙, 미리보기용)
# 미리보기에서 실제 글씨체로 보이게 — 에디터와 같은 se-* 패밀리명 사용
_FONT_FAMILIES = [
    "nanumgothic", "nanummyeongjo", "nanumbarungothic", "nanumsquare",
    "nanummaruburi", "nanumdasisijaghae", "nanumbareunhipi", "nanumuriddalsongeulssi",
]


def _font_face_css() -> str:
    return "\n".join(
        f"@font-face{{font-family:'se-{f}';src:url('/font?name=se-{f}') format('woff2');font-display:swap}}"
        for f in _FONT_FAMILIES
    )

_PAGE = r"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>블로그 자동작성</title><style>
 /*FONTFACES*/
 :root{--green:#03c75a;--green-d:#02b350;--ink:#1f2329;--sub:#8b95a1;--line:#e8eaed;--bg:#f2f4f6}
 *{box-sizing:border-box}
 body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Pretendard',sans-serif;
   background:var(--bg);color:var(--ink);display:flex;height:100vh;overflow:hidden}
 /* sidebar */
 .side{width:212px;flex:0 0 212px;background:#fff;border-right:1px solid var(--line);padding:18px 12px;display:flex;flex-direction:column;gap:4px}
 .brand{font-size:15px;font-weight:800;padding:8px 10px 16px;display:flex;align-items:center;gap:8px}
 .nav{display:flex;align-items:center;gap:10px;padding:11px 12px;border-radius:10px;cursor:pointer;color:#4b5563;font-size:14px;font-weight:600}
 .nav:hover{background:#f6f8fa}
 .nav.on{background:#eafaf0;color:var(--green-d)}
 .nav .ic{font-size:16px;width:20px;text-align:center}
 .side .foot{margin-top:auto;font-size:11px;color:var(--sub);padding:8px 10px;line-height:1.6}
 /* main */
 main{flex:1;overflow:auto;padding:26px 30px}
 .view{display:none}.view.on{display:block}
 h2.title{font-size:20px;margin:0 0 4px}
 .desc{color:var(--sub);font-size:13px;margin:0 0 20px}
 /* write layout */
 .grid{display:grid;grid-template-columns:minmax(360px,460px) 1fr;gap:22px;align-items:start}
 .card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px}
 .card h3{font-size:13px;margin:0 0 12px;color:#374151}
 label.f{display:block;font-size:12px;color:#6b7280;margin:14px 0 6px;font-weight:600}
 label.f:first-child{margin-top:0}
 input[type=text],textarea{width:100%;border:1px solid #d6dade;border-radius:10px;padding:10px 12px;font-size:13px;font-family:inherit;background:#fbfcfd}
 input[type=text]:focus,textarea:focus{outline:2px solid #03c75a33;border-color:var(--green)}
 textarea{min-height:130px;resize:vertical;line-height:1.6}
 .seg{display:flex;gap:6px}
 .seg button{flex:1;padding:9px;font-size:12px;background:#fff;color:#6b7280;border:1px solid #d6dade;border-radius:9px;cursor:pointer;font-weight:600}
 .seg button.on{background:#eafaf0;color:var(--green-d);border-color:var(--green)}
 .chips{display:flex;flex-wrap:wrap;gap:8px}
 .chip{display:inline-flex;align-items:center;gap:7px;padding:8px 12px;border:1px solid #d6dade;border-radius:999px;font-size:12.5px;cursor:pointer;background:#fff;user-select:none}
 .chip.on{background:var(--green);color:#fff;border-color:var(--green)}
 .chip .dot{width:7px;height:7px;border-radius:50%;background:#cbd2d9}
 .chip.on .dot{background:#fff}
 .btn{display:block;width:100%;padding:13px;border:none;border-radius:12px;background:var(--green);color:#fff;font-size:14.5px;font-weight:700;cursor:pointer}
 .btn:hover{background:var(--green-d)}
 .btn:disabled{opacity:.45;cursor:default}
 .btn.ghost{background:#fff;color:var(--ink);border:1px solid #d6dade;font-weight:600}
 #status{font-size:12.5px;color:var(--sub);min-height:18px;margin-top:6px;display:flex;align-items:center;gap:8px}
 .spin{width:13px;height:13px;border:2px solid #d6dade;border-top-color:var(--green);border-radius:50%;animation:sp .7s linear infinite;display:none}
 @keyframes sp{to{transform:rotate(360deg)}}
 .loading .spin{display:inline-block}
 /* photo grid */
 .pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(76px,1fr));gap:8px;max-height:230px;overflow:auto;padding:2px}
 .pcell{position:relative;aspect-ratio:1;border-radius:9px;overflow:hidden;cursor:pointer;border:2px solid transparent}
 .pcell img{width:100%;height:100%;object-fit:cover;display:block}
 .pcell.sel{border-color:var(--green)}
 .pcell .num{position:absolute;top:4px;left:4px;background:var(--green);color:#fff;width:18px;height:18px;border-radius:50%;font-size:11px;display:none;align-items:center;justify-content:center;font-weight:700}
 .pcell.sel .num{display:flex}
 /* preview */
 .doc{background:#fff;border:1px solid var(--line);border-radius:16px;padding:30px 34px;min-height:300px}
 .doc.empty{display:flex;align-items:center;justify-content:center;color:#b0b8c1;font-size:14px;min-height:420px}
 .doc h1{font-size:23px;margin:0 0 20px;line-height:1.4}
 .doc .tx{font-size:15px;line-height:2;white-space:pre-wrap;margin:0 0 6px}
 .doc hr{border:none;border-top:1px solid #e3e6ea;margin:22px 36px}
 .doc .q{border-left:3px solid var(--green);padding:8px 0 8px 18px;color:#3a4250;font-size:16.5px;margin:18px 0;font-style:italic}
 .doc img.st{width:148px;height:148px;object-fit:contain;display:block;margin:10px 0}
 .doc .ph{background:#eef6ff;border:1px dashed #9ec5ff;border-radius:10px;padding:14px;color:#2f6fd6;font-size:13px;margin:10px 0}
 em.hl{font-style:normal;border-radius:3px;padding:1px 3px}
 /* sticker / settings */
 .stgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:12px;margin-bottom:8px}
 .stcard{position:relative;background:#fff;border:1px solid var(--line);border-radius:14px;padding:10px;text-align:center}
 .stcard img{width:100%;aspect-ratio:1;object-fit:contain;background:#fafbfc;border-radius:9px}
 .stcard .tg{font-size:11px;color:var(--sub);margin-top:6px;line-height:1.4;min-height:28px}
 .favbtn{position:absolute;top:6px;right:6px;width:26px;height:26px;border-radius:50%;border:1px solid var(--line);
   background:#fff;color:#cbd2d9;font-size:15px;cursor:pointer;line-height:1;padding:0;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 3px #0001}
 .favbtn.on{color:#ffb400;border-color:#ffe2a6;background:#fffaf0}
 .packh{font-size:13px;color:#4b5563;font-weight:700;margin:18px 0 10px}
 .packh small{color:var(--sub);font-weight:500}
 .stat{display:flex;gap:18px;margin-bottom:18px}
 .stat .b{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 18px}
 .stat .b .n{font-size:22px;font-weight:800;color:var(--green-d)}
 .stat .b .l{font-size:12px;color:var(--sub)}
 .setrow{display:flex;justify-content:space-between;align-items:center;padding:16px 4px;border-bottom:1px solid var(--line)}
 .setrow:last-child{border:none}
 .setrow .t{font-size:14px;font-weight:600}.setrow .d{font-size:12px;color:var(--sub);margin-top:3px;max-width:520px}
 .sw{width:44px;height:26px;border-radius:999px;background:#cdd3da;position:relative;cursor:pointer;flex:0 0 44px;transition:.15s}
 .sw.on{background:var(--green)}
 .sw::after{content:"";position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:.15s}
 .sw.on::after{left:21px}
 .muted{color:var(--sub);font-size:12.5px}
 .vgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px;margin-bottom:8px}
 .vcell{border:2px solid var(--line);border-radius:12px;padding:13px 15px;cursor:pointer;background:#fff}
 .vcell.on{border-color:var(--green);background:#f3fcf6}
 .vcell .vinfo{margin-bottom:8px}
 .vcell .vname{font-size:13.5px;font-weight:700;display:flex;align-items:center;gap:6px}
 .vcell .vck{color:var(--green-d)}
 .vcell .vdesc{font-size:11.5px;color:var(--sub);margin-top:2px;line-height:1.4}
 .vcell img{width:100%;height:auto;max-height:38px;object-fit:contain;object-position:left}
 .vcell.q img{max-height:140px;object-position:center}
 .epgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
 .epcell{border:1px solid var(--line);border-radius:10px;padding:9px 10px;background:#fff}
 .epnum{font-size:11px;color:var(--sub);font-weight:600;margin-bottom:6px;display:flex;align-items:center}
 .epcell .sw-chip{display:inline-block;font-size:14px}
 .epmeta{font-size:11px;color:var(--sub);margin-top:5px}
 .swrap{display:flex;flex-wrap:wrap;gap:9px;align-items:center}
 .sw-chip{padding:8px 14px;border-radius:9px;font-size:14px;font-weight:600;border:1px solid var(--line);background:#fff}
 .sw-chip .pid{font-size:10px;opacity:.55;margin-left:6px;font-weight:500}
 .sub-h{font-size:12px;color:#6b7280;font-weight:700;margin:16px 0 9px}.sub-h:first-child{margin-top:4px}
 .promptbox details{border-top:1px solid var(--line);padding:4px 0}.promptbox details:first-child{border:none}
 .promptbox summary{cursor:pointer;font-size:13px;font-weight:600;padding:8px 0}
 .promptbox pre{background:#f6f8fa;border:1px solid var(--line);border-radius:10px;padding:14px;font-size:12px;line-height:1.65;white-space:pre-wrap;max-height:320px;overflow:auto;font-family:ui-monospace,Menlo,monospace;margin:4px 0 10px}
</style></head><body>
<aside class=side>
  <div class=brand>🖋️ 블로그 자동작성</div>
  <div class="nav on" data-view=write><span class=ic>✍️</span> 글쓰기</div>
  <div class=nav data-view=stickers><span class=ic>😊</span> 스티커</div>
  <div class=nav data-view=settings><span class=ic>⚙️</span> 설정</div>
  <div class=foot>로컬에서 동작 · 네이버 임시저장</div>
</aside>
<main>
  <!-- 글쓰기 -->
  <section class="view write on">
    <h2 class=title>글쓰기</h2>
    <p class=desc>경험 메모와 사진을 넣고 [초안 생성]을 누르면 오른쪽에 미리보기가 나옵니다.</p>
    <div class=grid>
      <div class=col>
        <div class=card>
          <label class=f>수집 (선택)</label>
          <div class=seg id=seg>
            <button data-src=none class=on>없음</button>
            <button data-src=place>맛집 URL</button>
            <button data-src=product>상품 검색</button>
          </div>
          <input type=text id=srcval placeholder="플레이스 URL 또는 상품 검색어" style="display:none;margin-top:8px">
          <label class=f>경험 메모 <span class=muted>(글의 중심)</span></label>
          <textarea id=memo placeholder="예: 비 오는 날 들렀는데 따뜻한 우동이 정말 맛있었어요. 사장님도 친절하셨고 분위기도 아늑했어요."></textarea>
          <label class=f>사진 <span class=muted id=psel></span></label>
          <div class=pgrid id=pgrid><div class=muted>불러오는 중…</div></div>
          <label class=f>문체 톤 (선택)</label>
          <input type=text id=tone placeholder="예: 친근한 반말로">
          <label class=f>자동 서식</label>
          <div class=chips id=fmt>
            <span class="chip on" data-k=emphasis><span class=dot></span>강조색</span>
            <span class="chip on" data-k=structure><span class=dot></span>구분선·인용구</span>
            <span class="chip on" data-k=stickers><span class=dot></span>스티커</span>
          </div>
          <div style="margin-top:18px"><button class=btn id=gen>초안 생성</button></div>
          <div id=status></div>
        </div>
        <div class=card style="margin-top:16px">
          <h3>네이버에 보내기</h3>
          <label class=f>발행 카테고리 (선택)</label>
          <input type=text id=category placeholder="카테고리 이름">
          <div style="margin-top:12px"><button class="btn ghost" id=save disabled>임시저장</button></div>
        </div>
      </div>
      <div class=col>
        <div class="doc empty" id=preview>왼쪽에서 메모를 쓰고 [초안 생성]을 누르세요.</div>
      </div>
    </div>
  </section>
  <!-- 스티커 -->
  <section class="view stickers">
    <h2 class=title>스티커</h2>
    <p class=desc>★를 눌러 즐겨찾기에 넣으세요. <b>즐겨찾기한 스티커만</b> 글에 쓰입니다.</p>
    <div class=stat id=ststat></div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap">
      <div class=seg style="width:280px" id=stfilter>
        <button data-f=fav class=on>⭐ 즐겨찾기</button>
        <button data-f=all>전체 둘러보기</button>
      </div>
      <button class="btn ghost" id=lblbtn style="width:auto;padding:9px 14px">🔍 즐겨찾기 태그 분석</button>
      <span class=muted id=lblstat></span>
    </div>
    <div id=stbody><div class=muted>불러오는 중…</div></div>
  </section>
  <!-- 설정 -->
  <section class="view settings">
    <h2 class=title>설정</h2>
    <p class=desc>글쓰기 규칙을 켜고 끄면 다음 생성부터 반영됩니다.</p>
    <div class=card id=rules></div>
    <div class=card style="margin-top:16px"><h3>🎨 강조색 미리보기 <span class=muted style="font-weight:400">— 핵심 문장에 번갈아 적용</span></h3><div id=emph><div class=muted>불러오는 중…</div></div></div>
    <div class=card style="margin-top:16px"><h3>➖ 구분선·인용구 종류 <span class=muted style="font-weight:400">— 글에 들어갈 기본 모양</span></h3><div id=variants><div class=muted>불러오는 중…</div></div></div>
    <div class=card style="margin-top:16px"><h3>📝 초안 생성 프롬프트 <span class=muted style="font-weight:400">— config/prompts/default.md + 마커 레이어</span></h3><div id=prompt><div class=muted>불러오는 중…</div></div></div>
    <div class=card style="margin-top:16px" id=models><h3>모델</h3><div class=muted>불러오는 중…</div></div>
  </section>
</main>
<script>
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let SRC='none', PHOTOS=[], SELP=[], PLAN=null;
const FMT={emphasis:true,structure:true,stickers:true};
const RULES={mobile_friendly:true,authenticity:true,structure_guide:true,seo:false,emoji:false};
const RULE_META=[
 ['mobile_friendly','모바일 친화','문단을 2~3줄로 짧게, 여백 넉넉히(네이버 트래픽 대부분 모바일)'],
 ['authenticity','진정성','과장·상투구·AI식 표현 피하고 솔직·담백하게(단점도 자연스럽게)'],
 ['structure_guide','구조 가이드','방문/구매 동기 → 경험 → 평가 흐름, 소제목으로 구간 나누기'],
 ['seo','검색 노출(SEO)','지역명·업종 키워드를 제목·본문에 자연스럽게(과도 반복은 저품질)'],
 ['emoji','이모지','분위기에 맞는 이모지 적절히 사용'],
];

// nav
$$('.nav').forEach(n=>n.onclick=()=>{
  $$('.nav').forEach(x=>x.classList.remove('on')); n.classList.add('on');
  $$('.view').forEach(v=>v.classList.remove('on')); $('.view.'+n.dataset.view).classList.add('on');
  if(n.dataset.view==='stickers') loadStickers();
});
// 수집 세그먼트
$('#seg').onclick=e=>{const b=e.target.closest('button'); if(!b)return;
  $$('#seg button').forEach(x=>x.classList.remove('on')); b.classList.add('on'); SRC=b.dataset.src;
  $('#srcval').style.display=SRC==='none'?'none':'block';};
// 서식 칩
$('#fmt').onclick=e=>{const c=e.target.closest('.chip'); if(!c)return;
  c.classList.toggle('on'); FMT[c.dataset.k]=c.classList.contains('on');};

function st(m,loading){const s=$('#status'); s.innerHTML=(loading?'<span class=spin></span>':'')+m;
  s.parentElement.classList.toggle('loading',!!loading);}

// 사진 로드
async function loadPhotos(){
  try{const ps=await (await fetch('/api/photos')).json(); PHOTOS=ps;
    const g=$('#pgrid'); g.innerHTML='';
    if(!ps.length){g.innerHTML='<div class=muted>test/ 폴더에 사진이 없어요.</div>';return;}
    ps.forEach(p=>{const d=document.createElement('div'); d.className='pcell';
      d.innerHTML=`<img loading=lazy src="/photo?path=${encodeURIComponent(p.path)}"><span class=num></span>`;
      d.onclick=()=>toggleP(p.path,d); g.appendChild(d);});
  }catch(e){$('#pgrid').innerHTML='<div class=muted>사진 로드 실패</div>';}
}
function toggleP(path,el){const i=SELP.indexOf(path);
  if(i>=0){SELP.splice(i,1);el.classList.remove('sel');} else {SELP.push(path);el.classList.add('sel');}
  // 번호 갱신
  $$('.pcell').forEach(c=>{}); SELP.forEach((p,idx)=>{});
  $$('#pgrid .pcell').forEach(c=>{const img=c.querySelector('img'); const pp=decodeURIComponent(img.src.split('path=')[1]);
    const n=c.querySelector('.num'); const k=SELP.indexOf(pp); n.textContent=k>=0?k+1:'';});
  $('#psel').textContent=SELP.length?`${SELP.length}장 선택`:'';
}

$('#gen').onclick=async()=>{
  if(!$('#memo').value.trim()){st('경험 메모를 입력하세요.');return;}
  $('#gen').disabled=true;$('#save').disabled=true; st('수집 + 초안 생성 중… (수십 초)',true);
  try{
    const body={memo:$('#memo').value,src:SRC,srcval:$('#srcval').value,photos:SELP,tone:$('#tone').value,
      emphasis:FMT.emphasis,structure:FMT.structure,stickers:FMT.stickers,rules:RULES};
    const r=await fetch('/api/generate',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok){st('실패: '+(d.error||''));return;}
    PLAN=d; renderPreview(d); st('생성 완료. 검토 후 임시저장하세요.'); $('#save').disabled=false;
  }catch(e){st('오류: '+e);}finally{$('#gen').disabled=false;}
};
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function renderText(b){let h=esc(b.text);
  (b.emphases||[]).forEach(e=>{const stl=(e.text_color?`color:${e.text_color};`:'')+(e.background_color?`background:${e.background_color};`:'');
    h=h.replace(esc(e.text),`<em class=hl style="${stl}">${esc(e.text)}</em>`);});
  return `<p class=tx>${h}</p>`;}
function renderPreview(d){
  let h=`<h1>${esc(d.title)||'(제목 없음)'}</h1>`;
  for(const b of d.blocks){
    if(b.kind==='text')h+=renderText(b);
    else if(b.kind==='divider')h+='<hr>';
    else if(b.kind==='quote')h+=`<div class=q>${esc(b.text)}</div>`;
    else if(b.kind==='sticker')h+=`<img class=st src="/img?ref=${encodeURIComponent(b.sticker_ref)}">`;
    else if(b.kind==='image')h+=`<div class=ph>🖼 ${esc(b.image_label)} <small>${esc(b.image_path)}</small></div>`;
  }
  const p=$('#preview'); p.classList.remove('empty'); p.innerHTML=h;
}
$('#save').onclick=async()=>{if(!PLAN)return;
  $('#save').disabled=true; st('네이버 에디터에 주입 중… 브라우저가 열립니다',true);
  try{const r=await fetch('/api/publish',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({category:$('#category').value})});
    const d=await r.json(); st(r.ok?'임시저장 완료 ✓ (네이버 글쓰기 › 저장 목록)':'실패: '+(d.error||''));
  }catch(e){st('오류: '+e);}finally{$('#save').disabled=false;}
};

// 스티커 탭
let CAT=null, ST_FILTER='fav';
async function loadStickers(force){
  if(CAT && !force){renderStickers();return;}
  try{CAT=await (await fetch('/api/catalog')).json(); renderStickers();}
  catch(e){$('#stbody').innerHTML='<div class=muted>스티커 로드 실패</div>';}
}
function updateStat(){if(!CAT)return;
  $('#ststat').innerHTML=`<div class=b><div class=n>${CAT.total}</div><div class=l>전체</div></div>
    <div class=b><div class=n>${CAT.favorites.length}</div><div class=l>⭐ 즐겨찾기</div></div>
    <div class=b><div class=n>${CAT.label_count}</div><div class=l>상황 라벨</div></div>`;}
function renderStickers(){
  updateStat();
  const favset=new Set(CAT.favorites);
  let list=CAT.stickers;
  if(ST_FILTER==='fav') list=list.filter(s=>favset.has(s.ref));
  const body=$('#stbody');
  if(!list.length){body.innerHTML=`<div class=muted>${ST_FILTER==='fav'?'아직 즐겨찾기가 없어요. [전체 둘러보기]에서 ★를 눌러 추가하세요.':'스티커가 없어요. 터미널에서 autoblog stickers pull'}</div>`;return;}
  const packs={};
  list.forEach(s=>{(packs[s.pack]=packs[s.pack]||[]).push(s);});
  let h='';
  for(const pack of Object.keys(packs)){
    h+=`<div class=packh>${pack} <small>(${packs[pack].length})</small></div><div class=stgrid>`;
    for(const s of packs[pack]){const on=favset.has(s.ref);
      h+=`<div class=stcard><button class="favbtn${on?' on':''}" data-ref="${s.ref}" title="즐겨찾기">★</button>
        <img loading=lazy src="/img?ref=${encodeURIComponent(s.ref)}">
        <div class=tg>${(s.tags||[]).slice(0,3).join(', ')||'—'}</div></div>`;}
    h+='</div>';
  }
  body.innerHTML=h;
}
$('#stfilter').onclick=e=>{const b=e.target.closest('button'); if(!b)return;
  $$('#stfilter button').forEach(x=>x.classList.remove('on')); b.classList.add('on');
  ST_FILTER=b.dataset.f; renderStickers();};
// 태그 분석(즐겨찾기만, 백그라운드 진행)
$('#lblbtn').onclick=async()=>{
  $('#lblbtn').disabled=true; $('#lblstat').textContent='시작 중…';
  try{
    const d=await (await fetch('/api/label',{method:'POST'})).json();
    if(!d.total){$('#lblstat').textContent='분석할 새 즐겨찾기가 없어요(이미 태그 있음).'; $('#lblbtn').disabled=false; return;}
    pollLabel();
  }catch(e){$('#lblstat').textContent='오류: '+e; $('#lblbtn').disabled=false;}
};
async function pollLabel(){
  const s=await (await fetch('/api/label/status')).json();
  $('#lblstat').textContent=`분석 중… ${s.done}/${s.total} (스티커당 수 초)`;
  if(s.running){setTimeout(pollLabel,1500);}
  else{$('#lblstat').textContent=`완료 ✓ 태그 ${s.done}개 분석`; $('#lblbtn').disabled=false; await loadStickers(true);}
}
$('#stbody').onclick=async e=>{const b=e.target.closest('.favbtn'); if(!b)return;
  const ref=b.dataset.ref, on=!b.classList.contains('on');
  b.classList.toggle('on',on);
  CAT.favorites=CAT.favorites.filter(r=>r!==ref); if(on)CAT.favorites.push(ref);
  updateStat();
  if(ST_FILTER==='fav' && !on) b.closest('.stcard').remove();  // 즐겨찾기 보기에선 해제 시 사라짐
  try{await fetch('/api/favorite',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({ref,on})});}
  catch(e){}
};

// 설정
function renderRules(){const c=$('#rules'); c.innerHTML='';
  RULE_META.forEach(([k,t,d])=>{const row=document.createElement('div'); row.className='setrow';
    row.innerHTML=`<div><div class=t>${t}</div><div class=d>${d}</div></div><div class="sw ${RULES[k]?'on':''}"></div>`;
    row.querySelector('.sw').onclick=function(){RULES[k]=!RULES[k]; this.classList.toggle('on',RULES[k]);};
    c.appendChild(row);});
}
async function loadModels(){try{const m=await (await fetch('/api/models')).json();
  $('#models').innerHTML=`<h3>모델</h3><div class=setrow><div class=t>텍스트</div><div class=muted>${m.text}</div></div>
    <div class=setrow><div class=t>비전</div><div class=muted>${m.vision}</div></div>`;
}catch(e){}}

async function loadEmphasis(){try{const e=await (await fetch('/api/emphasis')).json();
  const tag=u=>u?`<span style="font-size:10px;background:#eafaf0;color:#02b350;border-radius:4px;padding:1px 5px;margin-left:5px">${u==='순환'?'순환':u}</span>`:'';
  const card=s=>{
    const hasStyle=s.text_color||s.background_color||s.font;
    const stl=hasStyle?((s.text_color?`color:${s.text_color};`:'')+(s.background_color?`background:${s.background_color};`:'')+(s.bold?'font-weight:800;':'')+(s.font?`font-family:'se-${s.font}';`:'')+(s.size?`font-size:${s.size}px;`:'')):'color:#9aa5b1';
    const meta=[s.font_name,s.size?s.size+'pt':''].filter(Boolean).join(' · ');
    return `<div class=epcell><div class=epnum>#${s.id}${tag(s.use)}</div>
      <span class="sw-chip" style="${stl}">${hasStyle?'강조 텍스트':'(서식 없음)'}</span>
      ${meta?`<div class=epmeta>${meta}</div>`:'<div class=epmeta>&nbsp;</div>'}</div>`;};
  let h=`<div class=muted style="margin-bottom:10px">출처: <b>${e.source}</b> · 순환 풀 [${e.cycling.join(', ')}] · 고정 ${Object.entries(e.fixed).map(([k,v])=>k+'→#'+v).join(', ')||'없음'}</div>`;
  h+='<div class=epgrid>'+e.all.map(card).join('')+'</div>';
  $('#emph').innerHTML=h;
}catch(e){$('#emph').innerHTML='<div class=muted>로드 실패</div>';}}
async function loadPrompt(){try{const p=await (await fetch('/api/prompt')).json();
  let h='<div class=promptbox><details open><summary>베이스 프롬프트 (역할·포맷 규칙)</summary><pre>'+esc(p.base)+'</pre></details>';
  p.layers.forEach(([t,b])=>{h+=`<details><summary>${esc(t)}</summary><pre>${esc(b)}</pre></details>`;});
  $('#prompt').innerHTML=h+'</div>';
}catch(e){$('#prompt').innerHTML='<div class=muted>로드 실패</div>';}}
async function loadVariants(){try{const f=await (await fetch('/api/format')).json();
  const row=(items,type,qcls)=>{
    if(!items.length)return '<div class=muted>캡쳐된 종류가 없어요</div>';
    return '<div class=vgrid>'+items.map(it=>`<div class="vcell ${qcls}${it.enabled?' on':''}" data-type=${type} data-value="${it.value}">
      <div class=vinfo><div class=vname>${it.name} ${it.enabled?'<span class=vck>✓</span>':''}</div><div class=vdesc>${it.desc}</div></div>
      <img loading=lazy src="/variant-img?type=${type}&value=${encodeURIComponent(it.value)}"></div>`).join('')+'</div>';};
  $('#variants').innerHTML='<div class=muted style="margin-bottom:8px">쓰고 싶은 종류를 여러 개 골라두세요. 글 생성 때 그 중에서 쓰입니다.</div>'
    +'<div class=sub-h>구분선</div>'+row(f.dividers,'divider','')
    +'<div class=sub-h>인용구</div>'+row(f.quotes,'quote','q');
}catch(e){$('#variants').innerHTML='<div class=muted>로드 실패</div>';}}
$('#variants').onclick=async e=>{const c=e.target.closest('.vcell'); if(!c)return;
  const type=c.dataset.type, value=c.dataset.value, on=!c.classList.contains('on');
  c.classList.toggle('on',on);
  c.querySelector('.vname').innerHTML=c.querySelector('.vname').textContent.replace(' ✓','')+(on?' <span class=vck>✓</span>':'');
  try{await fetch('/api/format',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({type,value,on})});}catch(e){}
};
loadPhotos(); renderRules(); loadModels(); loadEmphasis(); loadPrompt(); loadVariants();
</script></body></html>"""


def _thumb(path: Path, cache: dict, size: int = 320) -> bytes | None:
    key = str(path)
    if key in cache:
        return cache[key]
    try:
        from PIL import Image

        im = Image.open(path)
        im.thumbnail((size, size))
        im = im.convert("RGB")
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=80)
        cache[key] = buf.getvalue()
        return cache[key]
    except Exception:
        return None


def _list_photos() -> list[dict]:
    if not PHOTO_DIR.exists():
        return []
    out = []
    for p in sorted(PHOTO_DIR.iterdir()):
        if p.is_file() and p.suffix.lower() in _IMG_EXT:
            out.append({"path": str(p), "name": p.name})
    return out


def _safe_photo(path: str) -> Path | None:
    p = Path(path).resolve()
    try:
        p.relative_to(PHOTO_DIR.resolve())
    except ValueError:
        return None
    return p if p.exists() else None


def _make_handler(state: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json_body(self):
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/":
                html = _PAGE.replace("/*FONTFACES*/", _font_face_css())
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            elif u.path == "/font":
                name = Path(q.get("name", [""])[0]).name  # 경로 차단
                fp = FONTS_DIR / f"{name}.woff2"
                if fp.exists() and fp.parent == FONTS_DIR:
                    self._send(200, fp.read_bytes(), "font/woff2")
                else:
                    self._send(404, b"x", "text/plain")
            elif u.path == "/api/photos":
                self._send(200, json.dumps(_list_photos()).encode())
            elif u.path == "/photo":
                p = _safe_photo(q.get("path", [""])[0])
                img = _thumb(p, state["thumbs"]) if p else None
                self._send(200, img, "image/jpeg") if img else self._send(404, b"x", "text/plain")
            elif u.path == "/img":
                img = _sticker_image(q.get("ref", [""])[0])
                self._send(200, img.read_bytes(), "image/png") if (img and img.exists()) else self._send(404, b"x", "text/plain")
            elif u.path == "/api/catalog":
                self._send(200, json.dumps(_catalog_summary()).encode())
            elif u.path == "/api/label/status":
                self._send(200, json.dumps(state["label"]).encode())
            elif u.path == "/api/models":
                from autoblog.config import load_models_config

                m = load_models_config().get()
                self._send(200, json.dumps({"text": m.text, "vision": m.vision}).encode())
            elif u.path == "/variant-img":
                typ = Path(q.get("type", [""])[0]).name
                val = Path(q.get("value", [""])[0]).name
                fp = PREVIEW_DIR / f"{typ}_{val}.png"
                if fp.exists() and fp.parent == PREVIEW_DIR:
                    self._send(200, fp.read_bytes(), "image/png")
                else:
                    self._send(404, b"x", "text/plain")
            elif u.path == "/api/format":
                self._send(200, json.dumps(_format_summary()).encode())
            elif u.path == "/api/emphasis":
                self._send(200, json.dumps(_emphasis_preview()).encode())
            elif u.path == "/api/prompt":
                self._send(200, json.dumps(_prompt_preview()).encode())
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                if path == "/api/generate":
                    self._generate(self._json_body())
                elif path == "/api/publish":
                    self._publish(self._json_body())
                elif path == "/api/favorite":
                    body = self._json_body()
                    n = _toggle_favorite(body.get("ref", ""), bool(body.get("on")))
                    self._send(200, json.dumps({"ok": True, "favorites": n}).encode())
                elif path == "/api/format":
                    import yaml

                    body = self._json_body()
                    cfg = _load_format()
                    key = "divider_enabled" if body.get("type") == "divider" else "quote_enabled"
                    lst = list(cfg.get(key) or ["default"])
                    value, on = body.get("value"), bool(body.get("on"))
                    if on and value not in lst:
                        lst.append(value)
                    elif not on and value in lst:
                        lst.remove(value)
                    cfg[key] = lst or ["default"]  # 최소 1개 유지
                    FORMAT_CONFIG_PATH.write_text(
                        yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8"
                    )
                    self._send(200, json.dumps({"ok": True, "enabled": cfg[key]}).encode())
                elif path == "/api/label":
                    lab = state["label"]
                    if lab.get("running"):
                        self._send(200, json.dumps({"running": True, "total": lab["total"]}).encode())
                        return
                    from autoblog.publish.stickers import load_sticker_catalog

                    total = _label_targets(load_sticker_catalog())
                    if total == 0:
                        self._send(200, json.dumps({"total": 0}).encode())
                        return
                    lab.update({"running": True, "done": 0, "total": total})
                    threading.Thread(target=_run_label, args=(state,), daemon=True).start()
                    self._send(200, json.dumps({"total": total}).encode())
                else:
                    self._send(404, b"not found", "text/plain")
            except Exception as exc:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(exc)}).encode())

        def _generate(self, body):
            from autoblog.draft.rules import CommonRules
            from autoblog.draft.style import StyleProfile
            from autoblog.pipeline import run_pipeline

            src = body.get("src")
            srcval = (body.get("srcval") or "").strip()
            photos = [p for p in (body.get("photos") or []) if p]
            tone = (body.get("tone") or "").strip() or None
            rules = CommonRules(**body["rules"]) if body.get("rules") else None
            dv, qv = _enabled_variants()  # 활성 종류 중 첫 번째를 기본 적용(다중 중 우선)
            result = run_pipeline(
                body["memo"],
                place_url=srcval if src == "place" else None,
                product=srcval if src == "product" else None,
                photos=photos or None,
                style=StyleProfile(tone=tone) if tone else None,
                rules=rules,
                emphasis=bool(body.get("emphasis")),
                structure=bool(body.get("structure")),
                stickers=bool(body.get("stickers")),
                divider_variant=dv[0],
                quote_variant=qv[0],
            )
            state["last"] = result
            blocks = []
            for b in result.plan.blocks:
                blk = {"kind": b.kind, "text": b.text, "variant": b.variant}
                if b.kind == "sticker":
                    blk["sticker_ref"] = f"{b.sticker_pack}:{b.sticker_index}"
                elif b.kind == "image":
                    blk["image_path"] = b.image_path
                    blk["image_label"] = b.image_label
                elif b.kind == "text":
                    blk["emphases"] = [
                        {"text": e.text, "text_color": e.style.text_color,
                         "background_color": e.style.background_color}
                        for e in b.emphases
                    ]
                blocks.append(blk)
            self._send(200, json.dumps({"title": result.plan.title, "blocks": blocks}).encode())

        def _publish(self, body):
            from autoblog.publish.editor import BlogPublisher

            result = state.get("last")
            if not result:
                self._send(400, json.dumps({"error": "먼저 초안을 생성하세요"}).encode())
                return
            category = (body.get("category") or "").strip() or None
            pub = BlogPublisher(headless=False)
            pub.start()
            try:
                if not pub.wait_for_login():
                    raise RuntimeError("네이버 로그인이 필요합니다")
                pub.publish(result.plan, category=category, save=True, submit=False)
            finally:
                pub.close()
            self._send(200, b'{"ok":true}')

    return Handler


FORMAT_CONFIG_PATH = REPO_ROOT / "config" / "format.yaml"
PREVIEW_DIR = REPO_ROOT / "config" / "editor_previews"


def _load_format() -> dict:
    import yaml

    try:
        return yaml.safe_load(FORMAT_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return {}


def _format_summary() -> dict:
    """구분선/인용구 종류 목록(이름·용도·인덱스) + 유저가 쓸 종류(다중 선택)."""
    from autoblog.publish.plan import DIVIDER_META, QUOTE_META

    cfg = _load_format()
    den = cfg.get("divider_enabled") or ["default"]
    qen = cfg.get("quote_enabled") or ["default"]

    def build(meta, enabled):
        return [
            {"value": v, "index": idx, "name": name, "desc": desc, "enabled": v in enabled}
            for v, (idx, name, desc) in meta.items()
        ]

    return {"dividers": build(DIVIDER_META, den), "quotes": build(QUOTE_META, qen)}


def _enabled_variants() -> tuple[list[int], list[int]]:
    """현재 활성화된 구분선/인용구 variant 인덱스 목록(생성에 사용)."""
    from autoblog.publish.plan import DIVIDER_META, QUOTE_META

    cfg = _load_format()
    den = cfg.get("divider_enabled") or ["default"]
    qen = cfg.get("quote_enabled") or ["default"]
    dv = [DIVIDER_META[v][0] for v in den if v in DIVIDER_META]
    qv = [QUOTE_META[v][0] for v in qen if v in QUOTE_META]
    return dv or [1], qv or [1]


def _editor_options() -> dict:
    """라이브 캡처한 에디터 실제 옵션(config/editor_options.json). 없으면 빈 dict."""
    p = REPO_ROOT / "config" / "editor_options.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _emphasis_preview() -> dict:
    """현재 강조 설정으로 실제 적용될 색을 해석(미리보기).

    프로젝트 프리셋(config/power_shortcuts.json)이 있으면 그 색으로, 없으면 내장 기본으로 해석.
    """
    from autoblog.publish.emphasis import (
        DEFAULT_STYLES,
        load_default_power_shortcuts,
        load_emphasis_config,
    )

    cfg = load_emphasis_config()
    presets = load_default_power_shortcuts() or DEFAULT_STYLES
    source = "파워 단축키 프리셋" if load_default_power_shortcuts() else "내장 기본"
    fonts = {f.get("value"): f.get("name", "").split("\n")[0] for f in _editor_options().get("fonts", [])}

    def resolve(pid):
        st = presets.get(pid)
        if not st:
            return {"id": pid, "defined": False}
        return {"id": pid, "defined": True, "text_color": st.text_color,
                "background_color": st.background_color, "bold": st.bold,
                "font": st.font_family, "font_name": fonts.get(st.font_family),
                "size": st.font_size}

    used = {}
    for i in cfg.cycling_pool or []:
        used.setdefault(i, "순환")
    for k, v in (cfg.fixed_map or {}).items():
        used[v] = k
    all_styles = [{**resolve(i), "use": used.get(i)} for i in sorted(presets)]
    return {
        "source": source,
        "all": all_styles,
        "cycling": list(cfg.cycling_pool or []),
        "fixed": cfg.fixed_map or {},
        "max_per_paragraph": cfg.max_per_paragraph,
        "min_sentence_gap": cfg.min_sentence_gap,
    }


def _prompt_preview() -> dict:
    """초안 생성에 쓰이는 프롬프트(베이스 + 우리가 얹는 마커 지시문 레이어)."""
    from autoblog.draft.prompts import load_base_prompt
    from autoblog.publish.emphasis import EMPHASIS_INSTRUCTION
    from autoblog.publish.plan import STRUCTURE_INSTRUCTION

    return {
        "base": load_base_prompt(),
        "layers": [
            ["강조 표시 (강조색 켤 때)", EMPHASIS_INSTRUCTION],
            ["구조 마커 (구분선·인용구 켤 때)", STRUCTURE_INSTRUCTION],
        ],
    }


def _sticker_image(ref: str) -> Path | None:
    from autoblog.publish.stickers import load_sticker_catalog

    s = load_sticker_catalog().by_ref().get(ref)
    if not s or not s.image:
        return None
    p = Path(s.image)
    return p if p.is_absolute() else REPO_ROOT / p


def _catalog_summary() -> dict:
    from autoblog.publish.stickers import load_sticker_catalog

    cat = load_sticker_catalog()
    favset = set(cat.favorites)
    stickers = [
        {"ref": s.ref, "pack": s.pack, "index": s.index, "tags": s.tags, "fav": s.ref in favset}
        for s in cat.stickers
        if not s.stale
    ]
    return {
        "total": len(stickers),
        "favorites": list(cat.favorites),
        "label_count": len(cat.labels()),
        "stickers": stickers,
    }


def _label_targets(cat) -> int:
    from autoblog.publish.stickers import _needs_label

    favs = set(cat.favorites)
    return sum(1 for s in cat.stickers if s.ref in favs and _needs_label(s, True))


def _run_label(state: dict) -> None:
    """즐겨찾기 중 태그 없는 것만 비전 라벨링(백그라운드 스레드). 진행은 state['label']에 기록."""
    from autoblog.publish.stickers import (
        STICKER_CONFIG_PATH,
        label_catalog,
        load_sticker_catalog,
        save_sticker_catalog,
    )

    lab = state["label"]
    try:
        cat = load_sticker_catalog()
        favs = set(cat.favorites)

        def prog(done, total, s):
            lab["done"], lab["total"] = done, total

        result = label_catalog(
            cat, only_refs=favs, only_new=True, on_progress=prog,
            save_path=STICKER_CONFIG_PATH, save_every=3,
        )
        save_sticker_catalog(result)
    finally:
        lab["running"] = False


def _toggle_favorite(ref: str, on: bool) -> int:
    """즐겨찾기 추가/해제 후 config/stickers.yaml 저장. 새 즐겨찾기 수 반환."""
    from autoblog.publish.stickers import load_sticker_catalog, save_sticker_catalog

    cat = load_sticker_catalog()
    favs = [f for f in cat.favorites if f != ref]
    if on and ref in cat.by_ref():
        favs.append(ref)
    cat.favorites = favs
    save_sticker_catalog(cat)
    return len(favs)


def serve_ui(host: str = "127.0.0.1", port: int = 8770) -> ThreadingHTTPServer:
    """글쓰기 UI 서버 생성. publish는 블로킹이라 스레드 서버 사용."""
    state: dict = {
        "last": None,
        "thumbs": {},
        "label": {"running": False, "done": 0, "total": 0},
    }
    server = ThreadingHTTPServer((host, port), _make_handler(state))
    server.daemon_threads = True
    threading.current_thread()
    return server
