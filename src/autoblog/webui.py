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

_PAGE = r"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>블로그 자동작성</title><style>
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
 .stgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:12px}
 .stcard{background:#fff;border:1px solid var(--line);border-radius:14px;padding:10px;text-align:center}
 .stcard img{width:100%;aspect-ratio:1;object-fit:contain;background:#fafbfc;border-radius:9px}
 .stcard .tg{font-size:11px;color:var(--sub);margin-top:6px;line-height:1.4;min-height:28px}
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
    <p class=desc>글에 들어갈 즐겨찾기 스티커예요. 추가/태그 수정은 <b>스티커 검수</b>에서 합니다.</p>
    <div class=stat id=ststat></div>
    <h3 style="font-size:14px;margin:0 0 12px">⭐ 즐겨찾기</h3>
    <div class=stgrid id=favgrid><div class=muted>불러오는 중…</div></div>
  </section>
  <!-- 설정 -->
  <section class="view settings">
    <h2 class=title>설정</h2>
    <p class=desc>글쓰기 규칙을 켜고 끄면 다음 생성부터 반영됩니다.</p>
    <div class=card id=rules></div>
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
let stLoaded=false;
async function loadStickers(){if(stLoaded)return; stLoaded=true;
  try{const c=await (await fetch('/api/catalog')).json();
    $('#ststat').innerHTML=`<div class=b><div class=n>${c.total}</div><div class=l>전체</div></div>
      <div class=b><div class=n>${c.favorites.length}</div><div class=l>⭐ 즐겨찾기</div></div>
      <div class=b><div class=n>${c.label_count}</div><div class=l>상황 라벨</div></div>`;
    const g=$('#favgrid');
    if(!c.favorites.length){g.innerHTML='<div class=muted>아직 즐겨찾기가 없어요. 터미널에서 <b>autoblog stickers review</b> 로 ★ 지정하세요.</div>';return;}
    g.innerHTML='';
    c.favorites.forEach(s=>{const d=document.createElement('div'); d.className='stcard';
      d.innerHTML=`<img src="/img?ref=${encodeURIComponent(s.ref)}"><div class=tg>${(s.tags||[]).slice(0,3).join(', ')||'—'}</div>`;
      g.appendChild(d);});
  }catch(e){$('#favgrid').innerHTML='<div class=muted>스티커 로드 실패</div>';}
}

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

loadPhotos(); renderRules(); loadModels();
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
                self._send(200, _PAGE.encode("utf-8"), "text/html; charset=utf-8")
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
            elif u.path == "/api/models":
                from autoblog.config import load_models_config

                m = load_models_config().get()
                self._send(200, json.dumps({"text": m.text, "vision": m.vision}).encode())
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                if path == "/api/generate":
                    self._generate(self._json_body())
                elif path == "/api/publish":
                    self._publish(self._json_body())
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
    by = cat.by_ref()
    favs = []
    for ref in cat.favorites:
        s = by.get(ref)
        if s:
            favs.append({"ref": ref, "tags": s.tags})
    active = [s for s in cat.stickers if not s.stale]
    return {"total": len(active), "favorites": favs, "label_count": len(cat.labels())}


def serve_ui(host: str = "127.0.0.1", port: int = 8770) -> ThreadingHTTPServer:
    """글쓰기 UI 서버 생성. publish는 블로킹이라 스레드 서버 사용."""
    state: dict = {"last": None, "thumbs": {}}
    server = ThreadingHTTPServer((host, port), _make_handler(state))
    server.daemon_threads = True
    threading.current_thread()
    return server
