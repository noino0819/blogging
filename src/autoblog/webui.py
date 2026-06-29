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
 /* 백그라운드 작업 칩 — 코너에 떠서 경과시간을 보여주고, 끝나면 사라진다 */
 #bgtasks{position:fixed;right:18px;bottom:18px;z-index:9999;display:flex;flex-direction:column;gap:9px;align-items:flex-end;pointer-events:none}
 .bgtask{display:flex;align-items:center;gap:10px;background:#fff;border:1px solid var(--line);border-radius:13px;padding:11px 16px;font-size:12.5px;font-weight:600;color:var(--ink);box-shadow:0 12px 30px rgba(0,0,0,.16);animation:tin .24s cubic-bezier(.2,.9,.3,1.25);pointer-events:auto}
 .bgtask.out{animation:tout .18s ease forwards}
 .bgtask .spin{display:inline-block}
 /* 토스트 팝업 — 에러/완료를 화면 중앙 상단에 크게 */
 #toasts{position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:9999;display:flex;flex-direction:column;gap:9px;align-items:center;pointer-events:none;width:max-content;max-width:90vw}
 .toast{position:relative;pointer-events:auto;min-width:300px;max-width:560px;padding:14px 46px 14px 16px;border-radius:14px;font-size:14px;font-weight:700;color:#fff;line-height:1.45;box-shadow:0 12px 34px rgba(0,0,0,.26);display:flex;gap:11px;align-items:flex-start;animation:tin .24s cubic-bezier(.2,.9,.3,1.25)}
 .toast.out{animation:tout .18s ease forwards}
 .toast.err{background:linear-gradient(135deg,#f15a4d,#e23b2e)}
 .toast.ok{background:linear-gradient(135deg,#1ec46c,#06a94f)}
 .toast.info{background:linear-gradient(135deg,#3f99f6,#2b7fe0)}
 .toast .ic{font-size:18px;line-height:1.3;flex:none}.toast .msg{flex:1;padding-top:1px}
 .toast .x{position:absolute;top:9px;right:9px;width:24px;height:24px;display:flex;align-items:center;justify-content:center;border-radius:50%;font-size:13px;line-height:1;opacity:.85;cursor:pointer;transition:.12s;background:rgba(255,255,255,.14)}
 .toast .x:hover{opacity:1;background:rgba(255,255,255,.32)}
 @keyframes tin{from{opacity:0;transform:translateY(-12px) scale(.97)}to{opacity:1;transform:none}}
 @keyframes tout{to{opacity:0;transform:translateY(-8px) scale(.97)}}
 /* 프롬프트 내보내기 모달 */
 .modal{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9998;display:flex;align-items:center;justify-content:center;padding:24px}
 .modalbox{background:#fff;border-radius:16px;width:min(780px,94vw);max-height:88vh;display:flex;flex-direction:column;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,.3)}
 .phbox{width:min(920px,96vw)}
 .phscroll{flex:1;overflow:auto;margin-top:10px}
 .phbox .pgrid{max-height:none;margin-bottom:10px}
 .phbox .pmeta{max-height:none;border:0;padding:0}
 .modalhd{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;font-size:15.5px;font-weight:700}
 .mx{border:0;background:#eef0f2;width:32px;height:32px;border-radius:9px;cursor:pointer;font-size:14px}
 .modalbox textarea{flex:1;min-height:360px;margin-top:10px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;line-height:1.55;background:#fafbfc}
 .modalft{margin-top:14px;display:flex;gap:10px}
 /* photo grid */
 .pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(76px,1fr));gap:8px;max-height:230px;overflow:auto;padding:2px;user-select:none;-webkit-user-select:none}
 .pcell{position:relative;aspect-ratio:1;border-radius:9px;overflow:hidden;cursor:pointer;border:2px solid transparent}
 .pcell img{width:100%;height:100%;object-fit:cover;display:block}
 .pcell.sel{border-color:var(--green)}
 .dropzone{border:2px dashed #cdd3da;border-radius:11px;padding:18px;text-align:center;color:var(--sub);font-size:13px;cursor:pointer;margin-bottom:10px}
 .dropzone:hover,.dropzone.drag{border-color:var(--green);background:#f3fcf6;color:var(--green-d)}
 .draftlist{border:1px solid #e3e7ec;border-radius:10px;margin-bottom:10px;max-height:220px;overflow:auto}
 .draftlist .ditem{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 12px;border-bottom:1px solid #f0f2f5;cursor:pointer;font-size:13px}
 .draftlist .ditem:last-child{border-bottom:none}
 .draftlist .ditem:hover{background:#f3fcf6}
 .draftlist .ditem .dt{font-weight:600;color:#1f2937;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .draftlist .ditem .dd{color:var(--sub);font-size:11px;white-space:nowrap}
 .minibtn{font-size:12px;padding:5px 10px;border:1px solid #cdd3da;border-radius:8px;background:#fff;cursor:pointer;color:#374151}
 .minibtn:hover{border-color:var(--green);color:var(--green-d)}
 .minibtn:disabled{opacity:.55;cursor:default}
 .pmeta{display:none;margin-top:8px;border:1px solid #e5e7eb;border-radius:10px;padding:8px;max-height:360px;overflow:auto;user-select:none;-webkit-user-select:none}
 .pmeta.open{display:block}
 .pmhead{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px;font-size:12px;color:#374151}
 .pmboard{display:flex;flex-direction:column;gap:6px}
 .pmlane{border:1px solid #e5e7eb;border-radius:8px;padding:5px 6px;background:#fafbfc;cursor:pointer;transition:background .12s,border-color .12s}
 .pmlane.over{border-color:var(--green);background:#eafaf0;box-shadow:0 0 0 2px rgba(46,160,67,.18) inset}
 .pmlane.active{border-color:var(--green);background:#eafaf0}
 .pmlanehd{font-size:11px;color:#6b7280;font-weight:600;margin-bottom:4px;display:flex;align-items:center;gap:5px}
 .pmlane.sub{margin-left:18px;border-style:dashed;background:#fff}
 .pmtarget{margin-left:auto;background:var(--green);color:#fff;border-radius:9px;padding:0 7px;font-size:10px;font-weight:600}
 .pmsubbtn{margin-left:auto;border:0;background:#eef0f2;color:#4b5563;border-radius:7px;padding:1px 7px;font-size:10px;cursor:pointer}
 .pmsubbtn:hover{background:var(--green);color:#fff}
 .pmsubdel{border:0;background:transparent;color:#9ca3af;font-size:12px;cursor:pointer;padding:0 2px}
 .pmsubdel:hover{color:#d9534f}
 .pmcount{background:#e5e7eb;color:#374151;border-radius:9px;padding:0 6px;font-size:10px}
 .pmdrop{display:flex;flex-wrap:wrap;gap:6px;min-height:44px;align-items:flex-start}
 .pmtile{position:relative;width:54px;height:54px;border-radius:6px;cursor:pointer}
 .pmtile img{width:54px;height:54px;object-fit:cover;border-radius:6px;border:1px solid #e5e7eb;background:#fff;display:block}
 .pmtile.sel img{outline:2px solid var(--green);outline-offset:1px;border-color:var(--green)}
 .pmtile img:active{cursor:grabbing}
 .pmx{position:absolute;top:-6px;right:-6px;width:18px;height:18px;border-radius:50%;border:0;background:#4b5563;color:#fff;font-size:12px;line-height:1;cursor:pointer;display:none;align-items:center;justify-content:center;padding:0}
 .pmtile:hover .pmx{display:flex}
 /* 대표 썸네일 — ★ 지정 버튼·대표 리본·강조 테두리 */
 .pmstar{position:absolute;top:-6px;left:-6px;width:18px;height:18px;border-radius:50%;border:0;background:#fff;color:#cbd2d9;font-size:12px;line-height:1;cursor:pointer;display:none;align-items:center;justify-content:center;padding:0;box-shadow:0 1px 3px #0002}
 .pmstar:hover{color:#ffb400}
 .pmstar.on{display:flex;background:#ffb400;color:#fff}
 .pmtile:hover .pmstar{display:flex}
 .pmtile.thumb img{outline:2px solid #ffb400;outline-offset:1px;border-color:#ffb400}
 .pmribbon{position:absolute;bottom:0;left:0;right:0;background:#ffb400;color:#fff;font-size:9px;font-weight:800;text-align:center;line-height:14px;border-radius:0 0 6px 6px;letter-spacing:.5px}
 .pmthumbbar{display:flex;align-items:center;gap:9px;margin-bottom:9px;padding:8px 10px;border:1px solid #ffe2a6;background:#fffaf0;border-radius:9px;font-size:11.5px;color:#7a5b00}
 .pmthumbbar .pmthumblbl{font-weight:800;color:#b87b00;white-space:nowrap}
 .pmthumbbar img{width:34px;height:34px;object-fit:cover;border-radius:6px;border:1px solid #ffd47a}
 .pmthumbbar .pmempty{padding:0}
 .pmthumbbar .minibtn{margin-left:auto;white-space:nowrap}
 .pmadd{display:flex;align-items:center;justify-content:center;border:1px dashed #cdd3da;border-radius:8px;background:#fff;color:#6b7280;font-size:12px;padding:8px;cursor:pointer}
 .pmadd:hover{border-color:var(--green);color:var(--green-d)}
 .pmempty{font-size:11px;color:#9ca3af;padding:12px 4px}
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
 .doc hr.ctr{width:42%;margin-left:auto;margin-right:auto}
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
 .epgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
 .eprow{display:flex;align-items:center;gap:5px;margin-top:6px;font-size:11px;color:var(--sub)}
 .eprow label{display:flex;align-items:center;gap:3px;cursor:pointer}
 .eprow input[type=color]{width:26px;height:22px;padding:0;border:1px solid #d6dade;border-radius:5px;background:#fff;cursor:pointer}
 .eprow select{padding:3px 4px;border:1px solid #d6dade;border-radius:6px;font-size:11px;background:#fff;cursor:pointer;min-width:0}
 .epsel-font{flex:1 1 auto;max-width:100%}
 .epclr-off{opacity:.35}
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
 .mgroup{font-size:12px;color:var(--sub);font-weight:700;margin:16px 0 8px;display:flex;align-items:center;gap:7px}
 .mgrid{display:flex;flex-wrap:wrap;gap:9px}
 .mcard{position:relative;border:1.5px solid #d6dade;border-radius:12px;padding:12px 16px 11px;cursor:pointer;background:#fbfcfd;min-width:150px;transition:.12s}
 .mcard:hover{border-color:#9aa5b1;background:#fff}
 .mcard.on{border-color:var(--green);background:var(--green-soft);box-shadow:0 0 0 2px #03c75a22}
 .mcard.miss{opacity:.62}
 .mc-t{font-weight:700;font-size:14px;color:var(--ink)}
 .mc-s{font-size:11.5px;color:var(--sub);margin-top:3px}
 .mc-ck{display:inline-block;margin-top:7px;font-size:11px;color:var(--green-d);font-weight:800}
 .keychip{font-size:10.5px;padding:1px 7px;border-radius:5px;font-weight:700}
 .keychip.ok{background:var(--green-soft);color:var(--green-d)}
 .keychip.no{background:#fdecec;color:#d6453c}
 .logflags{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
 .lf{font-size:11px;padding:3px 8px;border-radius:6px;background:#eef1f4;color:#555}
 .lf.ok{background:#eafaf0;color:#02b350}.lf.no{background:#fdecef;color:#d9534f}
 .logpre{background:#f6f8fa;border:1px solid var(--line);border-radius:9px;padding:12px;font-size:11.5px;line-height:1.6;white-space:pre-wrap;max-height:300px;overflow:auto;font-family:ui-monospace,Menlo,monospace;margin:4px 0 8px}
 .logsum{cursor:pointer;font-size:12px;font-weight:600;padding:6px 0;color:#4b5563}
 /* 도움말 툴팁(ⓘ) — 긴 설명을 마우스 오버로 */
 .hint{display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;border-radius:50%;
   background:#dfe3e8;color:#fff;font-size:10px;font-weight:800;cursor:help;position:relative;vertical-align:middle;margin-left:4px;font-style:normal}
 .hint:hover{background:var(--green)}
 .hint::after{content:attr(data-tip);position:absolute;left:50%;bottom:calc(100% + 8px);transform:translateX(-50%);
   background:#1f2329;color:#fff;font-size:12px;font-weight:500;line-height:1.5;padding:9px 12px;border-radius:9px;
   width:max-content;max-width:260px;white-space:normal;text-align:left;box-shadow:0 6px 22px rgba(0,0,0,.22);
   opacity:0;visibility:hidden;transition:.12s;z-index:50;pointer-events:none}
 .hint::before{content:"";position:absolute;left:50%;bottom:calc(100% + 2px);transform:translateX(-50%);
   border:6px solid transparent;border-top-color:#1f2329;opacity:0;visibility:hidden;transition:.12s;z-index:50}
 .hint:hover::after,.hint:hover::before{opacity:1;visibility:visible}
 /* 협찬 섹션 — 토글 켤 때만 스티커 픽커·링크 펼침 */
 .togrow{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:20px;
   padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:#fbfcfd}
 .togrow .tl{font-size:13px;font-weight:700;color:#374151;display:flex;align-items:center}
 .sponbox{margin-top:10px;padding:14px;border:1px dashed #cdd3da;border-radius:12px;background:#fcfdfe}
 .sponpick{display:grid;grid-template-columns:repeat(auto-fill,minmax(64px,1fr));gap:8px;margin:8px 0 4px;max-height:180px;overflow:auto}
 .sponpick .spc{position:relative;aspect-ratio:1;border:2px solid transparent;border-radius:10px;overflow:hidden;cursor:pointer;background:#fafbfc}
 .sponpick .spc img{width:100%;height:100%;object-fit:contain;padding:4px}
 .sponpick .spc.sel{border-color:#7c4dff;background:#f4f0ff}
 .sponpick .spc.sel::after{content:"✓";position:absolute;top:2px;right:4px;color:#7c4dff;font-weight:800;font-size:13px}
 /* 보조 액션(복사/붙여넣기) — 한 줄에 작게 */
 .actrow{display:flex;gap:8px;margin-top:9px}
 .actrow .btn{padding:10px;font-size:12px}
 /* 카테고리 버튼 + 팝오버 */
 .catwrap{position:relative}
 .catbtn{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;padding:11px 13px;
   border:1px solid #d6dade;border-radius:11px;background:#fbfcfd;cursor:pointer;font-size:13px;color:var(--ink);font-weight:600}
 .catbtn:hover{border-color:#9aa5b1}
 .catbtn b{font-weight:700}
 .popover{position:absolute;top:calc(100% + 6px);left:0;right:0;z-index:60;background:#fff;border:1px solid var(--line);
   border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.18);padding:12px;max-height:340px;display:flex;flex-direction:column}
 .popover .catlist{overflow:auto;margin:-2px -4px 0}
 .popover .catopt{padding:8px 10px;border-radius:8px;cursor:pointer;font-size:13px;color:#374151}
 .popover .catopt:hover{background:#f3f6f9}
 .popover .catopt.on{background:var(--green-soft);color:var(--green-d);font-weight:700}
 /* 중앙 알림(오류·확인) — 화면 가운데 카드로 */
 .alertbg{position:fixed;inset:0;background:rgba(20,24,31,.5);z-index:10000;display:flex;align-items:center;justify-content:center;padding:24px;animation:tin .16s ease}
 .alertcard{background:#fff;border-radius:18px;width:min(420px,92vw);padding:26px 26px 22px;text-align:center;box-shadow:0 24px 70px rgba(0,0,0,.32)}
 .alertcard .ai{width:56px;height:56px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:28px;margin:0 auto 14px}
 .alertcard.err .ai{background:#fdecec}.alertcard.info .ai{background:#eaf2fb}.alertcard.ok .ai{background:var(--green-soft)}
 .alertcard .at{font-size:17px;font-weight:800;color:var(--ink);margin:0 0 8px;letter-spacing:-.2px}
 .alertcard .am{font-size:14px;font-weight:600;color:#5a626c;line-height:1.6;white-space:pre-wrap}
 .alertcard .ab{margin-top:20px;display:flex;gap:10px}
 .alertcard .ab .btn{padding:12px}
</style></head><body><div id=toasts></div><div id=bgtasks></div>
<svg width=0 height=0 style="position:absolute" aria-hidden=true><defs>
 <g id=i-write fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><path d="M4 20h4L18.5 9.5a2.1 2.1 0 0 0-3-3L5 17v3Z"/><path d="M13.5 6.5l3 3"/></g>
 <g id=i-sticker fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><circle cx=12 cy=12 r=9 /><path d="M8.5 14.5a4 4 0 0 0 7 0"/><circle cx=9 cy=10 r=.7 fill=currentColor stroke=none /><circle cx=15 cy=10 r=.7 fill=currentColor stroke=none /></g>
 <g id=i-format fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><path d="M12 3a9 9 0 1 0 0 18c1.1 0 1.8-.9 1.8-1.9 0-.5-.2-.9-.5-1.2-.3-.3-.4-.6-.4-1 0-1 .8-1.7 1.7-1.7H17a4 4 0 0 0 4-4c0-4.4-4-8-9-8Z"/><circle cx=7.5 cy=11.5 r=.9 fill=currentColor stroke=none /><circle cx=12 cy=7.8 r=.9 fill=currentColor stroke=none /><circle cx=16.4 cy=11.5 r=.9 fill=currentColor stroke=none /></g>
 <g id=i-prompt fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v4h4"/><path d="M9 13h6M9 16.5h4"/></g>
 <g id=i-settings fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><circle cx=12 cy=12 r=3 /><path d="M19.4 13a7.6 7.6 0 0 0 0-2l2-1.5-2-3.4-2.3 1a7.6 7.6 0 0 0-1.7-1l-.4-2.5h-4l-.4 2.5a7.6 7.6 0 0 0-1.7 1l-2.3-1-2 3.4 2 1.5a7.6 7.6 0 0 0 0 2l-2 1.5 2 3.4 2.3-1a7.6 7.6 0 0 0 1.7 1l.4 2.5h4l.4-2.5a7.6 7.6 0 0 0 1.7-1l2.3 1 2-3.4-2-1.5Z"/></g>
 <g id=i-model fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><rect x=7 y=7 width=10 height=10 rx=1.5 /><path d="M10 3v2M14 3v2M10 19v2M14 19v2M3 10h2M3 14h2M19 10h2M19 14h2"/></g>
 <g id=i-copy fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><rect x=8 y=3 width=8 height=4 rx=1 /><path d="M16 5h2v16H6V5h2"/><path d="M9 12h6M9 16h4"/></g>
 <g id=i-inbox fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><path d="M4 14v5h16v-5"/><path d="M12 4v9m0 0 3.5-3.5M12 13 8.5 9.5"/></g>
 <g id=i-search fill=none stroke-width=1.7 stroke-linecap=round stroke-linejoin=round><circle cx=11 cy=11 r=6 /><path d="m20 20-3.6-3.6"/></g>
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
<div id=phmodal class=modal style="display:none"><div class="modalbox phbox">
  <div class=modalhd><span>📷 사진 추가·분류</span><button class=mx id=phclose>✕</button></div>
  <div class=muted>사진을 올리고 → 글에 넣을 사진을 클릭·Shift로 선택 → 아래 칸으로 끌거나 선택 후 칸을 눌러 분류하세요.</div>
  <div class=dropzone id=dropzone>📷 사진을 끌어다 놓거나 <b>클릭해서 추가</b><input type=file id=fileinput accept="image/*" multiple hidden></div>
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
    <button type=button class="btn ghost" id=draftload style="white-space:nowrap">📥 임시저장에서 불러오기</button>
    <span class=muted id=draftstat></span>
  </div>
  <div class=draftlist id=draftlist style="display:none"></div>
  <div class=phscroll>
    <div class=pgrid id=pgrid></div>
    <div class=pmeta id=pmeta></div>
  </div>
  <div class=modalft><button class=btn id=phdone style="flex:1">완료</button></div>
</div></div>
<div id=catmodal class=modal style="display:none"><div class=modalbox style="width:min(420px,92vw)">
  <div class=modalhd><span id=cattitle>새 분류 추가</span><button class=mx id=catx>✕</button></div>
  <div class=muted id=catdesc></div>
  <input type=text id=catinput placeholder="예: 디저트, 음료" autocomplete=off style="margin-top:12px;padding:10px 12px;border:1px solid #cdd3da;border-radius:9px;font-size:14px;width:100%">
  <div class=modalft><button class=btn id=catok style="flex:1">추가</button><button class="btn ghost" id=catcancel style="flex:0 0 100px">취소</button></div>
</div></div>
<div id=npmodal class=modal style="display:none"><div class=modalbox style="width:min(420px,92vw)">
  <div class=modalhd><span>✏️ 새 글 시작</span><button class=mx id=npx>✕</button></div>
  <div class=muted>지금 작성 중인 메모·사진 선택·분류가 모두 비워집니다. 새 글을 시작할까요?</div>
  <div class=modalft><button class=btn id=npok style="flex:1">새 글 시작</button><button class="btn ghost" id=npcancel style="flex:0 0 100px">취소</button></div>
</div></div>
<div id=alerthost></div>
<aside class=side>
  <div class=brand><svg class=ic viewBox="0 0 24 24"><use href="#i-write"/></svg> 블로그 자동작성</div>
  <div class="nav on" data-view=write><svg class=ic viewBox="0 0 24 24"><use href="#i-write"/></svg> 글쓰기</div>
  <div class=nav data-view=stickers><svg class=ic viewBox="0 0 24 24"><use href="#i-sticker"/></svg> 스티커</div>
  <div class=nav data-view=format><svg class=ic viewBox="0 0 24 24"><use href="#i-format"/></svg> 서식</div>
  <div class=nav data-view=prompt><svg class=ic viewBox="0 0 24 24"><use href="#i-prompt"/></svg> 프롬프트</div>
  <div class=nav data-view=models><svg class=ic viewBox="0 0 24 24"><use href="#i-model"/></svg> 모델</div>
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
          <label class=f>수집 <span class=hint data-tip="선택 사항이에요. 맛집 플레이스 URL을 붙여넣거나 상품 검색어를 적으면 정보를 자동으로 수집합니다.">i</span></label>
          <input type=text id=srcval placeholder="맛집 플레이스 URL 붙여넣기, 또는 상품 검색어 입력">
          <div class=kindseg id=kindseg style="margin-top:8px">
            <button data-k=place class=on><span class=em>🍜</span>맛집</button>
            <button data-k=product><span class=em>🛍️</span>상품</button>
          </div>
          <div class=muted id=srchint style="margin-top:6px">링크를 붙여넣으면 알아서 맞춰져요 — 따로 안 골라도 됩니다.</div>
          <label class=f>경험 메모 <span class=hint data-tip="글의 중심이 되는 실제 경험을 자유롭게 적어주세요. 이 내용을 토대로 글이 작성됩니다.">i</span></label>
          <textarea id=memo placeholder="예: 비 오는 날 들렀는데 따뜻한 우동이 정말 맛있었어요. 사장님도 친절하셨고 분위기도 아늑했어요."></textarea>
          <label class=f>사진 <span class=muted id=psel></span></label>
          <button type=button class="btn ghost" id=photobtn style="width:100%;justify-content:center;gap:8px">📷 사진 추가·분류 <span class=muted id=photosum>사진 없음</span></button>
          <label class=f>문체 톤 <span class=hint data-tip="비우면 기본 톤으로 써요. 예: 친근한 반말로 / 담백하고 차분하게">i</span></label>
          <input type=text id=tone placeholder="예: 친근한 반말로">
          <label class=f>필수 키워드 <span class=hint data-tip="본문에 꼭 들어갈 키워드를 쉼표로 구분해 적어주세요. 비우면 안 씁니다. 예: 강남맛집, 데이트코스">i</span></label>
          <input type=text id=keywords placeholder="예: 강남맛집, 데이트코스 (쉼표로 구분)">
          <label class=f>최소 글자 수 <span class=hint data-tip="본문이 이 글자 수(공백 제외) 이상이 되도록 써요. 비우면 1500자가 적용됩니다.">i</span></label>
          <input type=number id=minchars placeholder="1500" min=0 step=100>
          <div class=togrow>
            <div class=tl>협찬 글 <span class=hint data-tip="켜면 즐겨찾기 스티커 중 고른 고지 스티커가 본문 맨 위에 들어가고, 아래 쿠팡파트너스 링크가 본문 중간중간 카드로 분산 삽입됩니다.">i</span></div>
            <div class=sw id=sponsw></div>
          </div>
          <div class=sponbox id=sponbox style="display:none">
            <div class=muted>본문 맨 위에 넣을 <b>협찬 고지 스티커</b>를 즐겨찾기에서 고르세요. (선택 안 해도 됨)</div>
            <div class=sponpick id=sponpick></div>
            <label class=f>쿠팡파트너스 링크 <span class=hint data-tip="한 줄에 하나씩. 본문 끝에 몰지 않고 중간중간 카드로 분산 삽입돼요. 보통 3개.">i</span></label>
            <textarea id=links placeholder="쿠팡파트너스 링크를 한 줄에 하나씩 붙여넣기 (보통 3개)" style="min-height:80px"></textarea>
          </div>
          <div style="margin-top:18px;display:flex;gap:8px"><button class=btn id=gen style="flex:1">초안 생성</button><button class="btn ghost" id=newpost style="flex:0 0 110px" title="입력·사진·분류를 비우고 새 글 시작">✏️ 새 글</button></div>
          <div class=actrow>
            <button class="btn ghost" id=export title="내 프롬프트와 입력 자료를 합쳐 복사 — 다른 챗봇에 붙여넣기"><svg class=ic viewBox="0 0 24 24"><use href="#i-copy"/></svg>프롬프트 복사</button>
            <button class="btn ghost" id=import title="다른 챗봇에서 받은 글을 붙여넣어 미리보기로"><svg class=ic viewBox="0 0 24 24"><use href="#i-inbox"/></svg>받아온 글 붙여넣기</button>
          </div>
          <div id=status></div>
        </div>
        <div class=card style="margin-top:16px">
          <h3>네이버에 보내기</h3>
          <div class=catwrap>
            <button class=catbtn id=catbtn><span>발행 카테고리: <b id=catlabel>선택 안 함</b></span><span style="color:var(--sub)">▾</span></button>
            <div class=popover id=catpop style="display:none">
              <div class=catlist id=catlist><div class=muted style="padding:8px 10px">아래 [불러오기]를 눌러주세요</div></div>
              <div style="display:flex;gap:8px;margin-top:8px;padding-top:10px;border-top:1px solid var(--line)">
                <button class="btn ghost" id=catload style="flex:1;padding:9px 13px">네이버에서 불러오기</button>
              </div>
              <div class=muted id=catstat style="margin-top:6px"></div>
            </div>
          </div>
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
    <p class=desc>★를 눌러 즐겨찾기에 넣으세요. 기본은 <b>즐겨찾기한 스티커만</b> 글에 쓰입니다.</p>
    <div class=stat id=ststat></div>
    <div class=togrow style="margin:0 0 14px;max-width:560px">
      <div class=tl>스티커 전체 사용 <span class=hint data-tip="끄면 즐겨찾기한 스티커만 글에 쓰입니다. 켜면 전체 스티커에서 상황에 맞게 골라 씁니다.">i</span></div>
      <div class=sw id=stickerall></div>
    </div>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap">
      <div class=seg style="width:280px" id=stfilter>
        <button data-f=fav class=on>⭐ 즐겨찾기</button>
        <button data-f=all>전체 둘러보기</button>
      </div>
      <button class="btn ghost" id=lblbtn style="width:auto;display:inline-flex;align-items:center;padding:8px 14px;font-size:12.5px;font-weight:600;border-radius:999px"><svg class=ic viewBox="0 0 24 24" style="margin-top:0;width:15px;height:15px"><use href="#i-search"/></svg>즐겨찾기 태그 분석</button>
      <span class="chip on" id=hidedef title="네이버 기본 제공 팩 숨기기"><span class=dot></span>기본 이모티콘 숨기기</span>
      <span class=muted id=lblstat></span>
    </div>
    <div id=stbody><div class=muted>불러오는 중…</div></div>
  </section>
  <!-- 서식 -->
  <section class="view format">
    <h2 class=title>서식</h2>
    <p class=desc>글에 들어갈 강조색·구분선·인용구를 미리 보고 고릅니다.</p>
    <div class=card><h3>강조색 <span class=muted style="font-weight:400">— 색마다 글자색·배경·폰트·크기를 직접 설정</span></h3><div id=emph><div class=muted>불러오는 중…</div></div></div>
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
  <!-- 모델 -->
  <section class="view models">
    <h2 class=title>모델</h2>
    <p class=desc>초안 작성에 쓸 모델을 고릅니다 — 내 컴퓨터(GPU)에서 돌리는 내장 모델, 또는 외부 API(Claude·GPT·Gemini).</p>
    <div class=card id=models><h3>모델</h3><div class=muted>불러오는 중…</div></div>
  </section>
  <!-- 설정 -->
  <section class="view settings">
    <h2 class=title>설정</h2>
    <p class=desc>글쓰기 규칙을 관리합니다.</p>
    <div class=card id=rules></div>
  </section>
</main>
<script>
// fetch 래퍼: 네트워크 단절(서버 꺼짐/재시작)을 'TypeError: Failed to fetch' 대신 친절한 메시지로
const _fetch=window.fetch.bind(window);
window.fetch=async(...a)=>{try{return await _fetch(...a);}
  catch(e){const m='서버에 연결할 수 없어요. 앱(서버)이 꺼졌거나 재시작 중일 수 있어요 — 잠시 후 새로고침하거나 다시 시도하세요.';toast(m,'err');throw new Error(m);}};
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let PHOTOS=[], SELP=[], PLAN=null;
// 알림: 오류(err)는 화면 가운데 카드로 크게, 완료/안내(ok/info)는 상단 토스트로 가볍게.
function toast(msg,kind='err',ms){
  if(kind==='err'){centerAlert(msg,'err');return;}
  if(ms==null)ms=kind==='ok'?3500:6000;
  const t=document.createElement('div');t.className='toast '+kind;
  const ic=kind==='ok'?'✅':kind==='info'?'ℹ️':'⚠️';
  t.innerHTML='<span class=ic>'+ic+'</span><span class=msg>'+String(msg).replace(/</g,'&lt;')+'</span><span class=x title="닫기">✕</span>';
  const close=()=>{if(t._gone)return;t._gone=true;t.classList.add('out');setTimeout(()=>t.remove(),180);};
  t.querySelector('.x').onclick=close;$('#toasts').appendChild(t);setTimeout(close,ms);}
// 화면 중앙 알림 카드(오류·확인). 유저가 직접 닫아야 함(꼭 봐야 하는 알림용).
function centerAlert(msg,kind='err'){
  const ic=kind==='ok'?'✅':kind==='info'?'ℹ️':'⚠️';
  const title=kind==='ok'?'완료됐어요':kind==='info'?'알려드려요':'문제가 발생했어요';
  const bg=document.createElement('div');bg.className='alertbg';
  bg.innerHTML=`<div class="alertcard ${kind}"><div class=ai>${ic}</div>
    <div class=at>${title}</div>
    <div class=am>${String(msg).replace(/</g,'&lt;')}</div>
    <div class=ab><button class=btn>확인</button></div></div>`;
  const close=()=>bg.remove();
  bg.querySelector('.btn').onclick=close;
  bg.onclick=e=>{if(e.target===bg)close();};
  document.addEventListener('keydown',function esc(e){if(e.key==='Escape'){close();document.removeEventListener('keydown',esc);}});
  $('#alerthost').appendChild(bg);bg.querySelector('.btn').focus();}
// 실측 경과시간 카운터 — 가짜 %가 아니라 '진짜로 얼마나 걸리는지'를 보여줌.
// requestAnimationFrame으로 0.1초 단위 표시가 바뀔 때만 갱신해 숫자가 자연스럽게 올라가고,
// 글자만 바꾸므로 스피너 회전이 끊기지 않는다. render(plainText, sec)로 갱신, stop()은 멈추고 총 초(소수1).
function elapsed(label, render){
  const t0=Date.now();
  const fmt=s=>s<10?s.toFixed(1):Math.round(s);
  let raf, last=null;
  const tick=()=>{
    const s=(Date.now()-t0)/1000, shown=fmt(s);
    if(shown!==last){ last=shown; render(`${label} ${shown}초 경과…`, s); }
    raf=requestAnimationFrame(tick);
  };
  tick();
  return {stop(){if(raf)cancelAnimationFrame(raf); return +((Date.now()-t0)/1000).toFixed(1);}};
}
// 컨테이너에 스피너를 한 번만 그리고 글자만 바꾸는 setter를 돌려준다(rAF로 자주 갱신해도 회전이 안 끊김).
function spinRow(el){
  el.innerHTML='<span class=loading><span class=spin></span></span> <span class=spintext></span>';
  const txt=el.querySelector('.spintext');
  return t=>{txt.textContent=t;};
}
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
    ?('<b>'+(k==='place'?'맛집':'상품')+'</b>으로 수집합니다.')
    :('입력을 보고 <b>'+(k==='place'?'맛집':'상품')+'</b>으로 자동 인식했어요. 직접 골라도 돼요.');}
// 강조색·구분선/인용구·스티커는 항상 켜둠(즐겨찾기/설정이 없으면 자동으로 안 들어감) — 토글 UI 제거.
const FMT={emphasis:true,structure:true,stickers:true,stickerAll:false,sponsored:false,sponsorSticker:'',hideDefault:true};
let CATEGORY='';
const LINKS=()=>($('#links').value||'').split('\n').map(s=>s.trim()).filter(Boolean);
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
// 협찬 토글 — 켜면 고지 스티커 픽커·쿠팡 링크 입력을 펼침
$('#sponsw').onclick=function(){FMT.sponsored=!FMT.sponsored;
  this.classList.toggle('on',FMT.sponsored);
  $('#sponbox').style.display=FMT.sponsored?'block':'none';
  if(FMT.sponsored)loadSponPicker();
  savePrefs();};
// 협찬 고지 스티커 픽커 — 즐겨찾기한 스티커를 불러와 하나 고름(다시 누르면 해제)
async function loadSponPicker(){
  const box=$('#sponpick');
  try{const c=await (await fetch('/api/catalog')).json();
    const favset=new Set(c.favorites);
    const favs=c.stickers.filter(s=>favset.has(s.ref));
    if(!favs.length){box.innerHTML='<div class=muted>즐겨찾기한 스티커가 없어요. [스티커] 탭에서 ★로 추가하세요.</div>';return;}
    box.innerHTML=favs.map(s=>`<div class="spc${s.ref===FMT.sponsorSticker?' sel':''}" data-ref="${s.ref}"><img loading=lazy src="/img?ref=${encodeURIComponent(s.ref)}"></div>`).join('');
  }catch(e){box.innerHTML='<div class=muted>스티커 로드 실패</div>';}
}
$('#sponpick').onclick=e=>{const c=e.target.closest('.spc'); if(!c)return;
  const ref=c.dataset.ref;
  FMT.sponsorSticker=(FMT.sponsorSticker===ref)?'':ref;
  $$('#sponpick .spc').forEach(x=>x.classList.toggle('sel',x.dataset.ref===FMT.sponsorSticker));
  savePrefs();};

function st(m,loading){const s=$('#status'); s.innerHTML=(loading?'<span class=spin></span>':'')+m;
  s.parentElement.classList.toggle('loading',!!loading);}

// 사진: PHOTOS=업로드 전체, SELP=분류함(보드)에 넣은 사진. 그리드(위)=아직 분류 안 한 더미(=PHOTOS−SELP).
function inboxPhotos(){ return PHOTOS.filter(p=>!SELP.includes(p)); }
function gridCell(path){
  const d=document.createElement('div'); d.className='pcell'+(PMSEL.has(path)?' sel':''); d.dataset.path=path;
  d.innerHTML=`<img loading=lazy src="/photo?path=${encodeURIComponent(path)}">`;
  d.onclick=(e)=>photoSel(path,e);
  d.onmousedown=(e)=>{ if(e.shiftKey) e.preventDefault(); };  // Shift+클릭 시 텍스트선택 방지
  return d;
}
function renderGrid(){
  const g=$('#pgrid'); if(!g)return; g.innerHTML='';
  const inbox=inboxPhotos();
  if(!inbox.length) g.innerHTML='<div class=muted style="grid-column:1/-1;padding:6px 2px">분류할 사진이 없어요. 위에서 추가하거나 아래 분류함에서 ×로 다시 꺼낼 수 있어요.</div>';
  else inbox.forEach(p=>g.appendChild(gridCell(p)));
  updatePhotoSummary();
}
async function loadPhotos(){
  try{ const ps=await (await fetch('/api/photos')).json(); PHOTOS=ps.map(p=>p.path); renderGrid(); }catch(e){}
}
function setupUpload(){const dz=$('#dropzone'), fi=$('#fileinput');
  dz.onclick=()=>fi.click(); fi.onchange=()=>handleFiles(fi.files);
  dz.ondragover=e=>{e.preventDefault();dz.classList.add('drag');};
  dz.ondragleave=()=>dz.classList.remove('drag');
  dz.ondrop=e=>{e.preventDefault();dz.classList.remove('drag');handleFiles(e.dataTransfer.files);};}
async function handleFiles(files){
  for(const f of files){ if(!f.type.startsWith('image/'))continue;
    const dataurl=await new Promise(r=>{const fr=new FileReader();fr.onload=()=>r(fr.result);fr.readAsDataURL(f);});
    try{const res=await fetch('/api/upload',{method:'POST',headers:{'content-type':'application/json'},
        body:JSON.stringify({filename:f.name,data:dataurl.split(',')[1]})});
      const d=await res.json(); if(d.path && !PHOTOS.includes(d.path)) PHOTOS.push(d.path); renderGrid();
    }catch(e){}
  }
  renderGrid();
}

// 네이버 임시저장 글에서 사진 불러오기: 목록 조회 → 글 선택 → 본문 사진 다운로드 → PHOTOS에 추가
let DRAFTBUSY=false;
function setupDraftImport(){
  const btn=$('#draftload'); if(!btn) return;
  btn.onclick=async()=>{
    const list=$('#draftlist'), stat=$('#draftstat');
    if(list.style.display==='block'){ list.style.display='none'; return; }  // 토글로 닫기
    if(DRAFTBUSY) return; DRAFTBUSY=true;
    const el=elapsed('네이버에서 목록 불러오는 중…', spinRow(stat));
    try{
      const r=await fetch('/api/drafts',{method:'POST'});
      const d=await r.json();
      if(!r.ok){ throw new Error(d.error||'목록을 불러오지 못했어요'); }
      const sec=el.stop();
      const drafts=d.drafts||[];
      if(!drafts.length){ stat.textContent=`임시저장된 글이 없어요. (${sec}초)`; DRAFTBUSY=false; return; }
      stat.textContent=`${drafts.length}건 (${sec}초) — 사진을 가져올 글을 선택하세요`;
      list.innerHTML='';
      drafts.forEach(dr=>{
        const row=document.createElement('div'); row.className='ditem';
        row.innerHTML=`<span class=dt>${(dr.title||'(제목 없음)')}</span><span class=dd>${dr.date||''}</span>`;
        row.onclick=()=>importDraft(dr.idx, dr.title);
        list.appendChild(row);
      });
      list.style.display='block';
    }catch(e){ el.stop(); stat.textContent='불러오기 실패'; toast('임시저장 목록을 못 불러왔어요 — '+e.message,'err'); }
    DRAFTBUSY=false;
  };
}
async function importDraft(idx, title){
  if(DRAFTBUSY) return; DRAFTBUSY=true;
  const stat=$('#draftstat');
  const el=elapsed(`"${title}" 사진 가져오는 중…`, spinRow(stat));
  try{
    const r=await fetch('/api/drafts/import',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({idx})});
    const d=await r.json();
    if(!r.ok){ throw new Error(d.error||'가져오기 실패'); }
    const sec=el.stop();
    const paths=d.paths||[];
    // 기존 사진·분류 상태를 모두 비우고 불러온 사진으로 교체
    PHOTOS=paths.slice(); SELP=[]; PHOTOMETA={}; THUMB=null;
    PMACTIVE=undefined; PMSEL=new Set(); PMANCHOR=null; SUBCATS={}; PMDRAG=null;
    renderGrid(); renderPmeta(); updatePhotoSummary();
    $('#draftlist').style.display='none';
    stat.textContent = paths.length? `${paths.length}장 불러옴 (${sec}초) — 아래에서 분류하세요` : '가져올 사진이 없는 글이에요';
    if(paths.length) toast(`${paths.length}장 불러왔어요 (기존 사진 교체됨)`,'ok');
  }catch(e){ el.stop(); stat.textContent='가져오기 실패'; toast('사진을 못 가져왔어요 — '+e.message,'err'); }
  DRAFTBUSY=false;
}

// 사진 분류·캡션 (수동 + ✨ AI 자동 추천). 결과는 PHOTOMETA(경로→{label,caption})에 저장.
let PHOTOMETA={}, PHOTO_CATS={}, THUMB=null;  // THUMB=대표 썸네일 경로(글 맨 위 첫 사진, 최대 1장)
async function loadPhotoCats(){ try{PHOTO_CATS=await (await fetch('/api/photo_categories')).json();}catch(e){} }
function curCats(){ return PHOTO_CATS[SRCKIND]||PHOTO_CATS.place||['외관','내부','메뉴판','음식','영수증','기타']; }
function photoMetaForSel(){ const o={}; SELP.forEach(p=>{const m=PHOTOMETA[p]||{}; const e={};
  if(m.label)e.label=m.label; if(m.caption)e.caption=m.caption; if(p===THUMB)e.thumbnail=true;
  if(e.label||e.caption||e.thumbnail)o[p]=e; }); return o; }
function setThumb(path){ THUMB=(THUMB===path?null:path); renderGrid(); renderPmeta(); updatePhotoSummary(); }
function updatePhotoSummary(){
  const n=SELP.length;
  const ps=$('#psel'); if(ps) ps.textContent = n? `${n}장` : '';
  const su=$('#photosum'); if(su) su.textContent = n? `${n}장 선택됨` : '사진 없음';
}
function openPhotoModal(){
  const m=$('#phmodal'); if(!m)return;
  m.style.display='flex';
  const box=$('#pmeta'); if(box){ box.classList.add('open'); }
  renderGrid(); renderPmeta();
}
function closePhotoModal(){ const m=$('#phmodal'); if(m)m.style.display='none'; updatePhotoSummary(); }
// PMACTIVE: 활성 칸(undefined=초기→첫칸 외관, 문자열=활성, null=해제). PMSEL=보이는 선택(더미·보드 공통). SUBCATS=세션 세부분류.
let PMDRAG=null, PMSEL=new Set(), PMANCHOR=null, PMACTIVE=undefined, SUBCATS={}, CATCB=null;
function baseCats(){ return curCats(); }  // 영구 분류(config)
function allCats(){ const o=[]; baseCats().forEach(c=>{ o.push(c); (SUBCATS[c]||[]).forEach(s=>{ if(!o.includes(s))o.push(s); }); }); return o; }
function pmBuckets(){ const o=[]; baseCats().forEach(c=>{ o.push({key:c,name:c,sub:false}); (SUBCATS[c]||[]).forEach(s=>o.push({key:s,name:s,sub:true,parent:c})); }); return o; }
function pmBucketOf(path){ const cats=allCats(), lb=(PHOTOMETA[path]||{}).label||''; return cats.includes(lb)?lb:(baseCats()[0]||''); }
function pmAssign(path,key){ (PHOTOMETA[path]=PHOTOMETA[path]||{}).label=key; }
function pmEnsureDefaults(){ const def=baseCats()[0]||''; SELP.forEach(p=>{const m=(PHOTOMETA[p]=PHOTOMETA[p]||{}); if(!m.label)m.label=def;}); }
// 사진 클릭(더미·보드 공통): 단일=활성 칸으로 즉시 / Shift=보이는 범위 선택(이동X, 업로드 순서) / ⌘·Ctrl=개별 토글
function photoSel(path,ev){
  if(ev.shiftKey){  // Shift는 항상 '선택'만(즉시 이동 안 함). 시작점도 Shift로 가능.
    if(PMANCHOR){
      const a=PHOTOS.indexOf(PMANCHOR), b=PHOTOS.indexOf(path);
      if(a>=0&&b>=0){ const lo=Math.min(a,b),hi=Math.max(a,b), remove=PMSEL.has(path);
        for(let i=lo;i<=hi;i++){ const p=PHOTOS[i]; if(!p)continue; if(remove)PMSEL.delete(p); else PMSEL.add(p); } }
      else PMSEL.add(path);
    } else PMSEL.add(path);
    PMANCHOR=path;
  } else if(ev.metaKey||ev.ctrlKey){ if(PMSEL.has(path))PMSEL.delete(path); else PMSEL.add(path); PMANCHOR=path; }
  else {
    if(PMACTIVE!=null){ if(!SELP.includes(path))SELP.push(path); pmAssign(path,PMACTIVE); PMSEL.clear(); }
    else PMSEL=new Set([path]);
    PMANCHOR=path;
  }
  renderGrid(); renderPmeta();
}
function laneClick(key){  // 칸 클릭: 선택한 사진 있으면 그 칸으로 이동, 없으면 활성 토글
  if(PMSEL.size){
    const moved=[...PMSEL];
    moved.forEach(p=>{ if(!SELP.includes(p))SELP.push(p); pmAssign(p,key); });
    PMSEL=new Set(); PMANCHOR=null; PMACTIVE=key;
    if(moved.length>1){  // 시프트로 여러 장 담았으면 → 다음 더미 사진을 자동 선택해 이어서 처리
      const lastIdx=Math.max(...moved.map(p=>PHOTOS.indexOf(p)));
      const nxt=PHOTOS.find((p,i)=>i>lastIdx && !SELP.includes(p));
      if(nxt){ PMSEL.add(nxt); PMANCHOR=nxt; }
    }
  } else PMACTIVE=(PMACTIVE===key?null:key);
  renderGrid(); renderPmeta();
}
function openCatModal(title,desc,cb){
  CATCB=cb; $('#cattitle').textContent=title; $('#catdesc').textContent=desc||'';
  const inp=$('#catinput'); inp.value=''; $('#catmodal').style.display='flex'; setTimeout(()=>inp.focus(),30);
}
function closeCatModal(){ $('#catmodal').style.display='none'; CATCB=null; }
function catSubmit(){ const v=$('#catinput').value.trim(); if(!v){toast('이름을 입력하세요.','info');return;} const cb=CATCB; closeCatModal(); if(cb)cb(v); }
function addCategory(){  // 영구 분류 추가(파일 저장)
  openCatModal('새 분류 추가','이 리뷰 타입에 계속 쓸 분류예요(저장됨).', async name=>{
    if(allCats().includes(name)){ toast('이미 있는 분류예요.','info'); return; }
    try{ const r=await fetch('/api/photo_categories',{method:'POST',headers:{'content-type':'application/json'},
        body:JSON.stringify({reviewType:SRCKIND,category:name})});
      const d=await r.json(); if(!r.ok){ toast('분류 추가 실패: '+(d.error||''),'err'); return; }
      PHOTO_CATS=d; renderPmeta(); toast('"'+name+'" 분류를 추가했어요.','ok');
    }catch(e){ toast('분류 추가 오류: '+e,'err'); }
  });
}
function addSub(parent){  // 세부분류 추가(이 글에만, 저장 안 함)
  openCatModal('세부분류 추가', "'"+parent+"' 아래 세부분류 — 이번 글에만(새 글 시작하면 사라짐)", name=>{
    if(allCats().includes(name)){ toast('이미 있는 분류예요.','info'); return; }
    (SUBCATS[parent]=SUBCATS[parent]||[]).push(name); PMACTIVE=name; renderPmeta(); toast('세부분류 "'+name+'" 추가(이 글에만)','ok');
  });
}
function removeSub(parent,sub){
  SUBCATS[parent]=(SUBCATS[parent]||[]).filter(s=>s!==sub);
  SELP.forEach(p=>{ if((PHOTOMETA[p]||{}).label===sub) pmAssign(p,parent); });  // 그 세부 사진은 부모 칸으로
  if(PMACTIVE===sub)PMACTIVE=parent; renderPmeta();
}
function pmTile(path){
  const isT=path===THUMB;
  return `<div class="pmtile${PMSEL.has(path)?' sel':''}${isT?' thumb':''}" data-path="${esc(path)}">`
    +`<img draggable=true src="/photo?path=${encodeURIComponent(path)}">`
    +`<button type=button class="pmstar${isT?' on':''}" title="${isT?'대표 썸네일 해제':'대표 썸네일로 지정 — 글 맨 위 첫 사진'}">★</button>`
    +(isT?'<span class=pmribbon>대표</span>':'')
    +`<button type=button class=pmx title="분류함에서 빼기(다시 더미로)">×</button></div>`;
}
function renderPmeta(){
  if(PMACTIVE===undefined) PMACTIVE = baseCats()[0]||null;
  if(PMACTIVE!=null && !allCats().includes(PMACTIVE)) PMACTIVE=null;
  pmEnsureDefaults();
  [...PMSEL].forEach(p=>{ if(!PHOTOS.includes(p))PMSEL.delete(p); });
  if(THUMB && !SELP.includes(THUMB)) THUMB=null;  // 분류함에서 빠진 사진은 썸네일 해제
  const tbody = (THUMB)
    ? `<img src="/photo?path=${encodeURIComponent(THUMB)}"><span>이 사진이 글 맨 위 <b>첫 사진</b>으로 들어가요</span><button type=button class=minibtn id=thumbclr>해제</button>`
    : `<span class=pmempty>사진의 <b>★</b>를 눌러 <b>대표 썸네일</b>을 정하세요 — 글 맨 위 첫 사진이 됩니다</span>`;
  let h=`<div class=pmthumbbar><span class=pmthumblbl>⭐ 대표 썸네일</span>${tbody}</div>`
    +'<div class=pmhead><span>'
    + (PMSEL.size
        ? `<b>${PMSEL.size}장</b> 선택됨 — 담을 칸을 클릭(또는 드래그)`
        : (PMACTIVE!=null
            ? `<b>${esc(PMACTIVE)}</b> 칸 활성 — 사진 클릭하면 담겨요 · Shift로 여러 장 선택 후 칸 클릭`
            : '사진 클릭/Shift로 선택 → 담을 칸 클릭. (칸을 클릭하면 활성=클릭으로 담기)'))
    + '</span><button type=button class=minibtn id=aibtn>✨ AI 자동 추천</button></div>';
  h+='<div class=pmboard>'+pmBuckets().map(b=>{
    const items=SELP.filter(p=>pmBucketOf(p)===b.key);
    const inner=items.length?items.map(pmTile).join(''):'<span class=pmempty>여기로 끌어다 놓기</span>';
    const act=(b.key===PMACTIVE)?' active':'';
    const badge=`<span class=pmcount>${items.length}</span>${act?'<span class=pmtarget>담는 중</span>':''}`;
    const hd = b.sub
      ? `<div class=pmlanehd>↳ ${esc(b.name)} ${badge}<button type=button class=pmsubdel data-parent="${esc(b.parent)}" data-sub="${esc(b.name)}" title="세부분류 삭제">×</button></div>`
      : `<div class=pmlanehd>${esc(b.name)} ${badge}<button type=button class=pmsubbtn data-cat="${esc(b.key)}" title="세부분류 추가(이 글에만)">+세부</button></div>`;
    return `<div class="pmlane${b.sub?' sub':''}${act}" data-key="${esc(b.key)}">${hd}<div class=pmdrop>${inner}</div></div>`;
  }).join('')
   + '<button type=button class=pmadd id=pmadd>+ 새 분류 추가</button>'
   + '</div>';
  const box=$('#pmeta'); box.innerHTML=h;
  $('#aibtn').onclick=runAiCaption;
  $('#pmadd').onclick=addCategory;
  $$('#pmeta .pmsubbtn').forEach(btn=>{ btn.onclick=e=>{ e.stopPropagation(); addSub(btn.dataset.cat); }; });
  $$('#pmeta .pmsubdel').forEach(btn=>{ btn.onclick=e=>{ e.stopPropagation(); removeSub(btn.dataset.parent,btn.dataset.sub); }; });
  $$('#pmeta .pmlane[data-key]').forEach(l=>{
    l.onclick=()=>laneClick(l.dataset.key);
    l.ondragover=e=>{e.preventDefault(); e.dataTransfer.dropEffect='move'; l.classList.add('over');};
    l.ondragleave=()=>l.classList.remove('over');
    l.ondrop=e=>{e.preventDefault(); l.classList.remove('over');
      const set=(PMDRAG&&PMDRAG.length)?PMDRAG:[]; PMDRAG=null;
      if(!set.length)return;
      set.forEach(p=>{ if(!SELP.includes(p))SELP.push(p); pmAssign(p,l.dataset.key); }); PMSEL=new Set(); PMANCHOR=null;
      renderGrid(); renderPmeta();
    };
  });
  $$('#pmeta .pmtile img').forEach(img=>{
    const path=img.closest('.pmtile').dataset.path;
    img.onmousedown=e=>{ if(e.shiftKey) e.preventDefault(); };
    img.onclick=e=>{ e.stopPropagation(); photoSel(path,e); };
    img.ondragstart=e=>{ PMDRAG=(PMSEL.has(path)&&PMSEL.size)?[...PMSEL]:[path];
      e.dataTransfer.effectAllowed='move'; try{e.dataTransfer.setData('text/plain',path);}catch(_){}};
    img.ondragend=()=>{PMDRAG=null; $$('#pmeta .pmlane').forEach(l=>l.classList.remove('over'));};
  });
  $$('#pmeta .pmtile .pmx').forEach(x=>{
    x.onclick=e=>{ e.stopPropagation();
      const path=x.closest('.pmtile').dataset.path, i=SELP.indexOf(path);
      if(i>=0)SELP.splice(i,1); PMSEL.delete(path); if(THUMB===path)THUMB=null;
      renderGrid(); renderPmeta();
    };
  });
  $$('#pmeta .pmtile .pmstar').forEach(s=>{
    s.onclick=e=>{ e.stopPropagation(); setThumb(s.closest('.pmtile').dataset.path); };
  });
  const tc=$('#thumbclr'); if(tc) tc.onclick=()=>{ THUMB=null; renderGrid(); renderPmeta(); };
}
function newPost(){ $('#npmodal').style.display='flex'; }  // 새 글 시작 확인 모달
function closeNP(){ $('#npmodal').style.display='none'; }
function doNewPost(){  // 새 글: 입력·사진선택·분류·세부분류 비우기
  closeNP();
  $('#memo').value=''; $('#srcval').value=''; if(typeof setKind==='function')setKind('place',false);
  SELP=[]; PHOTOMETA={}; THUMB=null; PMACTIVE=undefined; PMSEL=new Set(); PMANCHOR=null; SUBCATS={}; PMDRAG=null;
  PLAN=null; const sv=$('#save'); if(sv)sv.disabled=true;
  const pv=$('#preview'); if(pv){ pv.className='doc empty'; pv.innerHTML='왼쪽에서 메모를 쓰고 [초안 생성]을 누르세요.'; }
  loadPhotos(); renderPmeta(); updatePhotoSummary();
  toast('새 글을 시작했어요.','ok');
}
async function runAiCaption(){
  const btn=$('#aibtn'); if(!btn)return; btn.disabled=true; const old=btn.textContent;
  const el=elapsed(`사진 ${SELP.length}장 분석 중…`, t=>btn.textContent=t);
  try{
    const body={memo:$('#memo').value,srcval:$('#srcval').value,kind:SRCKIND,photos:SELP,reviewType:SRCKIND};
    const r=await fetch('/api/photos/caption',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok){throw new Error(d.error||'알 수 없는 오류');}
    const sec=el.stop();
    (d.photos||[]).forEach(p=>{PHOTOMETA[p.path]={label:p.label||'',caption:p.caption||''};});
    renderPmeta(); toast(`사진 자동 분석 완료! (${sec}초) 검토·수정 후 생성하세요.`,'ok');
  }catch(e){el.stop(); toast('사진 자동 분석 실패 — '+e.message,'err');}
  finally{btn.disabled=false; btn.textContent=old;}
}

let GENTIMER=null, GENT0=0;
const GENCHARS=['🐥','✍️','🐣','💭','📝'];
const GENMSGS=[[0,'메모를 읽는 중…'],[18,'글을 쓰는 중…'],[50,'문장을 다듬는 중…'],[78,'강조·서식 입히는 중…'],[92,'거의 다 됐어요!']];
function genLoading(){
  $('#preview').classList.add('empty');
  $('#preview').innerHTML=`<div class=genload><div class=genchar id=genchar>🐥</div>
    <div class=genmsg id=genmsg>메모를 읽는 중…</div>
    <div class=genbar><div class=genfill id=genfill></div></div>
    <div class=genpct id=genpct>0%</div>
    <div class=gensub id=gensub>로컬 AI가 직접 글을 써요 · 보통 30~60초</div></div>`;
  let pct=0, ci=0; GENT0=Date.now();
  GENTIMER=setInterval(()=>{
    pct+=Math.max(0.4,(96-pct)*0.035); if(pct>96)pct=96;
    const fl=$('#genfill'); if(!fl){clearInterval(GENTIMER);return;}
    fl.style.width=pct+'%'; $('#genpct').textContent=Math.floor(pct)+'%';
    const m=GENMSGS.filter(x=>pct>=x[0]).pop(); if(m)$('#genmsg').textContent=m[1];
    ci++; $('#genchar').textContent=GENCHARS[ci%GENCHARS.length];
    const sb=$('#gensub'); if(sb)sb.textContent=`로컬 AI가 직접 글을 써요 · ${Math.round((Date.now()-GENT0)/1000)}초 경과`;
  },700);
}
function genDone(ok){ if(GENTIMER)clearInterval(GENTIMER);
  const sec=GENT0?((Date.now()-GENT0)/1000).toFixed(1):null;
  if(ok){const fl=$('#genfill'); if(fl){fl.style.width='100%'; $('#genpct').textContent='100%';}
    const sb=$('#gensub'); if(sb&&sec)sb.textContent=`완성! ${sec}초 걸렸어요`;} }
$('#gen').onclick=async()=>{
  if(!$('#memo').value.trim()){st('경험 메모를 입력하세요.');return;}
  $('#gen').disabled=true;$('#save').disabled=true; st('생성 중…',true); genLoading();
  try{
    const body={memo:$('#memo').value,srcval:$('#srcval').value,kind:SRCKIND,photos:SELP,photoMeta:photoMetaForSel(),tone:$('#tone').value,keywords:$('#keywords').value,minChars:$('#minchars').value,
      emphasis:FMT.emphasis,structure:FMT.structure,stickers:FMT.stickers,stickerAll:FMT.stickerAll,sponsored:FMT.sponsored,sponsorSticker:FMT.sponsorSticker,links:LINKS(),rules:RULES};
    const r=await fetch('/api/generate',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok){genDone(false); $('#preview').innerHTML='<div class=genload><div style="font-size:40px">😢</div><div class=genmsg>생성 실패</div><div class=gensub>'+(d.error||'')+'</div></div>'; st('실패'); toast('초안 생성 실패: '+(d.error||'알 수 없는 오류'),'err'); return;}
    genDone(true); PLAN=d; setTimeout(()=>renderPreview(d),350); st('생성 완료. 검토 후 임시저장하세요.'); toast('초안 생성 완료! 오른쪽 미리보기를 확인하세요.','ok'); $('#save').disabled=false;
    if(d.debug)showLog(d.debug);
  }catch(e){genDone(false); st('오류: '+e); toast('초안 생성 오류: '+e,'err');}finally{$('#gen').disabled=false;}
};
// 프롬프트 내보내기: 모달 안에서 진행바 + 실제 단계 메시지 보여주고, 합쳐진 프롬프트 표시·복사
let EXPTIMER=null;
const EXPCHARS=['🧩','✍️','🔗','📋','💭'];
function expLoading(on){
  $('#ploading').style.display=on?'block':'none'; $('#pcontent').style.display=on?'none':'block';
  if(EXPTIMER){clearInterval(EXPTIMER);EXPTIMER=null;}
  if(on){$('#pmodal').style.display='flex'; let pct=0,ci=0;
    $('#pfill').style.width='0%'; $('#ppct').textContent='0%'; $('#pmsg').textContent='자료를 준비하는 중…';
    // 진행바·스피너만 부드럽게 굴리고, 문구는 서버가 보내는 실제 단계로 갱신(expStage)
    EXPTIMER=setInterval(()=>{pct+=Math.max(1,(96-pct)*0.08); if(pct>96)pct=96;
      const fl=$('#pfill'); if(!fl){clearInterval(EXPTIMER);return;}
      fl.style.width=pct+'%'; $('#ppct').textContent=Math.floor(pct)+'%';
      ci++; $('#pchar').textContent=EXPCHARS[ci%EXPCHARS.length];},650);
  }else{const fl=$('#pfill'); if(fl)fl.style.width='100%'; $('#ppct').textContent='100%';}
}
function expStage(msg){const m=$('#pmsg'); if(m&&msg)m.textContent=msg;}
$('#export').onclick=async()=>{
  if(!$('#memo').value.trim()){toast('경험 메모를 먼저 입력하세요.','info');return;}
  $('#export').disabled=true; expLoading(true);
  try{
    const body={memo:$('#memo').value,srcval:$('#srcval').value,kind:SRCKIND,photos:SELP,photoMeta:photoMetaForSel(),tone:$('#tone').value,keywords:$('#keywords').value,minChars:$('#minchars').value,
      emphasis:FMT.emphasis,structure:FMT.structure,stickers:FMT.stickers,stickerAll:FMT.stickerAll,sponsored:FMT.sponsored,sponsorSticker:FMT.sponsorSticker,links:LINKS(),rules:RULES};
    const r=await fetch('/api/export-prompt',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    if(!r.body){closePM(); toast('프롬프트 생성 실패','err');return;}
    // NDJSON 스트림: {stage} 단계 갱신, 마지막에 {prompt} 또는 {error}
    const reader=r.body.getReader(), dec=new TextDecoder(); let buf='', prompt=null, err=null;
    for(;;){const {value,done}=await reader.read();
      if(value){buf+=dec.decode(value,{stream:true}); let nl;
        while((nl=buf.indexOf('\n'))>=0){const line=buf.slice(0,nl).trim(); buf=buf.slice(nl+1);
          if(!line)continue; let ev; try{ev=JSON.parse(line);}catch(_){continue;}
          if(ev.stage)expStage(ev.stage); if(ev.prompt!=null)prompt=ev.prompt; if(ev.error)err=ev.error;}}
      if(done)break;}
    if(err){closePM(); toast('프롬프트 생성 실패: '+err,'err');return;}
    if(prompt==null){closePM(); toast('프롬프트 생성 실패','err');return;}
    $('#ptext').value=prompt; expLoading(false);
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
    const body={text,srcval:$('#srcval').value,kind:SRCKIND,photos:SELP,photoMeta:photoMetaForSel(),emphasis:FMT.emphasis,structure:FMT.structure,stickers:FMT.stickers,stickerAll:FMT.stickerAll,sponsored:FMT.sponsored,sponsorSticker:FMT.sponsorSticker,links:LINKS()};
    const r=await fetch('/api/import-draft',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok){toast('가져오기 실패: '+(d.error||''),'err');return;}
    closeIM(); PLAN=d; renderPreview(d); st('받아온 글을 미리보기에 반영했어요. 검토 후 임시저장하세요.'); toast('받아온 글을 가져왔어요! 검토 후 임시저장하세요.','ok'); $('#save').disabled=false;
    if(d.debug)showLog(d.debug);
  }catch(e){toast('가져오기 오류: '+e,'err');}finally{$('#iapply').disabled=false;}
};
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
// 단락 정렬(left/center/right/justify) — 에디터에 실제 적용되는 align을 미리보기에도 반영
function alignStyle(b){return b&&b.align&&b.align!=='left'?`text-align:${b.align};`:'';}
function renderText(b){let h=esc(b.text);
  (b.emphases||[]).forEach(e=>{const stl=(e.text_color?`color:${e.text_color};`:'')+(e.background_color?`background:${e.background_color};`:'');
    h=h.replace(esc(e.text),`<em class=hl style="${stl}">${esc(e.text)}</em>`);});
  return `<p class=tx style="${alignStyle(b)}">${h}</p>`;}
function renderPreview(d){
  let h=`<h1>${esc(d.title)||'(제목 없음)'}</h1>`;
  for(const b of d.blocks){
    if(b.kind==='text')h+=renderText(b);
    else if(b.kind==='divider')h+=`<hr${b.align==='center'?' class=ctr':''}>`;
    else if(b.kind==='quote')h+=`<div class=q style="${alignStyle(b)}">${esc(b.text)}</div>`;
    else if(b.kind==='sticker')h+=`<img class=st src="/img?ref=${encodeURIComponent(b.sticker_ref)}">`;
    else if(b.kind==='image')h+=`<div class=ph>🖼 ${esc(b.image_label)} <small>${esc(b.image_path)}</small></div>`;
    else if(b.kind==='link')h+=`<div class=ph>🔗 링크 카드 <small>${esc(b.link_url)}</small></div>`;
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
// 카테고리: 자리 차지 않게 작은 버튼+팝오버. 고른 값(CATEGORY)은 기억(prefs).
function setCategory(name){CATEGORY=name||'';
  $('#catlabel').textContent=CATEGORY||'선택 안 함';}
function fillCategories(cats){
  const opts='<div class="catopt'+(CATEGORY?'':' on')+'" data-v="">— 선택 안 함 —</div>'+cats.map(c=>
    `<div class="catopt${c.name===CATEGORY?' on':''}" data-v="${esc(c.name)}">${'　'.repeat(c.depth||0)}${c.depth?'└ ':''}${esc(c.name)}</div>`).join('');
  $('#catlist').innerHTML=opts;}
async function loadCategories(){try{const d=await (await fetch('/api/categories')).json();
  if(d.categories&&d.categories.length){fillCategories(d.categories); $('#catstat').textContent=`저장된 ${d.categories.length}개 · 갱신하려면 [네이버에서 불러오기]`;}
}catch(e){}}
function catpopOpen(on){$('#catpop').style.display=on?'flex':'none';}
$('#catbtn').onclick=e=>{e.stopPropagation(); catpopOpen($('#catpop').style.display==='none');};
$('#catpop').onclick=e=>e.stopPropagation();
document.addEventListener('click',()=>catpopOpen(false));
$('#catlist').onclick=e=>{const o=e.target.closest('.catopt'); if(!o)return;
  setCategory(o.dataset.v);
  $$('#catlist .catopt').forEach(x=>x.classList.toggle('on',x===o));
  catpopOpen(false); savePrefs();};
$('#catload').onclick=async()=>{
  $('#catload').disabled=true;
  const el=elapsed('네이버에서 카테고리 불러오는 중…', spinRow($('#catstat')));
  try{const r=await fetch('/api/categories',{method:'POST'}); const d=await r.json();
    if(!r.ok){throw new Error(d.error||'알 수 없는 오류');}
    const sec=el.stop();
    fillCategories(d.categories); $('#catstat').textContent=`카테고리 ${d.categories.length}개 불러와 저장됨 (${sec}초)`; toast(`카테고리 ${d.categories.length}개를 불러와 저장했어요.`,'ok');
  }catch(e){el.stop(); $('#catstat').textContent='실패'; toast('카테고리 불러오기 실패 — '+e.message,'err');}finally{$('#catload').disabled=false;}
};
// 백그라운드 작업 칩 — 코너에 스피너+경과시간을 띄우고, done()이 부드럽게 닫는다.
function bgTask(label){
  const el=document.createElement('div'); el.className='bgtask';
  el.innerHTML='<span class=spin></span><span class=bgtext></span>';
  const txt=el.querySelector('.bgtext');
  $('#bgtasks').appendChild(el);
  const e=elapsed(label, t=>txt.textContent=t);
  return {done(){const sec=e.stop(); el.classList.add('out'); setTimeout(()=>el.remove(),200); return sec;}};
}
let BGSAVE=false;
$('#save').onclick=async()=>{if(!PLAN)return;
  if(BGSAVE){toast('이미 백그라운드에서 임시저장 중이에요. 잠시만요.','info');return;}
  BGSAVE=true; $('#save').disabled=true;
  st('백그라운드에서 임시저장 중… 다른 작업을 계속하셔도 돼요.');
  const task=bgTask('네이버에 임시저장 중…');
  try{const r=await fetch('/api/publish',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({category:CATEGORY})});
    const d=await r.json();
    if(!r.ok){throw new Error(d.error||'알 수 없는 오류');}
    const sec=task.done();
    st(`임시저장 완료 ✓ ${sec}초 (네이버 글쓰기 › 저장 목록)`); toast('임시저장 완료! 네이버 글쓰기 › 저장 목록에서 확인하세요.','ok');
  }catch(e){task.done(); st('임시저장 실패'); toast('임시저장 실패 — '+e.message,'err');}finally{BGSAVE=false; $('#save').disabled=false;}
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
  $('#hidedef').classList.toggle('on',!!FMT.hideDefault);
  $('#stickerall').classList.toggle('on',!!FMT.stickerAll);
  const favset=new Set(CAT.favorites);
  const defset=new Set(CAT.default_packs||[]);
  let list=CAT.stickers;
  if(ST_FILTER==='fav') list=list.filter(s=>favset.has(s.ref));
  if(FMT.hideDefault) list=list.filter(s=>!defset.has(s.pack)||favset.has(s.ref));
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
// 기본(네이버 제공) 이모티콘 숨기기 토글
$('#hidedef').onclick=function(){FMT.hideDefault=!FMT.hideDefault;
  this.classList.toggle('on',FMT.hideDefault); savePrefs(); renderStickers();};
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
// 스티커 전체 사용 토글(끄면 즐겨찾기만) — 글쓰기에서 쓰던 걸 스티커 탭에서 관리
$('#stickerall').onclick=function(){FMT.stickerAll=!FMT.stickerAll;
  this.classList.toggle('on',FMT.stickerAll); savePrefs();};

// 글쓰기 설정(규칙·협찬·톤·카테고리) 서버 저장/복원 — 새로고침해도 유지
async function savePrefs(){try{await fetch('/api/prefs',{method:'POST',headers:{'content-type':'application/json'},
  body:JSON.stringify({rules:RULES,fmt:FMT,tone:$('#tone').value,keywords:$('#keywords').value,minChars:$('#minchars').value,category:CATEGORY})});}catch(e){}}
async function loadPrefs(){
  try{const p=await (await fetch('/api/prefs')).json();
    if(p.rules)Object.assign(RULES,p.rules);
    if(p.fmt)Object.assign(FMT,p.fmt);
    if(typeof p.tone==='string')$('#tone').value=p.tone;
    if(typeof p.keywords==='string')$('#keywords').value=p.keywords;
    if(p.minChars!=null)$('#minchars').value=p.minChars;
    if(typeof p.category==='string')setCategory(p.category);
  }catch(e){}
  renderRules(); applyFmtState();
}
// 저장된 협찬/스티커 상태를 토글 UI에 반영(서식 칩은 제거됨)
function applyFmtState(){
  $('#sponsw').classList.toggle('on',!!FMT.sponsored);
  $('#sponbox').style.display=FMT.sponsored?'block':'none';
  if(FMT.sponsored)loadSponPicker();
  $('#stickerall').classList.toggle('on',!!FMT.stickerAll);
}

// 설정
function renderRules(){const c=$('#rules'); c.innerHTML='';
  RULE_META.forEach(([k,t,d])=>{const row=document.createElement('div'); row.className='setrow';
    row.innerHTML=`<div><div class=t>${t}</div><div class=d>${d}</div></div><div class="sw ${RULES[k]?'on':''}"></div>`;
    row.querySelector('.sw').onclick=function(){RULES[k]=!RULES[k]; this.classList.toggle('on',RULES[k]); savePrefs();};
    c.appendChild(row);});
}
// provider별 메타: 라벨·키 발급처·플레이스홀더
const PROV={
  anthropic:{name:'Claude API',short:'Claude',color:'#7b61ff',ph:'sk-ant-...',issuer:'console.anthropic.com › API Keys'},
  openai:{name:'OpenAI API',short:'OpenAI',color:'#10a37f',ph:'sk-...',issuer:'platform.openai.com › API keys'},
  gemini:{name:'Gemini API',short:'Gemini',color:'#1a73e8',ph:'AIza...',issuer:'aistudio.google.com › API keys'},
};
// 모델 표시명 — 코드명 대신 사람이 읽기 좋게(없으면 원본)
const MODELNAME={'claude-opus-4-8':'Opus 4.8','claude-sonnet-4-6':'Sonnet 4.6','gpt-4o':'GPT-4o','gemini-2.5-pro':'2.5 Pro'};
const nicer=v=>MODELNAME[v]||v;
// 선택 카드 한 장
function mcard(val,title,sub,active,miss){
  return `<div class="mcard${active?' on':''}${miss?' miss':''}" data-model="${val}">
    <div class=mc-t>${title}</div>${sub?`<div class=mc-s>${sub}</div>`:''}
    ${active?'<div class=mc-ck>✓ 사용 중</div>':''}</div>`;}
let MODEL_KEYS={};
function provOf(model){const s=(model||'').toLowerCase();
  if(s.startsWith('claude'))return 'anthropic';
  if(s.startsWith('gemini'))return 'gemini';
  if(s.startsWith('gpt')||/^o[134]/.test(s))return 'openai';
  return 'ollama';}
// 모델 적용(텍스트/비전 독립) — 적용 후 새로고침해 '적용 중' 갱신
async function applyModel(payload, okmsg, btn){
  if(btn)btn.disabled=true;
  try{const r=await fetch('/api/models',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});
    if(r.ok){toast(okmsg,'ok'); await loadModels();} else toast('적용 실패','err');
  }catch(e){toast('적용 오류: '+e,'err');}finally{if(btn)btn.disabled=false;}}
// API 키 입력 박스(텍스트가 외부 API일 때)
function apiKeyBox(provider){
  const pv=PROV[provider]; const has=!!MODEL_KEYS[provider];
  return `<div class=sub-h style="margin-top:16px">${pv.short} API 키</div>
    <div class=muted style="margin-bottom:8px">${has?`등록됨 ✓ — 다시 입력하면 교체돼요.`:`이 모델을 쓰려면 키가 필요해요. <b>${pv.issuer}</b>에서 발급 → .env에 저장됩니다.`}</div>
    <div style="display:flex;gap:8px">
      <input type=password id=apikey placeholder="${has?'키 등록됨 ✓ (교체하려면 입력)':pv.ph}" style="flex:1;border:1px solid #d6dade;border-radius:8px;padding:9px;font-size:13px">
      <button class=btn id=apikeysave data-prov="${provider}" style="width:auto;padding:9px 16px">저장</button>
    </div>`;
}
async function loadModels(){try{const m=await (await fetch('/api/models')).json();
  MODEL_KEYS=m.keys||{};
  const installed=m.installed||[];
  const instSet=new Set(installed.map(x=>x.name));
  const tApi=m.text_provider!=='ollama';
  // ── 텍스트: 내장 카드 ──
  const localTextNames=installed.map(x=>x.name);
  if(!tApi && m.text && !instSet.has(m.text)) localTextNames.unshift(m.text);  // 적용 중인데 미설치면 노출
  const localCards=localTextNames.map(n=>{const i=installed.find(x=>x.name===n), miss=!instSet.has(n);
    return mcard(n, n, miss?'미설치':(i&&i.size_gb?i.size_gb+'GB':'로컬'), n===m.text, miss);}).join('')
    || '<div class=muted>설치된 모델이 없어요</div>';
  // ── 텍스트: 외부 API 카드(공급자별 묶음) ──
  const byProv={}; (m.api_text||[]).forEach(a=>{(byProv[a.provider]=byProv[a.provider]||[]).push(a);});
  const apiCards=Object.entries(byProv).map(([prov,list])=>{const pv=PROV[prov]||{short:prov}; const key=!!MODEL_KEYS[prov];
    return `<div class=mgroup>${pv.short} <span class="keychip ${key?'ok':'no'}">${key?'키 있음':'키 필요'}</span></div>
      <div class=mgrid>${list.map(a=>mcard(a.model, nicer(a.model), pv.short, a.model===m.text)).join('')}</div>`;}).join('');
  // ── 비전: 카드(비전 추정 우선) ──
  const visNames=[...installed].sort((a,b)=>(b.vision?1:0)-(a.vision?1:0)).map(x=>x.name);
  if(m.vision && !instSet.has(m.vision)) visNames.unshift(m.vision);
  const visCards=visNames.map(n=>{const i=installed.find(x=>x.name===n), miss=!instSet.has(n);
    return mcard(n, (i&&i.vision?'🖼 ':'')+n, miss?'미설치':(i&&i.size_gb?i.size_gb+'GB':'로컬'), n===m.vision, miss);}).join('');

  const noLocal=installed.length===0;
  $('#models').innerHTML=`
    <h3>텍스트 모델 <span class=muted style="font-weight:400">— 초안 글 작성</span></h3>
    <div class=muted style="margin-bottom:4px">카드를 누르면 바로 적용돼요. 적용 중: <b>${m.text||'-'}</b> ${tApi?`<span style="color:${(PROV[m.text_provider]||{}).color||'#666'}">· ${(PROV[m.text_provider]||{}).short||m.text_provider}</span>`:'<span class=muted>· 내장</span>'}</div>
    <div id=txtsection>
      <div class=mgroup>내장 (내 컴퓨터 · Ollama)</div>
      <div class=mgrid>${localCards}</div>
      ${apiCards}
    </div>
    <div id=txtnote></div>
    <div id=apikeybox></div>

    <h3 style="margin-top:26px">비전 모델 <span class=muted style="font-weight:400">— 사진·상품 이미지 분석 (내장 전용)</span></h3>
    ${noLocal
      ? `<div class=muted>로컬 모델이 안 보여요 — Ollama가 꺼져 있거나 설치된 모델이 없어요. <b>ollama.com</b>에서 설치 후 아래 명령으로 받으세요.<pre class=mcmd>ollama pull qwen2.5vl:7b</pre></div>`
      : `<div class=muted style="margin-bottom:4px">적용 중: <b>${m.vision||'-'}</b> · 🖼 표시가 비전 모델이에요.</div>
         <div class=mgrid id=viscards>${visCards}</div>
         <div id=visnote></div>`}

    <details style="margin-top:26px"><summary style="cursor:pointer;font-weight:700;font-size:13px">🎁 추천 조합 (내 그래픽카드 사양별 한 번에)</summary>
      <div class=muted style="margin:8px 0">사양에 맞는 조합을 고르면 텍스트·비전을 한 번에 설정해요.</div>
      <div id=presets></div></details>`;

  // 텍스트 적용 중 안내(설치/키)
  function txtNote(){const prov=m.text_provider;
    $('#txtnote').innerHTML = (prov==='ollama' && !instSet.has(m.text))
      ? `<div class=sub-h style="margin-top:14px">설치 필요 — 터미널에 입력</div><pre class=mcmd>ollama pull ${m.text}</pre>` : '';
    $('#apikeybox').innerHTML = (prov!=='ollama') ? apiKeyBox(prov) : '';
    const sv=$('#apikeysave'); if(sv)sv.onclick=()=>saveKey(prov);}
  txtNote();
  $$('#txtsection [data-model]').forEach(c=>c.onclick=()=>{const v=c.dataset.model;
    if(v===m.text){toast('이미 쓰는 모델이에요.','info');return;}
    applyModel({text:v}, '텍스트 모델 적용됨 ✓');});

  // 비전 적용 중 안내 + 카드 클릭
  if(!noLocal){
    const vi=installed.find(x=>x.name===m.vision);
    $('#visnote').innerHTML = !instSet.has(m.vision)
      ? `<div class=sub-h style="margin-top:14px">설치 필요 — 터미널에 입력</div><pre class=mcmd>ollama pull ${m.vision}</pre>`
      : (vi&&!vi.vision?`<div class=muted style="margin-top:8px">⚠️ 이 모델은 비전(이미지) 모델이 아닐 수 있어요. 사진 분석이 안 되면 🖼 표시 모델을 고르세요.</div>`:'');
    $$('#viscards [data-model]').forEach(c=>c.onclick=()=>{const v=c.dataset.model;
      if(v===m.vision){toast('이미 쓰는 모델이에요.','info');return;}
      applyModel({vision:v}, '비전 모델 적용됨 ✓');});
  }

  // 추천 조합 — 내장(로컬) 프리셋만(GPU 사양 가이드)
  $('#presets').innerHTML=(m.presets||[]).filter(p=>p.provider==='ollama').map(p=>
    `<div class=setrow><div><div class=t>${p.label}</div><div class=d>텍스트 ${p.text} · 비전 ${p.vision}</div></div>
      <button class=btn data-preset="${p.key}" style="width:auto;padding:7px 14px">적용</button></div>`).join('');
  $$('#presets [data-preset]').forEach(b=>b.onclick=()=>applyModel({preset:b.dataset.preset}, '프리셋 적용됨 ✓', b));
}catch(e){$('#models').innerHTML='<div class=muted>로드 실패</div>';}}
async function saveKey(provider){const v=$('#apikey').value.trim(); if(!v){toast('키를 입력하세요.','info');return;}
  const b=$('#apikeysave'); if(b)b.disabled=true;
  try{const r=await fetch('/api/llm-key',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({provider,key:v})});
    if(r.ok){MODEL_KEYS[provider]=true; toast(`${(PROV[provider]||{}).name||provider} 키 저장됨 ✓`,'ok'); await loadModels();}
    else toast('API 키 저장 실패','err');
  }catch(e){toast('API 키 오류: '+e,'err');}finally{const x=$('#apikeysave'); if(x)x.disabled=false;}}

function renderEmphasis(e){
  // 색마다 글자색·배경·폰트·크기를 직접 편집 + 드롭다운으로 갈래 선택(안 씀 / 강조 / 주의 …).
  const lanes=(e.lanes&&e.lanes.length?e.lanes:[{name:'강조'},{name:'주의'},{name:'부정'}]);
  const fonts=e.fonts||[{value:'',name:'기본'}], sizes=e.sizes||[];
  const card=s=>{
    const tc=s.text_color||'', bg=s.background_color||'';
    const hasStyle=tc||bg||s.font||s.size||s.bold;
    const stl=hasStyle?((tc?`color:${tc};`:'')+(bg?`background:${bg};`:'')+(s.bold?'font-weight:800;':'')+(s.font?`font-family:'se-${s.font}';`:'')+(s.size?`font-size:${s.size}px;`:'')):'color:#9aa5b1';
    const lane=s.tag||'';
    const box=lane?'border-color:var(--green);background:#f3fbf6':'border-color:#e3e8ee;background:#fff';
    const laneOpts='<option value="">안 씀</option>'+lanes.map(L=>`<option value="${esc(L.name)}"${L.name===lane?' selected':''}>${esc(L.name)}</option>`).join('');
    const fontOpts=fonts.map(f=>`<option value="${esc(f.value)}"${(f.value||'')===(s.font||'')?' selected':''}>${esc(f.name)}</option>`).join('');
    const sizeOpts='<option value="">크기</option>'+sizes.map(z=>`<option value="${z}"${String(z)===String(s.size||'')?' selected':''}>${z}</option>`).join('');
    return `<div class=epcell data-id="${s.id}" style="border:1.5px solid;border-radius:11px;padding:9px;${box}">
      <div class=epnum>#${s.id}${s.edited?' <span style="color:var(--green)">· 내가 설정함</span>':''}</div>
      <div style="text-align:center"><span class="sw-chip" style="${stl}">${hasStyle?'강조 텍스트':'(서식 없음)'}</span></div>
      <div class=eprow>
        <label><input type=checkbox class=epclr-on data-clr=text ${tc?'checked':''}>글자</label>
        <input type=color class="epclr${tc?'':' epclr-off'}" data-clr=text value="${tc||'#e53935'}">
        <label><input type=checkbox class=epclr-on data-clr=bg ${bg?'checked':''}>배경</label>
        <input type=color class="epclr${bg?'':' epclr-off'}" data-clr=bg value="${bg||'#fff59d'}"></div>
      <div class=eprow>
        <select class=epstyle data-key=font title=폰트>${fontOpts}</select>
        <select class=epstyle data-key=size title=글씨크기>${sizeOpts}</select>
        <label><input type=checkbox class=epstyle data-key=bold ${s.bold?'checked':''}>굵게</label></div>
      <select class=eplane data-id="${s.id}" style="width:100%;margin-top:7px;padding:5px 7px;border:1px solid #d6dade;border-radius:7px;font-size:12px;background:#fff;cursor:pointer">${laneOpts}</select></div>`;};
  const laneHelp=lanes.map(L=>`<b>${esc(L.name)}</b>`).join(' · ');
  let h=`<div class=muted style="margin-bottom:10px">색마다 <b>글자색·배경·폰트·크기</b>를 직접 정하고, <b>갈래</b>를 고르세요 — ${laneHelp}. 같은 갈래에 여러 색을 주면 글에서 <b>번갈아</b> 쓰입니다. <b>안 씀</b>이면 그 색은 사용 안 함. (현재: <b>${esc(e.source||'')}</b>)</div>`;
  h+='<div class=epgrid>'+(e.all||[]).map(card).join('')+'</div>';
  const cfg = e.config || {};
  h += `<div style="margin-top:18px;padding:14px;border:1px solid #e7edf3;border-radius:14px;background:#fcfdff">
    <div class=sub-h style="margin-bottom:10px">강조 밀도</div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
      <div><div style="font-weight:700;margin-bottom:4px;font-size:13px">문단당 최소 강조</div><input class=epconf data-key="min_per_paragraph" value="${esc(cfg.min_per_paragraph||'')}" placeholder="0" style="width:100%;padding:9px 11px;border:1px solid #d6dade;border-radius:10px;background:#fff"></div>
      <div><div style="font-weight:700;margin-bottom:4px;font-size:13px">문단당 최대 강조</div><input class=epconf data-key="max_per_paragraph" value="${esc(cfg.max_per_paragraph||'')}" placeholder="2" style="width:100%;padding:9px 11px;border:1px solid #d6dade;border-radius:10px;background:#fff"></div>
      <div><div style="font-weight:700;margin-bottom:4px;font-size:13px">최소 문장 간격</div><input class=epconf data-key="min_sentence_gap" value="${esc(cfg.min_sentence_gap||'')}" placeholder="1" style="width:100%;padding:9px 11px;border:1px solid #d6dade;border-radius:10px;background:#fff"></div>
    </div>
    <div class=muted style="margin-top:8px;font-size:12px">문단당 최소 강조를 1 이상으로 두면 <b>모든 문단에 강조를 그만큼 넣으라고</b> LLM에게 안내돼요(아래 안내문에 반영). 최대만 두면 강조 없는 문단도 허용돼요.</div>
    <div style="margin-top:12px"><button class=btn data-action="save-emphasis-config" style="width:auto;padding:9px 16px">저장</button></div>
  </div>`;
  // 가시성 — LLM에게 실제로 들어가는 강조 지시문(어떻게 쓰이는지 그대로 보여줌)
  h+=`<div class=sub-h style="margin-top:16px">✍️ 생성 시 LLM에게 이렇게 안내됩니다</div>
    <pre style="white-space:pre-wrap;background:#f7f9fb;border:1px solid #eef1f5;border-radius:8px;padding:11px 13px;font-size:12px;line-height:1.6;margin-top:8px">${esc(e.instruction||'')}</pre>`;
  $('#emph').innerHTML=h;
}
async function loadEmphasis(){try{renderEmphasis(await (await fetch('/api/emphasis')).json());
}catch(e){$('#emph').innerHTML='<div class=muted>로드 실패</div>';}}
// 색 칸의 글자색·배경·폰트·크기·굵게 → emphasis.yaml styles에 저장
function collectStyle(cell){
  const on=c=>cell.querySelector(`.epclr-on[data-clr=${c}]`).checked;
  const v=sel=>cell.querySelector(sel).value;
  return {
    text_color: on('text')?v('.epclr[data-clr=text]'):'',
    background_color: on('bg')?v('.epclr[data-clr=bg]'):'',
    font: v('[data-key=font]'),
    size: v('[data-key=size]'),
    bold: cell.querySelector('[data-key=bold]').checked,
  };}
$('#emph').addEventListener('change',async e=>{
  // 갈래(태그) 선택
  const sel=e.target.closest('.eplane');
  if(sel){try{const r=await fetch('/api/emphasis',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({id:+sel.dataset.id,tag:sel.value})});
    if(r.ok){renderEmphasis(await r.json());}}catch(e){} return;}
  // 색·폰트·크기·굵게 편집
  const st=e.target.closest('.epclr,.epclr-on,.epstyle');
  if(st){const cell=st.closest('.epcell'); if(!cell)return;
    // 색을 직접 고르면 그 색을 켠 것으로 간주(체크 자동 ON)
    if(st.classList.contains('epclr')){const cb=cell.querySelector(`.epclr-on[data-clr=${st.dataset.clr}]`); if(cb)cb.checked=true;}
    try{const r=await fetch('/api/emphasis',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({id:+cell.dataset.id,style:collectStyle(cell)})});
      if(r.ok){renderEmphasis(await r.json()); toast('저장됨 ✓ 다음 생성부터 반영','ok',1200);}else{toast('저장 실패','err');}}
    catch(e){toast('저장 오류','err');}}
});
// 강조 밀도 저장
$('#emph').addEventListener('click',async e=>{const btn=e.target.closest('[data-action="save-emphasis-config"]'); if(!btn)return;
  const root=$('#emph');
  const cfg={
    min_per_paragraph: root.querySelector('[data-key="min_per_paragraph"]').value.trim() || null,
    max_per_paragraph: root.querySelector('[data-key="max_per_paragraph"]').value.trim() || null,
    min_sentence_gap: root.querySelector('[data-key="min_sentence_gap"]').value.trim() || null,
  };
  btn.disabled=true;
  try{const r=await fetch('/api/emphasis',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({config:cfg})});
    if(r.ok){renderEmphasis(await r.json()); toast('강조 밀도 저장됨 ✓ 다음 생성부터 반영','ok',1600);}else{toast('저장 실패','err');}}
  catch(e){toast('저장 오류','err');}
  finally{btn.disabled=false;}
});
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
$('#tone').onchange=savePrefs;
setKind('place',false); loadPhotos(); setupUpload(); setupDraftImport(); loadPrefs(); loadModels(); loadEmphasis(); loadPrompt(); loadVariants(); loadCategories(); loadPhotoCats();
$('#photobtn').onclick=openPhotoModal; $('#phclose').onclick=closePhotoModal; $('#phdone').onclick=closePhotoModal;
$('#phmodal').onclick=e=>{ if(e.target===$('#phmodal'))closePhotoModal(); };
$('#newpost').onclick=newPost;
$('#npok').onclick=doNewPost; $('#npx').onclick=closeNP; $('#npcancel').onclick=closeNP;
$('#npmodal').onclick=e=>{ if(e.target===$('#npmodal'))closeNP(); };
$('#catok').onclick=catSubmit; $('#catx').onclick=closeCatModal; $('#catcancel').onclick=closeCatModal;
$('#catinput').onkeydown=e=>{ if(e.key==='Enter')catSubmit(); else if(e.key==='Escape')closeCatModal(); };
$('#catmodal').onclick=e=>{ if(e.target===$('#catmodal'))closeCatModal(); };
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

        def _stream_begin(self, code=200):
            """NDJSON 스트리밍 응답 시작 — 진행 상태를 한 줄씩 흘려보낸다.

            HTTP/1.0(기본) + Connection: close라 Content-Length 없이 EOF로 종료한다.
            클라이언트는 줄 단위 JSON({stage}/{prompt}/{error})을 읽어 상태를 갱신한다.
            """
            self.send_response(code)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()

        def _stream_write(self, obj):
            self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

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
            elif u.path == "/api/photo_categories":
                from autoblog.config import load_photo_categories

                self._send(200, json.dumps(load_photo_categories()).encode())
            elif u.path == "/api/prefs":
                self._send(200, json.dumps(_load_prefs()).encode())
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
                elif path == "/api/drafts":
                    self._list_drafts()
                elif path == "/api/drafts/import":
                    self._import_draft_photos(self._json_body())
                elif path == "/api/favorite":
                    body = self._json_body()
                    n = _toggle_favorite(body.get("ref", ""), bool(body.get("on")))
                    self._send(200, json.dumps({"ok": True, "favorites": n}).encode())
                elif path == "/api/sponsor-sticker":
                    body = self._json_body()
                    ref = _set_sponsor_sticker(body.get("ref", ""))
                    self._send(200, json.dumps({"ok": True, "sponsor": ref}).encode())
                elif path == "/api/upload":
                    body = self._json_body()
                    p = _save_upload(body.get("filename", ""), body.get("data", ""))
                    self._send(200, json.dumps({"path": p}).encode())
                elif path == "/api/photos/caption":
                    self._caption_photos(self._json_body())
                elif path == "/api/photo_categories":
                    self._add_photo_category(self._json_body())
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
                elif path == "/api/prefs":
                    _save_prefs(self._json_body())
                    self._send(200, b'{"ok":true}')
                elif path == "/api/models":
                    body = self._json_body()
                    if body.get("preset"):
                        _set_model_preset(body["preset"])
                    else:
                        _set_model_selection(body.get("text"), body.get("vision"))
                    self._send(200, b'{"ok":true}')
                elif path == "/api/llm-key":
                    body = self._json_body()
                    _set_llm_key(body.get("provider", "anthropic"), body.get("key", ""))
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
                elif path == "/api/emphasis":
                    body = self._json_body()
                    if body.get("config") is not None:
                        _save_emphasis_config(body.get("config"))
                    elif body.get("style") is not None:
                        _save_emphasis_style(body.get("id"), body.get("style"))
                    elif body.get("id") is not None:
                        _save_emphasis_preset_tag(body.get("id"), body.get("tag", ""))
                    self._send(200, json.dumps(_emphasis_preview()).encode())
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
            photo_meta = body.get("photoMeta") if isinstance(body.get("photoMeta"), dict) else {}
            tone = (body.get("tone") or "").strip() or None
            rules = CommonRules(**body["rules"]) if body.get("rules") else None
            guidelines = _build_guidelines(body)
            dkeys, qkeys = _enabled_variant_keys()  # '서식'에서 고른 종류만 프롬프트에 안내

            # 진행 상태를 스트리밍으로 흘려보내며 수집·조립(수집 캐시 재사용으로 반복 호출 빠름)
            self._stream_begin()
            self._stream_write({"stage": "자료를 준비하는 중…"})

            def progress(msg):
                try:
                    self._stream_write({"stage": msg})
                except (BrokenPipeError, OSError):
                    pass  # 클라이언트가 끊어도 수집은 계속 진행

            try:
                text = build_export_prompt(
                    body.get("memo", ""),
                    place_url=srcval if src == "place" else None,
                    product=srcval if src == "product" else None,
                    photos=photos or None,
                    photo_meta=photo_meta,
                    style=StyleProfile(tone=tone) if tone else None,
                    rules=rules,
                    guidelines=guidelines,
                    emphasis=bool(body.get("emphasis")),
                    structure=bool(body.get("structure")),
                    stickers=bool(body.get("stickers")),
                    sticker_favorites_only=not bool(body.get("stickerAll")),
                    divider_variants=dkeys,
                    quote_variants=qkeys,
                    use_cache=True,
                    progress=progress,
                )
            except Exception as exc:  # noqa: BLE001 — 오류도 스트림으로 전달
                self._stream_write({"error": str(exc)})
                return
            self._stream_write({"prompt": text})

        def _caption_photos(self, body):
            """온디맨드 '✨ AI 자동 추천' — 사진 맥락 캡션 → [{path,label,caption}]."""
            from autoblog.pipeline import caption_photos

            srcval, src = self._resolve_src(body)
            photos = [p for p in (body.get("photos") or []) if p]
            if not photos:
                self._send(400, json.dumps({"error": "선택된 사진이 없어요"}).encode())
                return
            try:
                items = caption_photos(
                    body.get("memo", ""),
                    place_url=srcval if src == "place" else None,
                    product=srcval if src == "product" else None,
                    photos=photos,
                    review_type=(body.get("reviewType") or src or None),
                )
            except Exception as exc:  # noqa: BLE001 — 키 미설정/패키지 미설치/API 오류 그대로 안내
                self._send(400, json.dumps({"error": str(exc)}).encode())
                return
            self._send(200, json.dumps({"photos": items}).encode())

        def _add_photo_category(self, body):
            """사용자가 추가한 사진 분류를 config/photo_categories.yaml에 저장하고 전체 목록 반환."""
            import yaml

            from autoblog.config import CONFIG_DIR, load_photo_categories

            rt = (body.get("reviewType") or "place").strip() or "place"
            name = (body.get("category") or "").strip()
            if not name:
                self._send(400, json.dumps({"error": "분류 이름이 비었어요"}).encode())
                return
            path = CONFIG_DIR / "photo_categories.yaml"
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except FileNotFoundError:
                data = {}
            if not isinstance(data, dict):
                data = {}
            lst = [str(x) for x in data.get(rt, []) if isinstance(data.get(rt), list)]
            if name not in lst:
                lst.insert(lst.index("기타"), name) if "기타" in lst else lst.append(name)
            data[rt] = lst
            header = (
                "# 사진 카테고리 프리셋 — 리뷰 타입별 분류 목록. UI '+ 새 분류 추가' 또는 직접 편집.\n"
                "# 첫 칸이 기본값(분류 안 한 사진이 들어갈 곳).\n\n"
            )
            path.write_text(
                header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
            load_photo_categories.cache_clear()
            self._send(200, json.dumps(load_photo_categories()).encode())

        def _generate(self, body):
            from autoblog.draft.rules import CommonRules
            from autoblog.draft.style import StyleProfile
            from autoblog.pipeline import run_pipeline

            srcval, src = self._resolve_src(body)
            photos = [p for p in (body.get("photos") or []) if p]
            photo_meta = body.get("photoMeta") if isinstance(body.get("photoMeta"), dict) else {}
            tone = (body.get("tone") or "").strip() or None
            rules = CommonRules(**body["rules"]) if body.get("rules") else None
            guidelines = _build_guidelines(body)
            dv, qv = _enabled_variants()  # 활성 종류 중 첫 번째를 기본 적용(다중 중 우선)
            dkeys, qkeys = _enabled_variant_keys()  # 프롬프트에 안내할 고른 종류 전체
            result = run_pipeline(
                body["memo"],
                place_url=srcval if src == "place" else None,
                product=srcval if src == "product" else None,
                photos=photos or None,
                photo_meta=photo_meta,
                style=StyleProfile(tone=tone) if tone else None,
                rules=rules,
                guidelines=guidelines,
                emphasis=bool(body.get("emphasis")),
                structure=bool(body.get("structure")),
                stickers=bool(body.get("stickers")),
                sticker_favorites_only=not bool(body.get("stickerAll")),
                divider_variant=dv[0],
                quote_variant=qv[0],
                divider_variants=dkeys,
                quote_variants=qkeys,
                sponsored=bool(body.get("sponsored")),
                sponsor_links=_links(body),
                sponsor_sticker=(body.get("sponsorSticker") or "").strip(),
                use_cache=True,  # 같은 URL 재수집 방지(export/캡션과 캐시 공유)
            )
            self._send_plan(result)

        def _import_draft(self, body):
            """외부 챗봇에서 받아온 초안 텍스트 → 마커 파싱 → 게시 플랜(생성과 동일 흐름)."""
            from autoblog.pipeline import _place_info, cached_place_card, plan_from_text

            text = (body.get("text") or "").strip()
            if not text:
                self._send(400, json.dumps({"error": "붙여넣은 글이 비어 있어요"}).encode())
                return
            photos = [p for p in (body.get("photos") or []) if p]
            photo_meta = body.get("photoMeta") if isinstance(body.get("photoMeta"), dict) else {}
            # 플레이스 URL이 있으면 세션 캐시에 수집된 가게 카드에서 [지도] 마커용
            # 가게명·도로명 주소를 채운다(생성 경로와 동일). 캐시에 없으면 None → [지도:가게명] 폴백.
            place_query = place_address = None
            srcval, src = self._resolve_src(body)
            if src == "place" and srcval:
                card = cached_place_card(srcval)
                if card is not None:
                    _, place_query, place_address = _place_info(card)
            dv, qv = _enabled_variants()
            result = plan_from_text(
                text,
                photos=photos or None,
                photo_meta=photo_meta,
                emphasis=bool(body.get("emphasis")),
                structure=bool(body.get("structure")),
                stickers=bool(body.get("stickers")),
                sticker_favorites_only=not bool(body.get("stickerAll")),
                divider_variant=dv[0],
                quote_variant=qv[0],
                place_query=place_query,
                place_address=place_address,
                sponsored=bool(body.get("sponsored")),
                sponsor_links=_links(body),
                sponsor_sticker=(body.get("sponsorSticker") or "").strip(),
            )
            self._send_plan(result)

        def _send_plan(self, result):
            """PipelineResult → {title, blocks, debug} JSON. generate/import 공통."""
            state["last"] = result
            blocks = []
            for b in result.plan.blocks:
                blk = {"kind": b.kind, "text": b.text, "variant": b.variant, "align": b.align}
                if b.kind == "sticker":
                    blk["sticker_ref"] = f"{b.sticker_pack}:{b.sticker_index}"
                elif b.kind == "image":
                    blk["image_path"] = b.image_path
                    blk["image_label"] = b.image_label
                elif b.kind == "link":
                    blk["link_url"] = b.link_url
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

        def _list_drafts(self):
            """네이버 임시저장 글 목록을 읽어 [{idx,title,date}]로 반환."""
            from autoblog.publish.editor import BlogPublisher

            pub = BlogPublisher(headless=True)
            pub.start()
            try:
                if not pub.wait_for_login():
                    raise RuntimeError("네이버 로그인이 필요합니다")
                drafts = pub.list_drafts()
            finally:
                pub.close()
            self._send(200, json.dumps({"drafts": drafts}).encode())

        def _import_draft_photos(self, body):
            """선택한 임시저장 글(idx)의 본문 사진을 내려받아 로컬 경로 목록을 반환."""
            from autoblog.publish.editor import BlogPublisher

            try:
                idx = int(body.get("idx"))
            except (TypeError, ValueError):
                self._send(400, json.dumps({"error": "idx가 필요합니다"}).encode())
                return
            pub = BlogPublisher(headless=True)
            pub.start()
            try:
                if not pub.wait_for_login():
                    raise RuntimeError("네이버 로그인이 필요합니다")
                paths = pub.import_draft_photos(idx, UPLOAD_DIR)
            finally:
                pub.close()
            self._send(200, json.dumps({"paths": paths}).encode())

    return Handler


FORMAT_CONFIG_PATH = REPO_ROOT / "config" / "format.yaml"
PREVIEW_DIR = REPO_ROOT / "config" / "editor_previews"
PREFS_PATH = REPO_ROOT / "config" / "ui_prefs.json"

# 글쓰기 화면 기본 설정(서버가 기준). 새 키가 추가돼도 저장본 위에 머지된다.
DEFAULT_MIN_CHARS = 1500  # 글자 수를 따로 안 넣으면 기본 최소 글자 수

_PREFS_DEFAULT = {
    "rules": {
        "mobile_friendly": True, "authenticity": True,
        "structure_guide": True, "seo": False, "emoji": False,
    },
    "fmt": {
        "emphasis": True, "structure": True, "stickers": True,
        "stickerAll": False, "hideDefault": True,
        "sponsored": False, "sponsorSticker": "",
    },
    "tone": "",
    "keywords": "",
    "minChars": DEFAULT_MIN_CHARS,
    "category": "",
}


def _build_guidelines(body: dict):
    """요청 body의 키워드·글자수 입력으로 Guidelines를 만든다(둘 다 비어도 글자수 기본 적용).

    keywords: 쉼표/줄바꿈으로 구분한 필수 키워드. minChars: 최소 글자 수(빈 값이면 1500).
    """
    import re

    from autoblog.draft.guideline import Guidelines

    raw_kw = body.get("keywords") or ""
    keywords = [k.strip() for k in re.split(r"[,\n]", raw_kw) if k.strip()]
    raw_min = body.get("minChars")
    try:
        min_chars = int(raw_min)
    except (TypeError, ValueError):
        min_chars = DEFAULT_MIN_CHARS
    if min_chars <= 0:
        min_chars = DEFAULT_MIN_CHARS
    return Guidelines(required_keywords=keywords, min_chars=min_chars)


def _load_prefs() -> dict:
    """저장된 글쓰기 설정(없거나 깨지면 기본값). 기본값 위에 저장본을 머지해 반환."""
    try:
        saved = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        saved = {}
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _PREFS_DEFAULT.items()}
    for k, v in saved.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def _save_prefs(body: dict) -> None:
    """들어온 일부 키만 머지 저장(rules/fmt는 dict 머지, tone은 교체)."""
    cur = _load_prefs()
    for k in ("rules", "fmt"):
        if isinstance(body.get(k), dict):
            cur[k].update(body[k])
    if "tone" in body:
        cur["tone"] = body.get("tone") or ""
    if "keywords" in body:
        cur["keywords"] = body.get("keywords") or ""
    if "minChars" in body:
        try:
            cur["minChars"] = int(body.get("minChars"))
        except (TypeError, ValueError):
            cur["minChars"] = DEFAULT_MIN_CHARS
    if "category" in body:
        cur["category"] = body.get("category") or ""
    PREFS_PATH.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _links(body: dict) -> list[str]:
    """요청 바디의 links(쿠팡파트너스 링크 줄목록) → 공백 제거한 URL 리스트."""
    return [u.strip() for u in (body.get("links") or []) if isinstance(u, str) and u.strip()]


def _enabled_variant_keys() -> tuple[list[str], list[str]]:
    """현재 활성화된 구분선/인용구 종류 키 목록(프롬프트 안내에 사용)."""
    from autoblog.publish.plan import DIVIDER_META, QUOTE_META

    cfg = _load_format()
    den = [v for v in (cfg.get("divider_enabled") or ["default"]) if v in DIVIDER_META]
    qen = [v for v in (cfg.get("quote_enabled") or ["default"]) if v in QUOTE_META]
    return den or ["default"], qen or ["default"]


def _enabled_variants() -> tuple[list[int], list[int]]:
    """현재 활성화된 구분선/인용구 variant 인덱스 목록(생성에 사용)."""
    from autoblog.publish.plan import DIVIDER_META, QUOTE_META

    den, qen = _enabled_variant_keys()
    dv = [DIVIDER_META[v][0] for v in den]
    qv = [QUOTE_META[v][0] for v in qen]
    return dv or [1], qv or [1]


def _editor_options() -> dict:
    """라이브 캡처한 에디터 실제 옵션(config/editor_options.json). 없으면 빈 dict."""
    p = REPO_ROOT / "config" / "editor_options.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


# 스마트에디터 글자 크기 옵션(fs<N>) — 본문 기본은 15.
_EDITOR_FONT_SIZES = [11, 13, 15, 16, 19, 24, 28, 30, 34, 38]


def _size_num(size) -> str | None:
    """'16px'/'16'/16 → '16'. 빈 값이면 None."""
    if size in (None, ""):
        return None
    return str(size).strip().lower().replace("px", "") or None


def _emphasis_preview() -> dict:
    """현재 강조 설정으로 실제 적용될 색을 해석(미리보기).

    프로젝트 프리셋(config/power_shortcuts.json)이 있으면 그 색으로, 없으면 내장 기본으로 해석.
    """
    from autoblog.publish.emphasis import (
        DEFAULT_STYLES,
        build_emphasis_instruction,
        load_default_power_shortcuts,
        load_emphasis_config,
    )

    cfg = load_emphasis_config()
    # 색(번호)별 기본 시드 — 있으면 파워 단축키 프리셋, 없으면 내장 기본. 그 위에 사용자가
    # 서식 탭에서 직접 편집한 styles를 덮어쓴다(색·폰트·크기는 사용자 편집이 최우선).
    presets = dict(load_default_power_shortcuts() or DEFAULT_STYLES)
    presets.update(cfg.styles)
    source = "내 설정" if cfg.styles else "기본값(편집 가능)"
    font_opts = _editor_options().get("fonts", [])
    fonts = {f.get("value"): f.get("name", "").split("\n")[0] for f in font_opts}

    # 프리셋ID → 태그(용도). preset_tags가 있으면 그대로, 없으면 레거시에서 파생해 보여준다.
    pools = cfg.tag_pools()
    tag_of = {pid: tag for tag, ids in pools.items() for pid in ids}

    def resolve(pid):
        st = presets.get(pid)
        base = {"id": pid, "tag": tag_of.get(pid, ""), "edited": pid in cfg.styles}
        if not st:
            return {**base, "defined": False}
        return {**base, "defined": True, "text_color": st.text_color,
                "background_color": st.background_color, "bold": st.bold,
                "font": st.font_family, "font_name": fonts.get(st.font_family),
                "size": _size_num(st.font_size)}

    all_styles = [resolve(i) for i in sorted(presets)]
    # 같은 태그가 몇 색에 걸렸는지(순환 여부 표시용)
    groups = [{"tag": t, "ids": ids} for t, ids in pools.items()]
    # 드롭다운에 보여줄 갈래 = 기본(강조/주의/부정) + 사용자가 이미 쓴 갈래(중복 제거, 순서 유지)
    from autoblog.publish.emphasis import DEFAULT_LANES, LANE_DESC

    lane_names = list(dict.fromkeys([*DEFAULT_LANES, *pools.keys()]))
    lanes = [{"name": t, "desc": LANE_DESC.get(t, t)} for t in lane_names]
    # 색마다 직접 고를 폰트·크기 후보(에디터 실제 옵션). 폰트는 value 있는 것만, 맨 앞에 '기본'.
    font_choices = [{"value": "", "name": "기본"}] + [
        {"value": f["value"], "name": f.get("name", "").split("\n")[0]}
        for f in font_opts if f.get("value")
    ]
    return {
        "source": source,
        "all": all_styles,
        "groups": groups,
        "lanes": lanes,
        "fonts": font_choices,
        "sizes": _EDITOR_FONT_SIZES,
        "config": {
            "cycling_pool": cfg.cycling_pool,
            "negative_pool": cfg.negative_pool,
            "fixed_map": cfg.fixed_map,
            "max_per_paragraph": cfg.max_per_paragraph,
            "min_per_paragraph": cfg.min_per_paragraph,
            "min_sentence_gap": cfg.min_sentence_gap,
        },
        # LLM에게 실제로 들어가는 강조 지시문(가시성 — 어떻게 쓰이는지 그대로 보여줌)
        "instruction": build_emphasis_instruction(cfg),
        "max_per_paragraph": cfg.max_per_paragraph,
        "min_per_paragraph": cfg.min_per_paragraph,
        "min_sentence_gap": cfg.min_sentence_gap,
    }


def _save_emphasis_config(data: dict) -> None:
    """config/emphasis.yaml에서 순환 풀·고정 매핑·밀도 설정을 저장."""
    import re

    import yaml

    from autoblog.publish.emphasis import _EMPHASIS_CONFIG_PATH, load_emphasis_config

    cfg = load_emphasis_config()
    if "cycling_pool" in data:
        cfg.cycling_pool = [int(x) for x in (data.get("cycling_pool") or []) if isinstance(x, int) or (isinstance(x, str) and x.isdigit())]
    if "negative_pool" in data:
        cfg.negative_pool = [int(x) for x in (data.get("negative_pool") or []) if isinstance(x, int) or (isinstance(x, str) and x.isdigit())]
    if "fixed_map" in data:
        fixed = {}
        for k, v in (data.get("fixed_map") or {}).items():
            try:
                fixed[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
        cfg.fixed_map = fixed
    if "max_per_paragraph" in data:
        cfg.max_per_paragraph = int(data["max_per_paragraph"]) if data.get("max_per_paragraph") not in (None, "") else None
    if "min_per_paragraph" in data:
        cfg.min_per_paragraph = int(data["min_per_paragraph"]) if data.get("min_per_paragraph") not in (None, "") else None
    if "min_sentence_gap" in data:
        cfg.min_sentence_gap = int(data["min_sentence_gap"]) if data.get("min_sentence_gap") not in (None, "") else None

    path = _EMPHASIS_CONFIG_PATH
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    raw = re.sub(r"(?ms)^cycling_pool:\n(?:[ \t]+.*\n?)*", "", raw)
    raw = re.sub(r"(?ms)^negative_pool:\n(?:[ \t]+.*\n?)*", "", raw)
    raw = re.sub(r"(?ms)^fixed_map:\n(?:[ \t]+.*\n?)*", "", raw)
    raw = re.sub(r"(?ms)^max_per_paragraph:.*\n?", "", raw)
    raw = re.sub(r"(?ms)^min_per_paragraph:.*\n?", "", raw)
    raw = re.sub(r"(?ms)^min_sentence_gap:.*\n?", "", raw)
    body = {}
    if cfg.cycling_pool:
        body["cycling_pool"] = cfg.cycling_pool
    if cfg.negative_pool:
        body["negative_pool"] = cfg.negative_pool
    if cfg.fixed_map:
        body["fixed_map"] = cfg.fixed_map
    if cfg.max_per_paragraph is not None:
        body["max_per_paragraph"] = cfg.max_per_paragraph
    if cfg.min_per_paragraph is not None:
        body["min_per_paragraph"] = cfg.min_per_paragraph
    if cfg.min_sentence_gap is not None:
        body["min_sentence_gap"] = cfg.min_sentence_gap
    block = ""
    if body:
        block = (
            "\n# 강조 배정 설정 (서식 탭에서 편집) — 순환 풀, 고정 매핑, 밀도 규칙\n"
            + yaml.safe_dump(body, allow_unicode=True, sort_keys=False)
        )
    path.write_text(raw.rstrip("\n") + "\n" + block, encoding="utf-8")


def _save_emphasis_style(preset_id, style: dict) -> None:
    """색(프리셋ID)의 글자색·배경·굵게·폰트·크기를 config/emphasis.yaml의 styles에 저장.

    서식 탭에서 색마다 직접 편집한 값. 모든 속성이 비면 해당 색의 사용자 설정을 제거(= 기본으로 복귀).
    기존 주석·내용은 보존하고 styles 블록만 교체한다.
    """
    import re

    import yaml

    from autoblog.publish.emphasis import (
        _EMPHASIS_CONFIG_PATH,
        EmphasisStyle,
        load_emphasis_config,
    )

    try:
        pid = int(preset_id)
    except (TypeError, ValueError):
        return

    style = style or {}
    tc = (style.get("text_color") or "").strip() or None
    bg = (style.get("background_color") or "").strip() or None
    font = (style.get("font") or "").strip() or None
    size = _size_num(style.get("size"))
    bold = bool(style.get("bold"))
    st = EmphasisStyle(text_color=tc, background_color=bg, font_family=font,
                       font_size=size, bold=bold)

    styles = {int(k): v for k, v in (load_emphasis_config().styles or {}).items()}
    if st.is_empty():
        styles.pop(pid, None)
    else:
        styles[pid] = st

    path = _EMPHASIS_CONFIG_PATH
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    raw = re.sub(r"\n*# 색\(강조\)별 글자색[^\n]*\n", "\n", raw)
    raw = re.sub(r"(?ms)^styles:\n(?:[ \t]+.*\n?)*", "", raw)
    block = ""
    if styles:
        # 빈 속성은 빼고 깔끔히 덤프(색마다 설정한 값만).
        dump = {
            sid: {k: v for k, v in s.model_dump().items() if v not in (None, False)}
            for sid, s in sorted(styles.items())
        }
        body = yaml.safe_dump({"styles": dump}, allow_unicode=True, sort_keys=False)
        block = ("\n# 색(강조)별 글자색·배경·굵게·폰트·크기 (서식 탭에서 직접 편집)\n" + body)
    path.write_text(raw.rstrip("\n") + "\n" + block, encoding="utf-8")


def _save_emphasis_preset_tag(preset_id, tag: str) -> None:
    """프리셋(강조색)의 태그를 config/emphasis.yaml의 preset_tags에 저장(기존 주석·내용 보존).

    빈 태그를 주면 해당 프리셋의 태그를 제거(= 안 쓰는 색). 콜론·꺾쇠는 마커와 충돌하므로 제거.
    """
    import re

    import yaml

    from autoblog.publish.emphasis import _EMPHASIS_CONFIG_PATH, load_emphasis_config

    try:
        pid = int(preset_id)
    except (TypeError, ValueError):
        return
    tag = re.sub(r"[:<>]", "", tag or "").strip()
    pt = {int(k): v for k, v in (load_emphasis_config().preset_tags or {}).items()}
    if tag:
        pt[pid] = tag
    else:
        pt.pop(pid, None)

    path = _EMPHASIS_CONFIG_PATH
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    # 기존 preset_tags 블록(헤더 주석 + 매핑) 제거 후 끝에 다시 쓴다.
    raw = re.sub(r"\n*# 프리셋\(강조색\)별 태그[^\n]*\n", "\n", raw)
    raw = re.sub(r"(?ms)^preset_tags:\n(?:[ \t]+.*\n?)*", "", raw)
    block = ""
    if pt:
        body = yaml.safe_dump({"preset_tags": dict(sorted(pt.items()))},
                              allow_unicode=True, sort_keys=False)
        block = ("\n# 프리셋(강조색)별 태그 (서식 탭에서 편집) — 색마다 용도. "
                 "같은 태그를 여러 색에 주면 자동 순환. LLM은 <<태그:어구>>로 고름\n" + body)
    path.write_text(raw.rstrip("\n") + "\n" + block, encoding="utf-8")


def _prompt_preview() -> dict:
    """초안 생성에 쓰이는 프롬프트(편집용 raw default.md + 우리가 얹는 마커 지시문 레이어)."""
    from autoblog.draft.prompts import DEFAULT_PROMPT_PATH
    from autoblog.publish.emphasis import build_emphasis_instruction, load_emphasis_config
    from autoblog.publish.plan import build_structure_instruction
    from autoblog.publish.stickers import build_sticker_instruction, load_sticker_catalog

    dkeys, qkeys = _enabled_variant_keys()  # 미리보기도 현재 고른 종류만 반영
    layers = [
        ["강조 표시 (강조색 켤 때)", build_emphasis_instruction(load_emphasis_config())],
        ["구조 마커 (구분선·인용구 켤 때)", build_structure_instruction(dkeys, qkeys)],
    ]
    sticker_instr = build_sticker_instruction(load_sticker_catalog().labels())
    if sticker_instr:  # 보유 스티커 라벨이 있을 때만(감정·구분선 스티커 안내)
        layers.append(["스티커 (스티커 켤 때)", sticker_instr])
    return {
        "base_raw": DEFAULT_PROMPT_PATH.read_text(encoding="utf-8"),
        "layers": layers,
    }


def _save_prompt(text: str) -> None:
    from autoblog.draft.prompts import DEFAULT_PROMPT_PATH

    DEFAULT_PROMPT_PATH.write_text(text, encoding="utf-8")


def _ollama_installed() -> list[dict]:
    """로컬 Ollama에 실제 설치된 모델 목록(없거나 꺼져 있으면 빈 목록).

    각 항목: {name, size_gb, vision}(vision은 모델명으로 추정).
    """
    import requests

    from autoblog.config import load_env

    host = load_env().ollama_host
    try:
        data = requests.get(f"{host}/api/tags", timeout=3).json()
    except (requests.RequestException, ValueError):
        return []
    out = []
    for m in data.get("models", []):
        name = m.get("name", "")
        if not name:
            continue
        size = m.get("size") or 0
        out.append({
            "name": name,
            "size_gb": round(size / 1e9, 1) if size else None,
            "vision": _looks_vision(name),
        })
    out.sort(key=lambda x: x["name"])
    return out


# 모델명에 비전 능력이 드러나는 흔한 토큰(설치 모델 분류용 추정 — 100% 정확하진 않음)
_VISION_HINTS = ("vl", "vision", "llava", "moondream", "minicpm-v", "bakllava")


def _looks_vision(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in _VISION_HINTS)


def _models_info() -> dict:
    """현재 적용 모델 + 텍스트/비전 독립 선택용 후보(로컬 설치본 + 외부 API)."""
    from autoblog.config import load_env, load_models_config, provider_for_model

    cfg = load_models_config()
    eff = cfg.effective()
    presets = [
        {"key": k, "label": p.label, "text": p.text, "vision": p.vision,
         "note": p.note, "provider": p.provider, "concurrent_load": p.concurrent_load}
        for k, p in cfg.presets.items()
    ]
    # 외부 API 텍스트 모델 후보 — 프리셋에서 추출(provider별 중복 제거, 모델명 기준)
    api_text: dict[str, dict] = {}
    for p in cfg.presets.values():
        if p.provider != "ollama":
            api_text.setdefault(p.text, {
                "model": p.text, "provider": p.provider, "label": p.label,
            })
    env = load_env()
    return {
        "text": eff.text,
        "vision": eff.vision,
        "text_provider": eff.provider,
        "vision_provider": provider_for_model(eff.vision),  # 비전은 사실상 항상 ollama
        "installed": _ollama_installed(),
        "api_text": list(api_text.values()),
        "presets": presets,
        "default_preset": cfg.default,
        "keys": {
            "anthropic": bool(env.anthropic_api_key),
            "openai": bool(env.openai_api_key),
            "gemini": bool(env.gemini_api_key),
        },
    }


_LLM_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def _set_llm_key(provider: str, key: str) -> None:
    from autoblog.config import load_env, save_env_value

    env_var = _LLM_KEY_ENV.get(provider)
    if not env_var:
        raise ValueError(f"알 수 없는 provider: {provider!r}")
    save_env_value(env_var, key.strip())
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


def _write_models_yaml(data: dict) -> None:
    import yaml

    from autoblog.config import CONFIG_DIR, load_models_config

    path = CONFIG_DIR / "models.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    load_models_config.cache_clear()  # lru_cache 무효화


def _read_models_yaml() -> dict:
    import yaml

    from autoblog.config import CONFIG_DIR

    return yaml.safe_load((CONFIG_DIR / "models.yaml").read_text(encoding="utf-8"))


def _set_model_preset(key: str) -> None:
    """프리셋 한 방 적용 — 텍스트·비전 둘 다 그 프리셋 값으로 selection에 기록."""
    data = _read_models_yaml()
    preset = data.get("presets", {}).get(key)
    if not preset:
        return
    data["default"] = key
    data["selection"] = {"text": preset["text"], "vision": preset["vision"]}
    _write_models_yaml(data)


def _set_model_selection(text: str | None, vision: str | None) -> None:
    """텍스트/비전을 독립적으로 변경(준 값만 갱신, 나머지는 유지)."""
    data = _read_models_yaml()
    sel = dict(data.get("selection") or {})
    if text:
        sel["text"] = text
    if vision:
        sel["vision"] = vision
    data["selection"] = sel
    _write_models_yaml(data)


def _sticker_image(ref: str) -> Path | None:
    from autoblog.publish.stickers import load_sticker_catalog

    s = load_sticker_catalog().by_ref().get(ref)
    if not s or not s.image:
        return None
    p = Path(s.image)
    return p if p.is_absolute() else REPO_ROOT / p


def _catalog_summary() -> dict:
    from autoblog.publish.stickers import DEFAULT_PACKS, load_sticker_catalog

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
        "default_packs": sorted(DEFAULT_PACKS),
        "sponsor": cat.sponsor,  # 현재 협찬 고지로 지정된 스티커 ref(없으면 "")
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


def _set_sponsor_sticker(ref: str) -> str:
    """협찬 고지 스티커를 ref로 지정(같은 ref면 해제). 하나만 유지. 새 sponsor ref 반환."""
    from autoblog.publish.stickers import load_sticker_catalog, save_sticker_catalog

    cat = load_sticker_catalog()
    cat.sponsor = "" if cat.sponsor == ref else (ref if ref in cat.by_ref() else "")
    save_sticker_catalog(cat)
    return cat.sponsor


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
