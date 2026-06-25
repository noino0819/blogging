"""글쓰기 유저 화면 — 로컬 웹(표준 http.server, npm/node 0).

스티커 검수에서 검증한 "로컬 서버 + 브라우저" 패턴을 글쓰기 전체로 확장한 유저 화면.
경험 메모/수집 입력 → [생성](run_pipeline) → 초안·미리보기(마커가 서식으로) → [임시저장](BlogPublisher).
`autoblog ui` 한 줄이 서버 기동 + 브라우저 자동 오픈. 일반 유저용은 이후 PyInstaller로 더블클릭 앱.
Electron으로 가더라도 이 화면을 그대로 띄우면 됨(로컬서버+웹뷰는 표준 패턴).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from autoblog.config import REPO_ROOT

_PAGE = """<!doctype html><html lang=ko><head><meta charset=utf-8>
<title>블로그 글쓰기</title><style>
 *{box-sizing:border-box}
 body{font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;margin:0;background:#f6f7f9;color:#222;display:flex;height:100vh}
 .panel{padding:18px;overflow:auto;height:100vh}
 .left{width:380px;flex:0 0 380px;background:#fff;border-right:1px solid #e3e5e8}
 .right{flex:1}
 h1{font-size:16px;margin:0 0 14px}
 label.f{display:block;font-size:12px;color:#555;margin:12px 0 4px;font-weight:600}
 input[type=text],textarea,select{width:100%;border:1px solid #d0d3d7;border-radius:7px;padding:8px;font-size:13px;font-family:inherit}
 textarea{min-height:120px;resize:vertical}
 .row{display:flex;gap:8px;align-items:center}
 .toggles label{font-size:13px;margin-right:14px;cursor:pointer}
 button{font-size:14px;padding:10px 16px;border:1px solid #03c75a;background:#03c75a;color:#fff;border-radius:8px;cursor:pointer;font-weight:600;width:100%}
 button.sec{background:#fff;color:#222;border-color:#d0d3d7;font-weight:500}
 button:disabled{opacity:.5;cursor:default}
 .seg{display:flex;gap:6px;margin-bottom:6px}
 .seg button{width:auto;flex:1;padding:7px;font-size:12px;background:#fff;color:#555;border-color:#d0d3d7;font-weight:500}
 .seg button.on{background:#eafaf0;color:#03c75a;border-color:#03c75a}
 #status{font-size:12px;color:#888;margin-top:10px;min-height:16px}
 /* preview */
 .doc{background:#fff;border:1px solid #e3e5e8;border-radius:12px;max-width:620px;margin:0 auto;padding:28px 32px}
 .doc h2{font-size:22px;margin:0 0 18px}
 .doc .tx{font-size:15px;line-height:1.9;white-space:pre-wrap;margin:0 0 4px}
 .doc hr{border:none;border-top:1px solid #ddd;margin:20px 40px}
 .doc .q{border-left:3px solid #03c75a;padding:6px 0 6px 16px;color:#444;font-size:16px;margin:16px 0}
 .doc img.st{width:140px;height:140px;object-fit:contain;display:block;margin:8px 0}
 .doc .ph{background:#f0f7ff;border:1px dashed #9cf;border-radius:8px;padding:14px;color:#37c;font-size:13px;margin:8px 0}
 em.hl{font-style:normal;border-radius:3px;padding:0 2px}
 .empty{color:#aaa;text-align:center;margin-top:80px}
</style></head><body>
<div class="panel left">
 <h1>✍️ 블로그 글쓰기</h1>
 <label class=f>수집(선택)</label>
 <div class=seg>
   <button type=button data-src=none class=on>없음</button>
   <button type=button data-src=place>맛집 URL</button>
   <button type=button data-src=product>상품 검색</button>
 </div>
 <input type=text id=srcval placeholder="맛집 플레이스 URL 또는 상품 검색어" style="display:none">
 <label class=f>경험 메모 (글의 중심)</label>
 <textarea id=memo placeholder="예: 비 오는 날 들렀는데 따뜻한 우동이 정말 맛있었어요. 사장님도 친절하셨고..."></textarea>
 <label class=f>사진 경로 (쉼표, 선택)</label>
 <input type=text id=photos placeholder="/path/a.jpg, /path/b.jpg">
 <label class=f>문체 톤 (선택)</label>
 <input type=text id=tone placeholder="예: 친근한 반말로">
 <label class=f>자동 서식</label>
 <div class=toggles>
   <label><input type=checkbox id=emphasis checked> 강조색</label>
   <label><input type=checkbox id=structure checked> 구분선·인용구</label>
   <label><input type=checkbox id=stickers checked> 스티커</label>
 </div>
 <div style="margin-top:18px"><button id=gen>초안 생성</button></div>
 <div id=status></div>
 <hr style="margin:18px 0;border:none;border-top:1px solid #eee">
 <label class=f>발행 카테고리 (선택)</label>
 <input type=text id=category placeholder="카테고리 이름">
 <div style="margin-top:10px"><button id=save class=sec disabled>네이버에 임시저장</button></div>
</div>
<div class="panel right">
 <div id=preview><div class=empty>왼쪽에서 메모를 쓰고 [초안 생성]을 누르세요.</div></div>
</div>
<script>
let SRC='none', PLAN=null;
document.querySelectorAll('.seg button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.seg button').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); SRC=b.dataset.src;
  document.getElementById('srcval').style.display = SRC==='none'?'none':'block';
});
const $=id=>document.getElementById(id);
function st(m){$('status').textContent=m;}

$('gen').onclick=async()=>{
  if(!$('memo').value.trim()){st('경험 메모를 입력하세요.');return;}
  $('gen').disabled=true; $('save').disabled=true; st('수집 + 초안 생성 중... (수십 초)');
  try{
    const body={memo:$('memo').value, src:SRC, srcval:$('srcval').value,
      photos:$('photos').value, tone:$('tone').value,
      emphasis:$('emphasis').checked, structure:$('structure').checked, stickers:$('stickers').checked};
    const r=await fetch('/api/generate',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok){st('실패: '+(d.error||'')); return;}
    PLAN=d; renderPreview(d); st('생성 완료. 검토 후 임시저장하세요.'); $('save').disabled=false;
  }catch(e){st('오류: '+e);}
  finally{$('gen').disabled=false;}
};

function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function renderText(b){
  let h=esc(b.text);
  (b.emphases||[]).forEach(e=>{
    const style=(e.text_color?`color:${e.text_color};`:'')+(e.background_color?`background:${e.background_color};`:'');
    h=h.replace(esc(e.text), `<em class=hl style="${style}">${esc(e.text)}</em>`);
  });
  return `<p class=tx>${h}</p>`;
}
function renderPreview(d){
  let h=`<div class=doc><h2>${esc(d.title)||'(제목 없음)'}</h2>`;
  for(const b of d.blocks){
    if(b.kind==='text') h+=renderText(b);
    else if(b.kind==='divider') h+='<hr>';
    else if(b.kind==='quote') h+=`<div class=q>${esc(b.text)}</div>`;
    else if(b.kind==='sticker') h+=`<img class=st src="/img?ref=${encodeURIComponent(b.sticker_ref)}">`;
    else if(b.kind==='image') h+=`<div class=ph>🖼 사진: ${esc(b.image_label)} <small>${esc(b.image_path)}</small></div>`;
  }
  h+='</div>';
  $('preview').innerHTML=h;
}

$('save').onclick=async()=>{
  if(!PLAN){return;}
  $('save').disabled=true; st('네이버 에디터에 주입 중... 브라우저가 열립니다(수십 초)');
  try{
    const r=await fetch('/api/publish',{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({category:$('category').value})});
    const d=await r.json();
    st(r.ok? '임시저장 완료 ✓ (네이버 글쓰기 > 저장 목록에서 확인)' : '실패: '+(d.error||''));
  }catch(e){st('오류: '+e);}
  finally{$('save').disabled=false;}
};
</script></body></html>"""


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
            if u.path == "/":
                self._send(200, _PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif u.path == "/img":
                ref = parse_qs(u.query).get("ref", [""])[0]
                img = _sticker_image(ref)
                if img and img.exists():
                    self._send(200, img.read_bytes(), "image/png")
                else:
                    self._send(404, b"no image", "text/plain")
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
            except Exception as exc:  # noqa: BLE001 - 사용자에게 메시지 전달
                self._send(500, json.dumps({"error": str(exc)}).encode(), "application/json")

        def _generate(self, body):
            from autoblog.draft.style import StyleProfile
            from autoblog.pipeline import run_pipeline

            src = body.get("src")
            srcval = (body.get("srcval") or "").strip()
            photos = [p.strip() for p in (body.get("photos") or "").split(",") if p.strip()]
            tone = (body.get("tone") or "").strip() or None
            result = run_pipeline(
                body["memo"],
                place_url=srcval if src == "place" else None,
                product=srcval if src == "product" else None,
                photos=photos or None,
                style=StyleProfile(tone=tone) if tone else None,
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


def serve_ui(host: str = "127.0.0.1", port: int = 8770) -> ThreadingHTTPServer:
    """글쓰기 UI 서버 생성(serve_forever는 호출 측). publish는 블로킹이라 스레드 서버 사용."""
    state: dict = {"last": None}
    server = ThreadingHTTPServer((host, port), _make_handler(state))
    server.daemon_threads = True
    threading.current_thread()  # no-op; 스레드 서버라 동시 요청 처리
    return server
