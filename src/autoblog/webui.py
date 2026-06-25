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
UPLOAD_DIR = REPO_ROOT / "data" / "uploads"  # 유저가 올린 사진
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
 :root{
   --green:#03c75a;--green-d:#02b350;--green-soft:#eafaf0;
   --ink:#1f2329;--sub:#8b95a1;--line:#e8eaed;--bg:#f2f4f6;
   --red:#e5484d;--ok:#1f9d57;--blue:#3b82c4;
   --r-sm:8px;--r:12px;--r-lg:16px;--r-pill:999px;
   --fs-xs:12px;--fs-sm:13px;--fs-md:14px;--fs-lg:16px;--fs-xl:20px}
 *{box-sizing:border-box}
 svg.ic{width:18px;height:18px;display:inline-block;vertical-align:middle;flex:0 0 auto;stroke:currentColor}
 .btn .ic,.mx .ic{width:16px;height:16px;margin-right:6px;margin-top:-2px}
 body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Pretendard',sans-serif;
   background:var(--bg);color:var(--ink);display:flex;height:100vh;overflow:hidden}
 /* sidebar */
 .side{width:212px;flex:0 0 212px;background:#fff;border-right:1px solid var(--line);padding:18px 12px;display:flex;flex-direction:column;gap:4px}
 .brand{font-size:15px;font-weight:800;padding:8px 10px 16px;display:flex;align-items:center;gap:9px}
 .brand .ic{width:20px;height:20px;color:var(--green-d)}
 .nav{display:flex;align-items:center;gap:10px;padding:11px 12px;border-radius:var(--r-sm);cursor:pointer;color:#4b5563;font-size:var(--fs-md);font-weight:600}
 .nav:hover{background:#f6f8fa}
 .nav.on{background:var(--green-soft);color:var(--green-d)}
 .nav .ic{width:19px;height:19px;color:#9aa3ad}
 .nav.on .ic{color:var(--green-d)}
 .side .foot{margin-top:auto;font-size:11px;color:var(--sub);padding:8px 10px;line-height:1.6}
 /* main */
 main{flex:1;overflow:auto;padding:26px 30px}
 .view{display:none}.view.on{display:block}
 h2.title{font-size:20px;margin:0 0 4px}
 .desc{color:var(--sub);font-size:13px;margin:0 0 20px}
 /* write layout */
 .grid{display:grid;grid-template-columns:minmax(360px,460px) 1fr;gap:22px;align-items:start}
 .card{background:#fff;border:1px solid var(--line);border-radius:var(--r-lg);padding:20px}
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
 .btn{display:block;width:100%;padding:13px;border:none;border-radius:var(--r);background:var(--green);color:#fff;font-size:var(--fs-md);font-weight:700;cursor:pointer}
 .btn:hover{background:var(--green-d)}
 .btn:disabled{opacity:.45;cursor:default}
 .btn.ghost{background:#fff;color:var(--ink);border:1px solid #d6dade;font-weight:600}
 #status{font-size:12.5px;color:var(--sub);min-height:18px;margin-top:6px;display:flex;align-items:center;gap:8px}
 .spin{width:13px;height:13px;border:2px solid #d6dade;border-top-color:var(--green);border-radius:50%;animation:sp .7s linear infinite;display:none}
 @keyframes sp{to{transform:rotate(360deg)}}
 .loading .spin{display:inline-block}
 /* 수집 종류(맛집/상품) — 크게 잘 보이게 */
 .kindseg{display:flex;gap:8px;margin-top:8px}
 .kindseg button{flex:1;padding:12px;font-size:14px;font-weight:800;background:#fff;color:#9aa3ad;border:2px solid #e0e3e7;border-radius:11px;cursor:pointer;transition:.12s}
 .kindseg button .em{font-size:17px;margin-right:5px}
 .kindseg button.on{background:var(--green);color:#fff;border-color:var(--green);box-shadow:0 3px 10px #03c75a44}
 .kindseg button.auto{outline:3px solid #03c75a33}
 /* 토스트 팝업 — 에러/완료를 화면 중앙 상단에 크게 */
 #toasts{position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:9999;display:flex;flex-direction:column;gap:9px;align-items:center;pointer-events:none;width:max-content;max-width:90vw}
 .toast{pointer-events:auto;min-width:300px;max-width:560px;padding:14px 18px;border-radius:12px;font-size:14px;font-weight:700;color:#fff;line-height:1.45;box-shadow:0 8px 30px rgba(0,0,0,.22);display:flex;gap:11px;align-items:flex-start;cursor:pointer;animation:tin .22s ease}
 .toast.err{background:var(--red)}.toast.ok{background:var(--ok)}.toast.info{background:var(--blue)}
 .toast .ic{font-size:18px;line-height:1.2}.toast .x{margin-left:10px;opacity:.7;font-weight:400}
 @keyframes tin{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:none}}
 /* 프롬프트 내보내기 모달 */
 .modal{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9998;display:flex;align-items:center;justify-content:center;padding:24px}
 .modalbox{background:#fff;border-radius:16px;width:min(780px,94vw);max-height:88vh;display:flex;flex-direction:column;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,.3)}
 .modalhd{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;font-size:15.5px;font-weight:700}
 .mx{border:0;background:#eef0f2;width:32px;height:32px;border-radius:9px;cursor:pointer;font-size:14px}
 .modalbox textarea{flex:1;min-height:360px;margin-top:10px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;line-height:1.55;background:#fafbfc}
 .modalft{margin-top:14px;display:flex;gap:10px}
 /* photo grid */
 .pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(76px,1fr));gap:8px;max-height:230px;overflow:auto;padding:2px}
 .pcell{position:relative;aspect-ratio:1;border-radius:9px;overflow:hidden;cursor:pointer;border:2px solid transparent}
 .pcell img{width:100%;height:100%;object-fit:cover;display:block}
 .pcell.sel{border-color:var(--green)}
 .dropzone{border:2px dashed #cdd3da;border-radius:11px;padding:18px;text-align:center;color:var(--sub);font-size:13px;cursor:pointer;margin-bottom:10px}
 .dropzone:hover,.dropzone.drag{border-color:var(--green);background:#f3fcf6;color:var(--green-d)}
 .pcell.uploading{opacity:.5}
 .pcell .num{position:absolute;top:4px;left:4px;background:var(--green);color:#fff;width:18px;height:18px;border-radius:50%;font-size:11px;display:none;align-items:center;justify-content:center;font-weight:700}
 .pcell.sel .num{display:flex}
 /* preview */
 .doc{background:#fff;border:1px solid var(--line);border-radius:16px;padding:30px 34px;min-height:300px}
 .doc.empty{display:flex;align-items:center;justify-content:center;color:#b0b8c1;font-size:14px;min-height:420px}
 .genload{text-align:center;padding:40px 20px}
 .genchar{font-size:60px;display:inline-block;animation:bounce 1s ease-in-out infinite}
 @keyframes bounce{0%,100%{transform:translateY(0) rotate(-4deg)}50%{transform:translateY(-16px) rotate(4deg)}}
 .genmsg{font-size:16px;color:#374151;margin-top:14px;font-weight:700}
 .genbar{height:14px;background:#eef1f4;border-radius:99px;overflow:hidden;max-width:340px;margin:20px auto 10px}
 .genfill{height:100%;width:0;background:linear-gradient(90deg,#03c75a,#5fe0a0);border-radius:99px;transition:width .5s ease}
 .genpct{font-size:14px;color:var(--green-d);font-weight:800}
 .gensub{font-size:12px;color:var(--sub);margin-top:6px}
 .promptarea{width:100%;min-height:420px;border:1px solid #d6dade;border-radius:10px;padding:14px;font-size:13px;font-family:ui-monospace,Menlo,monospace;line-height:1.6;resize:vertical;background:#fbfcfd}
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
 .tags2{display:flex;flex-wrap:wrap;gap:4px;margin-top:7px;justify-content:center;align-items:center}
 .tg2{background:#eef1f4;border-radius:6px;padding:2px 5px 2px 7px;font-size:11px;display:inline-flex;align-items:center;gap:3px;color:#374151}
 .tg2 .x{cursor:pointer;color:#aab;font-weight:700;font-size:12px}
 .tg2 .x:hover{color:#e2536a}
 .taginput{border:1px dashed #cdd3da;border-radius:6px;padding:2px 6px;font-size:11px;width:54px;text-align:center}
 .taginput:focus{outline:none;border-color:var(--green);border-style:solid}
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
 .mcmd{background:#1f2329;color:#e8eaed;border-radius:10px;padding:14px 16px;font-size:13px;font-family:ui-monospace,Menlo,monospace;line-height:1.8;white-space:pre-wrap}
 .logflags{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
 .lf{font-size:11px;padding:3px 8px;border-radius:6px;background:#eef1f4;color:#555}
 .lf.ok{background:#eafaf0;color:#02b350}.lf.no{background:#fdecef;color:#d9534f}
 .logpre{background:#f6f8fa;border:1px solid var(--line);border-radius:9px;padding:12px;font-size:11.5px;line-height:1.6;white-space:pre-wrap;max-height:300px;overflow:auto;font-family:ui-monospace,Menlo,monospace;margin:4px 0 8px}
 .logsum{cursor:pointer;font-size:12px;font-weight:600;padding:6px 0;color:#4b5563}
</style></head><body><div id=toasts></div>
<svg width=0 height=0 style="position:absolute" aria-hidden=true><defs>
 <g id=i-write fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><path d="M4 20h4L18.5 9.5a2.1 2.1 0 0 0-3-3L5 17v3Z"/><path d="M13.5 6.5l3 3"/></g>
 <g id=i-sticker fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><circle cx=12 cy=12 r=9/><path d="M8.5 14.5a4 4 0 0 0 7 0"/><circle cx=9 cy=10 r=.7 fill=currentColor stroke=none/><circle cx=15 cy=10 r=.7 fill=currentColor stroke=none/></g>
 <g id=i-format fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><path d="M12 3a9 9 0 1 0 0 18c1.1 0 1.8-.9 1.8-1.9 0-.5-.2-.9-.5-1.2-.3-.3-.4-.6-.4-1 0-1 .8-1.7 1.7-1.7H17a4 4 0 0 0 4-4c0-4.4-4-8-9-8Z"/><circle cx=7.5 cy=11.5 r=.9 fill=currentColor stroke=none/><circle cx=12 cy=7.8 r=.9 fill=currentColor stroke=none/><circle cx=16.4 cy=11.5 r=.9 fill=currentColor stroke=none/></g>
 <g id=i-prompt fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v4h4"/><path d="M9 13h6M9 16.5h4"/></g>
 <g id=i-settings fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><circle cx=12 cy=12 r=3/><path d="M19.4 13a7.6 7.6 0 0 0 0-2l2-1.5-2-3.4-2.3 1a7.6 7.6 0 0 0-1.7-1l-.4-2.5h-4l-.4 2.5a7.6 7.6 0 0 0-1.7 1l-2.3-1-2 3.4 2 1.5a7.6 7.6 0 0 0 0 2l-2 1.5 2 3.4 2.3-1a7.6 7.6 0 0 0 1.7 1l.4 2.5h4l.4-2.5a7.6 7.6 0 0 0 1.7-1l2.3 1 2-3.4-2-1.5Z"/></g>
 <g id=i-copy fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><rect x=8 y=3 width=8 height=4 rx=1/><path d="M16 5h2v16H6V5h2"/><path d="M9 12h6M9 16h4"/></g>
 <g id=i-inbox fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><path d="M4 14v5h16v-5"/><path d="M12 4v9m0 0 3.5-3.5M12 13 8.5 9.5"/></g>
 <g id=i-search fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><circle cx=11 cy=11 r=6/><path d="m20 20-3.6-3.6"/></g>
</defs></svg>
<div id=pmodal class=modal style="display:none"><div class=modalbox>
  <div class=modalhd><span><svg class=ic viewBox="0 0 24 24"><use href="#i-copy"/></svg> 다른 챗봇에 붙여넣을 프롬프트</span><button class=mx id=pmclose>✕</button></div>
  <div id=ploading style="display:none"><div class=genload>
    <div class=genchar id=pchar>🧩</div>
    <div class=genmsg id=pmsg>자료를 모으는 중…</div>
    <div class=genbar><div class=genfill id=pfill></div></div>
    <div class=genpct id=ppct>0%</div>
    <div class=gensub>내 프롬프트와 입력 자료를 합치고 있어요</div></div></div>
  <div id=pcontent>
    <div class=muted>내 베이스 프롬프트 + 켜둔 서식/규칙 지시문 + 입력 자료를 합친 전체 프롬프트예요. 복사해서 ChatGPT·Claude 등에 붙여넣고, <b>받은 글은 [📥 받아온 글 붙여넣기]</b>로 다시 가져오세요.</div>
    <textarea id=ptext readonly></textarea>
    <div class=modalft><button class=btn id=pcopy style="flex:1">복사하기</button><button class="btn ghost" id=pmclose2 style="flex:0 0 120px">닫기</button></div>
  </div>
</div></div>
<div id=imodal class=modal style="display:none"><div class=modalbox>
  <div class=modalhd><span><svg class=ic viewBox="0 0 24 24"><use href="#i-inbox"/></svg> 받아온 글 붙여넣기</span><button class=mx id=imclose>✕</button></div>
  <div class=muted>다른 챗봇에서 받은 글을 붙여넣으세요. 강조 &lt;&lt;…&gt;&gt; · [구분선] · [인용구] · [스티커:상황] 마커가 있으면 그대로 적용돼 미리보기로 보여줍니다. 선택한 사진도 함께 배치돼요.</div>
  <textarea id=itext placeholder="여기에 받아온 글을 붙여넣기"></textarea>
  <div class=modalft><button class=btn id=iapply style="flex:1">이 글로 미리보기</button><button class="btn ghost" id=imclose2 style="flex:0 0 120px">닫기</button></div>
</div></div>
<aside class=side>
  <div class=brand><svg class=ic viewBox="0 0 24 24"><use href="#i-write"/></svg> 블로그 자동작성</div>
  <div class="nav on" data-view=write><svg class=ic viewBox="0 0 24 24"><use href="#i-write"/></svg> 글쓰기</div>
  <div class=nav data-view=stickers><svg class=ic viewBox="0 0 24 24"><use href="#i-sticker"/></svg> 스티커</div>
  <div class=nav data-view=format><svg class=ic viewBox="0 0 24 24"><use href="#i-format"/></svg> 서식</div>
  <div class=nav data-view=prompt><svg class=ic viewBox="0 0 24 24"><use href="#i-prompt"/></svg> 프롬프트</div>
  <div class=nav data-view=settings><svg class=ic viewBox="0 0 24 24"><use href="#i-settings"/></svg> 설정</div>
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
          <label class=f>수집 <span class=muted>(선택) — 넣으면 정보 자동 수집</span></label>
          <input type=text id=srcval placeholder="맛집 플레이스 URL 붙여넣기, 또는 상품 검색어 입력">
          <div class=muted style="margin-top:8px">자동 인식 <span class=muted>(틀리면 눌러서 바꾸기)</span></div>
          <div class=kindseg id=kindseg>
            <button data-k=place class=on><span class=em>🍜</span>맛집</button>
            <button data-k=product><span class=em>🛍️</span>상품</button>
          </div>
          <div class=muted id=srchint style="margin-top:6px">링크를 붙여넣으면 알아서 맞춰져요 — 따로 안 골라도 됩니다.</div>
          <label class=f>경험 메모 <span class=muted>(글의 중심)</span></label>
          <textarea id=memo placeholder="예: 비 오는 날 들렀는데 따뜻한 우동이 정말 맛있었어요. 사장님도 친절하셨고 분위기도 아늑했어요."></textarea>
          <label class=f>사진 <span class=muted id=psel></span></label>
          <div class=dropzone id=dropzone>📷 사진을 끌어다 놓거나 <b>클릭해서 추가</b><input type=file id=fileinput accept="image/*" multiple hidden></div>
          <div class=pgrid id=pgrid></div>
          <label class=f>문체 톤 (선택)</label>
          <input type=text id=tone placeholder="예: 친근한 반말로">
          <label class=f>자동 서식</label>
          <div class=chips id=fmt>
            <span class="chip on" data-k=emphasis><span class=dot></span>강조색</span>
            <span class="chip on" data-k=structure><span class=dot></span>구분선·인용구</span>
            <span class="chip on" data-k=stickers><span class=dot></span>스티커</span>
          </div>
          <div style="margin-top:18px"><button class=btn id=gen>초안 생성</button></div>
          <div style="margin-top:9px"><button class="btn ghost" id=export><svg class=ic viewBox="0 0 24 24"><use href="#i-copy"/></svg>내 프롬프트 합쳐서 복사 <span class=muted>(다른 챗봇에 붙여넣기)</span></button></div>
          <div style="margin-top:7px"><button class="btn ghost" id=import><svg class=ic viewBox="0 0 24 24"><use href="#i-inbox"/></svg>받아온 글 붙여넣기 <span class=muted>(다른 챗봇 결과를 미리보기로)</span></button></div>
          <div id=status></div>
        </div>
        <div class=card style="margin-top:16px">
          <h3>네이버에 보내기</h3>
          <label class=f>발행 카테고리 (선택)</label>
          <div style="display:flex;gap:8px">
            <select id=category style="flex:1;border:1px solid #d6dade;border-radius:10px;padding:9px;font-size:13px;background:#fbfcfd">
              <option value="">— 불러오기를 눌러주세요 —</option>
            </select>
            <button class="btn ghost" id=catload style="width:auto;padding:9px 13px;flex:0 0 auto">불러오기</button>
          </div>
          <div class=muted id=catstat style="margin-top:5px"></div>
          <div style="margin-top:12px"><button class="btn ghost" id=save disabled>임시저장</button></div>
        </div>
      </div>
      <div class=col>
        <div class="doc empty" id=preview>왼쪽에서 메모를 쓰고 [초안 생성]을 누르세요.</div>
        <details id=logbox style="display:none;margin-top:14px" class=card>
          <summary style="cursor:pointer;font-weight:700;font-size:13px">🔍 이번 생성 로그 — 들어간 프롬프트 + 모델 원본 출력</summary>
          <div id=logbody style="margin-top:10px"></div>
        </details>
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
      <button class="btn ghost" id=lblbtn style="width:auto;padding:9px 14px"><svg class=ic viewBox="0 0 24 24"><use href="#i-search"/></svg>즐겨찾기 태그 분석</button>
      <span class=muted id=lblstat></span>
    </div>
    <div id=stbody><div class=muted>불러오는 중…</div></div>
  </section>
  <!-- 서식 -->
  <section class="view format">
    <h2 class=title>서식</h2>
    <p class=desc>글에 들어갈 강조색·구분선·인용구를 미리 보고 고릅니다.</p>
    <div class=card><h3>강조색 <span class=muted style="font-weight:400">— 핵심 문장에 번갈아 적용(파워 단축키 프리셋)</span></h3><div id=emph><div class=muted>불러오는 중…</div></div></div>
    <div class=card style="margin-top:16px"><h3>구분선·인용구 종류 <span class=muted style="font-weight:400">— 쓸 종류를 여러 개 고르기</span></h3><div id=variants><div class=muted>불러오는 중…</div></div></div>
  </section>
  <!-- 프롬프트 -->
  <section class="view prompt">
    <h2 class=title>프롬프트</h2>
    <p class=desc>초안 생성에 쓰이는 베이스 프롬프트를 직접 수정할 수 있어요. 저장하면 다음 생성부터 반영됩니다.</p>
    <div class=card>
      <h3>베이스 프롬프트 <span class=muted style="font-weight:400">— config/prompts/default.md</span></h3>
      <textarea id=promptedit class=promptarea placeholder="불러오는 중…"></textarea>
      <div style="margin-top:10px;display:flex;align-items:center;gap:12px">
        <button class=btn id=promptsave style="width:auto;padding:9px 18px">저장</button>
        <span class=muted id=promptstat></span>
      </div>
    </div>
    <div class=card style="margin-top:16px"><h3>자동 추가 레이어 <span class=muted style="font-weight:400">— 마커 지시문(읽기 전용, 토글 켤 때만)</span></h3><div id=promptlayers><div class=muted>불러오는 중…</div></div></div>
  </section>
  <!-- 설정 -->
  <section class="view settings">
    <h2 class=title>설정</h2>
    <p class=desc>글쓰기 규칙과 사용할 모델을 관리합니다.</p>
    <div class=card id=rules></div>
    <div class=card style="margin-top:16px" id=models><h3>모델</h3><div class=muted>불러오는 중…</div></div>
  </section>
</main>
<script>
// fetch 래퍼: 네트워크 단절(서버 꺼짐/재시작)을 'TypeError: Failed to fetch' 대신 친절한 메시지로
const _fetch=window.fetch.bind(window);
window.fetch=async(...a)=>{try{return await _fetch(...a);}
  catch(e){const m='서버에 연결할 수 없어요. 앱(서버)이 꺼졌거나 재시작 중일 수 있어요 — 잠시 후 새로고침하거나 다시 시도하세요.';toast(m,'err');throw new Error(m);}};
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let PHOTOS=[], SELP=[], PLAN=null;
// 토스트 팝업: kind=err|ok|info, ms 후 자동 사라짐(클릭 시 즉시)
function toast(msg,kind='err',ms){if(ms==null)ms=kind==='ok'?3500:6000;
  const t=document.createElement('div');t.className='toast '+kind;
  const ic=kind==='ok'?'✅':kind==='info'?'ℹ️':'⚠️';
  t.innerHTML='<span class=ic>'+ic+'</span><span>'+String(msg).replace(/</g,'&lt;')+'</span><span class=x>✕</span>';
  t.onclick=()=>t.remove();$('#toasts').appendChild(t);setTimeout(()=>t.remove(),ms);}
// 수집 종류: 'place'(맛집·기본) | 'product'(상품). 입력으로 자동 추정하되 직접 고르면 고정.
let SRCKIND='place', KINDMANUAL=false;
function autoKind(v){v=(v||'').trim().toLowerCase(); if(!v)return 'place';
  // 쇼핑 링크 → 상품, 그 외 URL/플레이스 → 맛집, 그냥 글자 → 상품(검색어)
  if(/smartstore\.|shopping\.naver|brand\.naver|coupang\.|11st\.|gmarket\.|ssg\.com/.test(v))return 'product';
  if(/^https?:\/\//.test(v)||/naver\.me|place|map\.naver/.test(v))return 'place';
  return 'product';}
function setKind(k,manual){SRCKIND=k; if(manual)KINDMANUAL=true;
  $$('#kindseg button').forEach(b=>{b.classList.toggle('on',b.dataset.k===k);
    b.classList.toggle('auto',!KINDMANUAL&&b.dataset.k===k);});
  $('#srchint').innerHTML=KINDMANUAL
    ?('<b>'+(k==='place'?'맛집':'상품')+'</b>으로 수집합니다 (직접 선택).')
    :('입력을 보고 <b>'+(k==='place'?'맛집':'상품')+'</b>으로 자동 인식했어요. 직접 골라도 돼요.');}
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
// 수집 종류: 직접 클릭 → 고정, 안 골랐으면 입력으로 자동 추정
$$('#kindseg button').forEach(b=>b.onclick=()=>setKind(b.dataset.k,true));
$('#srcval').oninput=()=>{if(!KINDMANUAL)setKind(autoKind($('#srcval').value),false);};
// 서식 칩
$('#fmt').onclick=e=>{const c=e.target.closest('.chip'); if(!c)return;
  c.classList.toggle('on'); FMT[c.dataset.k]=c.classList.contains('on');};

function st(m,loading){const s=$('#status'); s.innerHTML=(loading?'<span class=spin></span>':'')+m;
  s.parentElement.classList.toggle('loading',!!loading);}

// 사진 로드
function addCell(path, thumbSrc, sel){
  const d=document.createElement('div'); d.className='pcell'+(sel?' sel':''); d.dataset.path=path;
  d.innerHTML=`<img loading=lazy src="${thumbSrc}"><span class=num></span>`;
  d.onclick=()=>toggleP(d); $('#pgrid').appendChild(d); return d;
}
function renumP(){$$('#pgrid .pcell').forEach(c=>{const k=SELP.indexOf(c.dataset.path);
  c.querySelector('.num').textContent=k>=0?k+1:'';});
  $('#psel').textContent=SELP.length?`${SELP.length}장 선택`:'';}
async function loadPhotos(){
  try{const ps=await (await fetch('/api/photos')).json(); $('#pgrid').innerHTML='';
    ps.forEach(p=>addCell(p.path, '/photo?path='+encodeURIComponent(p.path)));
  }catch(e){}
}
function toggleP(el){const path=el.dataset.path; if(!path)return; const i=SELP.indexOf(path);
  if(i>=0){SELP.splice(i,1);el.classList.remove('sel');} else {SELP.push(path);el.classList.add('sel');}
  renumP();
}
function setupUpload(){const dz=$('#dropzone'), fi=$('#fileinput');
  dz.onclick=()=>fi.click(); fi.onchange=()=>handleFiles(fi.files);
  dz.ondragover=e=>{e.preventDefault();dz.classList.add('drag');};
  dz.ondragleave=()=>dz.classList.remove('drag');
  dz.ondrop=e=>{e.preventDefault();dz.classList.remove('drag');handleFiles(e.dataTransfer.files);};}
async function handleFiles(files){
  for(const f of files){ if(!f.type.startsWith('image/'))continue;
    const dataurl=await new Promise(r=>{const fr=new FileReader();fr.onload=()=>r(fr.result);fr.readAsDataURL(f);});
    const cell=addCell('', dataurl, true); cell.classList.add('uploading');
    try{const res=await fetch('/api/upload',{method:'POST',headers:{'content-type':'application/json'},
        body:JSON.stringify({filename:f.name,data:dataurl.split(',')[1]})});
      const d=await res.json(); cell.dataset.path=d.path; cell.classList.remove('uploading'); SELP.push(d.path);
    }catch(e){cell.remove();}
  }
  renumP();
}

let GENTIMER=null;
const GENCHARS=['🐥','✍️','🐣','💭','📝'];
const GENMSGS=[[0,'메모를 읽는 중…'],[18,'글을 쓰는 중…'],[50,'문장을 다듬는 중…'],[78,'강조·서식 입히는 중…'],[92,'거의 다 됐어요!']];
function genLoading(){
  $('#preview').classList.add('empty');
  $('#preview').innerHTML=`<div class=genload><div class=genchar id=genchar>🐥</div>
    <div class=genmsg id=genmsg>메모를 읽는 중…</div>
    <div class=genbar><div class=genfill id=genfill></div></div>
    <div class=genpct id=genpct>0%</div>
    <div class=gensub>로컬 AI가 직접 글을 써요 · 보통 30~60초</div></div>`;
  let pct=0, ci=0;
  GENTIMER=setInterval(()=>{
    pct+=Math.max(0.4,(96-pct)*0.035); if(pct>96)pct=96;
    const fl=$('#genfill'); if(!fl){clearInterval(GENTIMER);return;}
    fl.style.width=pct+'%'; $('#genpct').textContent=Math.floor(pct)+'%';
    const m=GENMSGS.filter(x=>pct>=x[0]).pop(); if(m)$('#genmsg').textContent=m[1];
    ci++; $('#genchar').textContent=GENCHARS[ci%GENCHARS.length];
  },700);
}
function genDone(ok){ if(GENTIMER)clearInterval(GENTIMER);
  if(ok){const fl=$('#genfill'); if(fl){fl.style.width='100%'; $('#genpct').textContent='100%';}} }
$('#gen').onclick=async()=>{
  if(!$('#memo').value.trim()){st('경험 메모를 입력하세요.');return;}
  $('#gen').disabled=true;$('#save').disabled=true; st('생성 중…',true); genLoading();
  try{
    const body={memo:$('#memo').value,srcval:$('#srcval').value,kind:SRCKIND,photos:SELP,tone:$('#tone').value,
      emphasis:FMT.emphasis,structure:FMT.structure,stickers:FMT.stickers,rules:RULES};
    const r=await fetch('/api/generate',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok){genDone(false); $('#preview').innerHTML='<div class=genload><div style="font-size:40px">😢</div><div class=genmsg>생성 실패</div><div class=gensub>'+(d.error||'')+'</div></div>'; st('실패'); toast('초안 생성 실패: '+(d.error||'알 수 없는 오류'),'err'); return;}
    genDone(true); PLAN=d; setTimeout(()=>renderPreview(d),350); st('생성 완료. 검토 후 임시저장하세요.'); toast('초안 생성 완료! 오른쪽 미리보기를 확인하세요.','ok'); $('#save').disabled=false;
    if(d.debug)showLog(d.debug);
  }catch(e){genDone(false); st('오류: '+e); toast('초안 생성 오류: '+e,'err');}finally{$('#gen').disabled=false;}
};
// 프롬프트 내보내기: 모달 안에서 진행바 보여주고, 합쳐진 프롬프트 표시·복사
let EXPTIMER=null;
const EXPCHARS=['🧩','✍️','🔗','📋','💭'], EXPMSGS=[[0,'자료를 모으는 중…'],[45,'내 프롬프트와 합치는 중…'],[80,'마무리 중…']];
function expLoading(on){
  $('#ploading').style.display=on?'block':'none'; $('#pcontent').style.display=on?'none':'block';
  if(EXPTIMER){clearInterval(EXPTIMER);EXPTIMER=null;}
  if(on){$('#pmodal').style.display='flex'; let pct=0,ci=0;
    $('#pfill').style.width='0%'; $('#ppct').textContent='0%'; $('#pmsg').textContent=EXPMSGS[0][1];
    EXPTIMER=setInterval(()=>{pct+=Math.max(1,(96-pct)*0.08); if(pct>96)pct=96;
      const fl=$('#pfill'); if(!fl){clearInterval(EXPTIMER);return;}
      fl.style.width=pct+'%'; $('#ppct').textContent=Math.floor(pct)+'%';
      const m=EXPMSGS.filter(x=>pct>=x[0]).pop(); if(m)$('#pmsg').textContent=m[1];
      ci++; $('#pchar').textContent=EXPCHARS[ci%EXPCHARS.length];},650);
  }else{const fl=$('#pfill'); if(fl)fl.style.width='100%'; $('#ppct').textContent='100%';}
}
$('#export').onclick=async()=>{
  if(!$('#memo').value.trim()){toast('경험 메모를 먼저 입력하세요.','info');return;}
  $('#export').disabled=true; expLoading(true);
  try{
    const body={memo:$('#memo').value,srcval:$('#srcval').value,kind:SRCKIND,photos:SELP,tone:$('#tone').value,
      emphasis:FMT.emphasis,structure:FMT.structure,stickers:FMT.stickers,rules:RULES};
    const r=await fetch('/api/export-prompt',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok){closePM(); toast('프롬프트 생성 실패: '+(d.error||''),'err');return;}
    $('#ptext').value=d.prompt; expLoading(false);
  }catch(e){closePM(); toast('프롬프트 오류: '+e,'err');}finally{$('#export').disabled=false;}
};
$('#pcopy').onclick=async()=>{const t=$('#ptext');
  try{await navigator.clipboard.writeText(t.value);}catch(e){t.select();document.execCommand('copy');}
  toast('복사했어요! 다른 챗봇에 붙여넣으세요.','ok');};
function closePM(){$('#pmodal').style.display='none'; if(EXPTIMER){clearInterval(EXPTIMER);EXPTIMER=null;}}
$('#pmclose').onclick=closePM; $('#pmclose2').onclick=closePM;
$('#pmodal').onclick=e=>{if(e.target===$('#pmodal'))closePM();};
// 받아온 글 붙여넣기: 외부 챗봇 결과 → 마커 파싱 → 미리보기(생성과 동일 경로)
function closeIM(){$('#imodal').style.display='none';}
$('#import').onclick=()=>{$('#imodal').style.display='flex'; $('#itext').focus();};
$('#imclose').onclick=closeIM; $('#imclose2').onclick=closeIM;
$('#imodal').onclick=e=>{if(e.target===$('#imodal'))closeIM();};
$('#iapply').onclick=async()=>{
  const text=$('#itext').value.trim();
  if(!text){toast('붙여넣은 글이 비어 있어요.','info');return;}
  $('#iapply').disabled=true;
  try{
    const body={text,photos:SELP,emphasis:FMT.emphasis,structure:FMT.structure,stickers:FMT.stickers};
    const r=await fetch('/api/import-draft',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok){toast('가져오기 실패: '+(d.error||''),'err');return;}
    closeIM(); PLAN=d; renderPreview(d); st('받아온 글을 미리보기에 반영했어요. 검토 후 임시저장하세요.'); toast('받아온 글을 가져왔어요! 검토 후 임시저장하세요.','ok'); $('#save').disabled=false;
    if(d.debug)showLog(d.debug);
  }catch(e){toast('가져오기 오류: '+e,'err');}finally{$('#iapply').disabled=false;}
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
function showLog(dbg){
  const raw=dbg.raw||'';
  const cnt=(re)=>(raw.match(re)||[]).length;
  const flags=`<div class=logflags>
    <span class="lf ${raw.includes('<<')?'ok':'no'}">강조마킹 &lt;&lt; ${raw.includes('<<')?'있음':'없음'}</span>
    <span class="lf ${cnt(/\[구분선/g)?'ok':'no'}">구분선 ${cnt(/\[구분선/g)}</span>
    <span class="lf ${cnt(/\[인용구\]/g)?'ok':'no'}">인용구 ${cnt(/\[인용구\]/g)}</span>
    <span class="lf ${cnt(/\[스티커/g)?'ok':'no'}">스티커 ${cnt(/\[스티커/g)}</span>
    <span class=lf>줄바꿈 ${cnt(/\n/g)}</span>
    <span class=lf>모델 ${dbg.model||'기본'}</span></div>`;
  $('#logbody').innerHTML=flags
    +'<div class=sub-h>모델 원본 출력 (후처리 전)</div><pre class=logpre>'+esc(raw)+'</pre>'
    +'<details><summary class=logsum>시스템 프롬프트 전체 보기</summary><pre class=logpre>'+esc(dbg.system||'')+'</pre></details>'
    +'<details><summary class=logsum>유저 프롬프트(재료) 보기</summary><pre class=logpre>'+esc(dbg.user||'')+'</pre></details>';
  $('#logbox').style.display='block';
}
function fillCategories(cats){const sel=$('#category');
  sel.innerHTML='<option value="">— 선택 안 함 —</option>'+cats.map(c=>
    `<option value="${esc(c.name)}">${'　'.repeat(c.depth||0)}${c.depth?'└ ':''}${esc(c.name)}</option>`).join('');}
async function loadCategories(){try{const d=await (await fetch('/api/categories')).json();
  if(d.categories&&d.categories.length){fillCategories(d.categories); $('#catstat').textContent=`저장된 ${d.categories.length}개 · 갱신하려면 [불러오기]`;}
}catch(e){}}
$('#catload').onclick=async()=>{
  $('#catload').disabled=true; $('#catstat').textContent='백그라운드에서 불러오는 중… (브라우저 안 뜸, 수십 초)';
  try{const r=await fetch('/api/categories',{method:'POST'}); const d=await r.json();
    if(!r.ok){$('#catstat').textContent='실패: '+(d.error||''); toast('카테고리 불러오기 실패: '+(d.error||''),'err'); return;}
    fillCategories(d.categories); $('#catstat').textContent=`카테고리 ${d.categories.length}개 불러와 저장됨`; toast(`카테고리 ${d.categories.length}개를 불러와 저장했어요.`,'ok');
  }catch(e){$('#catstat').textContent='오류: '+e; toast('카테고리 오류: '+e,'err');}finally{$('#catload').disabled=false;}
};
$('#save').onclick=async()=>{if(!PLAN)return;
  $('#save').disabled=true; st('네이버 에디터에 주입 중… 브라우저가 열립니다',true);
  try{const r=await fetch('/api/publish',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({category:$('#category').value})});
    const d=await r.json(); st(r.ok?'임시저장 완료 ✓ (네이버 글쓰기 › 저장 목록)':'실패: '+(d.error||'')); toast(r.ok?'임시저장 완료! 네이버 글쓰기 › 저장 목록에서 확인하세요.':'임시저장 실패: '+(d.error||''),r.ok?'ok':'err');
  }catch(e){st('오류: '+e); toast('임시저장 오류: '+e,'err');}finally{$('#save').disabled=false;}
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
        ${tagsHtml(s)}</div>`;}
    h+='</div>';
  }
  body.innerHTML=h;
}
function tagsHtml(s){return `<div class=tags2 data-ref="${s.ref}">`
  +(s.tags||[]).map(t=>`<span class=tg2>${esc(t)}<span class=x data-t="${esc(t)}">×</span></span>`).join('')
  +`<input class=taginput placeholder="+태그"></div>`;}
function stickerOf(ref){return CAT.stickers.find(z=>z.ref===ref);}
async function saveTags(s){try{await fetch('/api/sticker-tags',{method:'POST',headers:{'content-type':'application/json'},
  body:JSON.stringify({ref:s.ref,tags:s.tags})});}catch(e){}}
function redrawTags(wrap){const s=stickerOf(wrap.dataset.ref); if(s)wrap.outerHTML=tagsHtml(s);}
$('#stfilter').onclick=e=>{const b=e.target.closest('button'); if(!b)return;
  $$('#stfilter button').forEach(x=>x.classList.remove('on')); b.classList.add('on');
  ST_FILTER=b.dataset.f; renderStickers();};
// 태그 칩 삭제(×)
$('#stbody').addEventListener('click', e=>{const x=e.target.closest('.x'); if(!x)return;
  const wrap=x.closest('.tags2'); const s=stickerOf(wrap.dataset.ref); if(!s)return;
  s.tags=(s.tags||[]).filter(t=>t!==x.dataset.t); redrawTags(wrap); saveTags(s);});
// 태그 추가(엔터)
$('#stbody').addEventListener('keydown', e=>{
  if(!e.target.classList.contains('taginput')||e.key!=='Enter')return;
  e.preventDefault(); const wrap=e.target.closest('.tags2'); const s=stickerOf(wrap.dataset.ref);
  const v=e.target.value.trim(); if(!s||!v)return;
  if(!(s.tags||[]).includes(v)){s.tags=(s.tags||[]).concat(v);} redrawTags(wrap);
  const ni=wrap.querySelector('.taginput'); if(ni)ni.focus(); saveTags(s);});
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
let HAS_API_KEY=false;
function renderModelInfo(p){if(!p)return;
  const isApi=p.provider==='anthropic';
  let h=`<div class=setrow><div><div class=t>텍스트 (초안 작성)</div><div class=d>${p.text} ${isApi?'<span style="color:#7b61ff">· Claude API</span>':'<span class=muted>· 로컬</span>'}</div></div></div>
    <div class=setrow><div><div class=t>비전 (사진/상품 분석)</div><div class=d>${p.vision} <span class=muted>· 로컬</span></div></div></div>
    ${p.note?`<div class=muted style="margin:8px 0 14px">💡 ${p.note}</div>`:''}`;
  if(isApi){
    h+=`<div class=muted style="margin-bottom:6px">✅ 이 프리셋은 <b>Claude API</b>를 씁니다. 아래에서 API 키를 등록하면 바로 적용돼요(비전은 로컬 유지).</div>`;
  }else{
    h+=`<div class=sub-h>설치 방법 — 터미널에 입력</div>
      <pre class=mcmd>ollama pull ${p.text}\nollama pull ${p.vision}</pre>
      <div class=muted style="margin-top:8px">Ollama가 없으면 <b>ollama.com</b>에서 먼저 설치 → 위 명령으로 모델 다운로드. 한 번만 받으면 계속 씁니다.</div>`;
  }
  $('#minfo').innerHTML=h;
}
function refreshApiKeyUI(){
  $('#apikey').placeholder=HAS_API_KEY?'키 저장됨 ✓ (다시 입력해 교체)':'sk-ant-...';
  $('#apikeystat').innerHTML=HAS_API_KEY
    ?'저장됨 ✓ · 프리셋에서 <b>Claude API</b>를 고르면 Claude로 생성됩니다.'
    :'키는 <b>console.anthropic.com</b> › API Keys에서 발급. .env에 저장됩니다.';}
async function loadModels(){try{const m=await (await fetch('/api/models')).json();
  HAS_API_KEY=!!m.has_api_key;
  const opts=m.presets.map(p=>`<option value="${p.key}"${p.key===m.current?' selected':''}>${p.label}</option>`).join('');
  $('#models').innerHTML=`<h3>모델 <span class=muted style="font-weight:400">— 내 컴퓨터(GPU)에 맞게</span></h3>
    <div class=setrow><div class=t>프리셋</div><select id=mpreset style="width:auto;min-width:260px;border:1px solid #d6dade;border-radius:8px;padding:8px">${opts}</select></div>
    <div id=minfo></div>
    <div class=sub-h style="margin-top:20px">Claude API 키 <span class=muted style="font-weight:400">— (선택) 로컬 모델이 마커를 잘 못 넣으면 정확함</span></div>
    <div class=muted style="margin-bottom:8px">키를 등록해두고, 위 <b>프리셋</b>에서 "Claude API"를 고르면 초안을 Claude로 생성합니다(토큰당 과금).</div>
    <div style="display:flex;gap:8px">
      <input type=password id=apikey placeholder="sk-ant-..." style="flex:1;border:1px solid #d6dade;border-radius:8px;padding:9px;font-size:13px">
      <button class=btn id=apikeysave style="width:auto;padding:9px 16px">저장</button>
    </div>
    <div class=muted id=apikeystat style="margin-top:6px"></div>`;
  $('#mpreset').onchange=async()=>{const k=$('#mpreset').value;
    await fetch('/api/models',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({preset:k})});
    renderModelInfo(m.presets.find(p=>p.key===k));};
  $('#apikeysave').onclick=async()=>{const v=$('#apikey').value.trim(); if(!v){toast('키를 입력하세요.','info');return;}
    $('#apikeysave').disabled=true; $('#apikeystat').textContent='저장 중…';
    try{const r=await fetch('/api/anthropic-key',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({key:v})});
      HAS_API_KEY=r.ok; $('#apikey').value=''; refreshApiKeyUI();
      if(r.ok)toast('API 키 저장됨 ✓ 프리셋에서 "Claude API"를 고르면 적용돼요.','ok'); else toast('API 키 저장 실패','err');
    }catch(e){toast('API 키 오류: '+e,'err');}finally{$('#apikeysave').disabled=false;}};
  renderModelInfo(m.presets.find(p=>p.key===m.current));
  refreshApiKeyUI();
}catch(e){$('#models').innerHTML='<div class=muted>로드 실패</div>';}}

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
  $('#promptedit').value=p.base_raw||'';
  $('#promptlayers').innerHTML='<div class=promptbox>'+p.layers.map(([t,b])=>`<details><summary>${esc(t)}</summary><pre>${esc(b)}</pre></details>`).join('')+'</div>';
}catch(e){$('#promptlayers').innerHTML='<div class=muted>로드 실패</div>';}}
$('#promptsave').onclick=async()=>{
  $('#promptsave').disabled=true; $('#promptstat').textContent='저장 중…';
  try{const r=await fetch('/api/prompt',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({base:$('#promptedit').value})});
    $('#promptstat').textContent=r.ok?'저장됨 ✓ 다음 생성부터 반영돼요':'저장 실패';
  }catch(e){$('#promptstat').textContent='오류';}finally{$('#promptsave').disabled=false;}
};
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
setKind('place',false); loadPhotos(); setupUpload(); renderRules(); loadModels(); loadEmphasis(); loadPrompt(); loadVariants(); loadCategories();
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
    for base in (PHOTO_DIR.resolve(), UPLOAD_DIR.resolve()):
        try:
            p.relative_to(base)
            return p if p.exists() else None
        except ValueError:
            continue
    return None


def _save_upload(filename: str, b64: str) -> str:
    """업로드 이미지를 data/uploads/에 저장하고 경로 반환."""
    import base64
    import uuid

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = Path(filename).name or "image"
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{safe}"
    dest.write_bytes(base64.b64decode(b64))
    return str(dest)


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
            try:
                self._route_get()
            except BrokenPipeError:
                pass  # 클라이언트가 먼저 끊음 — 무시
            except Exception as exc:  # noqa: BLE001
                import traceback

                print(f"[webui] GET {self.path} 실패: {exc}", flush=True)
                traceback.print_exc()

        def _route_get(self):
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
                self._send(200, json.dumps(_models_info()).encode())
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
            elif u.path == "/api/categories":
                self._send(200, json.dumps({"categories": _load_categories()}).encode())
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                if path == "/api/generate":
                    self._generate(self._json_body())
                elif path == "/api/export-prompt":
                    self._export_prompt(self._json_body())
                elif path == "/api/import-draft":
                    self._import_draft(self._json_body())
                elif path == "/api/publish":
                    self._publish(self._json_body())
                elif path == "/api/favorite":
                    body = self._json_body()
                    n = _toggle_favorite(body.get("ref", ""), bool(body.get("on")))
                    self._send(200, json.dumps({"ok": True, "favorites": n}).encode())
                elif path == "/api/upload":
                    body = self._json_body()
                    p = _save_upload(body.get("filename", ""), body.get("data", ""))
                    self._send(200, json.dumps({"path": p}).encode())
                elif path == "/api/categories":
                    cats = _fetch_categories()
                    state["categories"] = cats
                    self._send(200, json.dumps({"categories": cats}).encode())
                elif path == "/api/sticker-tags":
                    body = self._json_body()
                    _set_sticker_tags(body.get("ref", ""), body.get("tags", []))
                    self._send(200, b'{"ok":true}')
                elif path == "/api/prompt":
                    _save_prompt(self._json_body().get("base", ""))
                    self._send(200, b'{"ok":true}')
                elif path == "/api/models":
                    _set_model_preset(self._json_body().get("preset", ""))
                    self._send(200, b'{"ok":true}')
                elif path == "/api/anthropic-key":
                    _set_anthropic_key(self._json_body().get("key", ""))
                    self._send(200, b'{"ok":true}')
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
            except BrokenPipeError:
                pass  # 클라이언트가 먼저 끊음(새로고침/이탈) — 무시
            except Exception as exc:  # noqa: BLE001
                import traceback

                print(f"[webui] POST {path} 실패: {exc}", flush=True)
                traceback.print_exc()
                try:
                    self._send(500, json.dumps({"error": str(exc)}).encode())
                except Exception:  # noqa: BLE001
                    pass

        @staticmethod
        def _resolve_src(body):
            """body의 srcval+kind → (srcval, src) — generate/export 공통 종류 판정."""
            srcval = (body.get("srcval") or "").strip()
            kind = (body.get("kind") or "").strip()
            if srcval and kind in ("place", "product"):
                return srcval, kind
            is_url = srcval.startswith("http") or "naver.me" in srcval or "place" in srcval
            return srcval, ("place" if (srcval and is_url) else ("product" if srcval else None))

        def _export_prompt(self, body):
            """수집+내 프롬프트+지시문을 한 텍스트로 합쳐 반환(다른 챗봇에 붙여넣기용)."""
            from autoblog.draft.rules import CommonRules
            from autoblog.draft.style import StyleProfile
            from autoblog.pipeline import build_export_prompt

            srcval, src = self._resolve_src(body)
            photos = [p for p in (body.get("photos") or []) if p]
            tone = (body.get("tone") or "").strip() or None
            rules = CommonRules(**body["rules"]) if body.get("rules") else None
            text = build_export_prompt(
                body.get("memo", ""),
                place_url=srcval if src == "place" else None,
                product=srcval if src == "product" else None,
                photos=photos or None,
                style=StyleProfile(tone=tone) if tone else None,
                rules=rules,
                emphasis=bool(body.get("emphasis")),
                structure=bool(body.get("structure")),
                stickers=bool(body.get("stickers")),
            )
            self._send(200, json.dumps({"prompt": text}).encode())

        def _generate(self, body):
            from autoblog.draft.rules import CommonRules
            from autoblog.draft.style import StyleProfile
            from autoblog.pipeline import run_pipeline

            srcval, src = self._resolve_src(body)
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
            self._send_plan(result)

        def _import_draft(self, body):
            """외부 챗봇에서 받아온 초안 텍스트 → 마커 파싱 → 게시 플랜(생성과 동일 흐름)."""
            from autoblog.pipeline import plan_from_text

            text = (body.get("text") or "").strip()
            if not text:
                self._send(400, json.dumps({"error": "붙여넣은 글이 비어 있어요"}).encode())
                return
            photos = [p for p in (body.get("photos") or []) if p]
            dv, qv = _enabled_variants()
            result = plan_from_text(
                text,
                photos=photos or None,
                emphasis=bool(body.get("emphasis")),
                structure=bool(body.get("structure")),
                stickers=bool(body.get("stickers")),
                divider_variant=dv[0],
                quote_variant=qv[0],
            )
            self._send_plan(result)

        def _send_plan(self, result):
            """PipelineResult → {title, blocks, debug} JSON. generate/import 공통."""
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
            self._send(200, json.dumps(
                {"title": result.plan.title, "blocks": blocks, "debug": result.draft.debug}
            ).encode())

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
    for i in cfg.negative_pool or []:
        used.setdefault(i, "부정")
    for k, v in (cfg.fixed_map or {}).items():
        used[v] = k
    all_styles = [{**resolve(i), "use": used.get(i)} for i in sorted(presets)]
    return {
        "source": source,
        "all": all_styles,
        "cycling": list(cfg.cycling_pool or []),
        "negative": list(cfg.negative_pool or []),
        "fixed": cfg.fixed_map or {},
        "max_per_paragraph": cfg.max_per_paragraph,
        "min_sentence_gap": cfg.min_sentence_gap,
    }


def _prompt_preview() -> dict:
    """초안 생성에 쓰이는 프롬프트(편집용 raw default.md + 우리가 얹는 마커 지시문 레이어)."""
    from autoblog.draft.prompts import DEFAULT_PROMPT_PATH
    from autoblog.publish.emphasis import EMPHASIS_INSTRUCTION
    from autoblog.publish.plan import STRUCTURE_INSTRUCTION

    return {
        "base_raw": DEFAULT_PROMPT_PATH.read_text(encoding="utf-8"),
        "layers": [
            ["강조 표시 (강조색 켤 때)", EMPHASIS_INSTRUCTION],
            ["구조 마커 (구분선·인용구 켤 때)", STRUCTURE_INSTRUCTION],
        ],
    }


def _save_prompt(text: str) -> None:
    from autoblog.draft.prompts import DEFAULT_PROMPT_PATH

    DEFAULT_PROMPT_PATH.write_text(text, encoding="utf-8")


def _models_info() -> dict:
    """현재 모델 + 선택 가능한 프리셋 목록(모델 변경용)."""
    from autoblog.config import load_env, load_models_config

    cfg = load_models_config()
    cur = cfg.get()
    presets = [
        {"key": k, "label": p.label, "text": p.text, "vision": p.vision,
         "note": p.note, "provider": p.provider}
        for k, p in cfg.presets.items()
    ]
    return {
        "current": cfg.default, "text": cur.text, "vision": cur.vision,
        "provider": cur.provider, "presets": presets,
        "has_api_key": bool(load_env().anthropic_api_key),
    }


def _set_anthropic_key(key: str) -> None:
    from autoblog.config import load_env, save_env_value

    save_env_value("ANTHROPIC_API_KEY", key.strip())
    load_env.cache_clear()


CATEGORIES_PATH = REPO_ROOT / "config" / "categories.json"


def _load_categories() -> list:
    """저장해둔 카테고리(한 번 불러오면 파일에 캐시). 없으면 빈 목록."""
    try:
        return json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def _fetch_categories() -> list:
    """네이버 블로그 카테고리(이름+뎁스)를 헤드리스로 불러와 파일에 저장(브라우저 안 뜸).

    저장된 세션(storage_state)으로 자동로그인되므로 백그라운드(headless)로 동작한다.
    """
    from autoblog.publish.editor import BlogPublisher

    pub = BlogPublisher(headless=True)
    pub.start()
    try:
        if not pub.wait_for_login():
            raise RuntimeError("네이버 로그인이 필요합니다")
        cats = pub.get_categories_detailed()
    finally:
        pub.close()
    CATEGORIES_PATH.write_text(json.dumps(cats, ensure_ascii=False), encoding="utf-8")
    return cats


def _set_model_preset(key: str) -> None:
    import yaml

    from autoblog.config import CONFIG_DIR

    path = CONFIG_DIR / "models.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if key in data.get("presets", {}):
        data["default"] = key
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        from autoblog.config import load_models_config

        load_models_config.cache_clear()  # lru_cache 무효화


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


def _set_sticker_tags(ref: str, tags: list) -> None:
    """스티커 태그를 유저가 직접 수정 → config/stickers.yaml 저장(reviewed=True로 보호)."""
    from autoblog.publish.stickers import load_sticker_catalog, save_sticker_catalog

    cat = load_sticker_catalog()
    by = cat.by_ref()
    s = by.get(ref)
    if s:
        clean = []
        for t in tags:
            t = str(t).strip()
            if t and t not in clean:
                clean.append(t)
        s.tags = clean
        s.reviewed = True
        save_sticker_catalog(cat)


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
    ThreadingHTTPServer.request_queue_size = 128  # 동시 요청(이미지 다발) 대비 backlog 확대
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((host, port), _make_handler(state))
    server.daemon_threads = True
    return server
