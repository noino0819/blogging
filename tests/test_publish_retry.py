"""/api/publish 실패 처리 — 안전 중단(PublishAborted)은 자동 재시도 없이 즉시 실패 탭으로.

자동 재시도(3회×20초)는 제거됨(2026-08-13): 실측상 중단 원인이 일시적 흔들림이
아니라 구조적 문제(맨 위 협찬 배너 앵커 등)라 재시도가 성공한 적이 없고,
브라우저를 여닫으며 편집기만 뒤흔들었다. 저장 전 중단은 멱등이므로 스냅샷을
남겨 실패 탭에서 수동 재시도(retryJob)한다 — 여기서는 그 경로만 검증한다.
"""
from __future__ import annotations

import json
import threading
import urllib.request

import pytest

import autoblog.webui as webui
from autoblog.publish.plan import PublishPlan


class _FakeCard:
    photos: list = []


class _FakeResult:
    def __init__(self):
        self.plan = PublishPlan(title="재시도 테스트", blocks=[])
        self.card = _FakeCard()


def _make_fake_pub(fail_times: int, calls: dict):
    """fail_times번 PublishAborted를 던진 뒤 성공하는 가짜 BlogPublisher."""
    from autoblog.publish.editor import PublishAborted

    class _FakePub:
        def __init__(self, headless=True):
            pass

        def start(self):
            return self

        def wait_for_login(self):
            return True

        def close(self):
            pass

        def publish_inplace(self, plan, **kw):
            calls["n"] += 1
            if calls["n"] <= fail_times:
                raise PublishAborted("저장 전 검증 중단(테스트)")
            return (["경고1"], [])

    return _FakePub


@pytest.fixture()
def ui():
    server = webui.serve_ui(port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _post_publish(url: str, extra: dict | None = None) -> tuple[int, dict]:
    payload = {"inplace": True, "inplaceDraft": {"title": "x", "date": ""}, **(extra or {})}
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{url}/api/publish", data=body, headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_abort_fails_immediately_then_manual_retry(ui, monkeypatch):
    """안전 중단 1번 = 즉시 실패(자동 재시도 없음) + 스냅샷(jobId).
    그 jobId로 수동 재시도하면 성공."""
    import autoblog.publish.editor as ed

    server, url = ui
    server.state["last"] = _FakeResult()
    calls = {"n": 0}
    monkeypatch.setattr(ed, "BlogPublisher", _make_fake_pub(99, calls))
    status, d = _post_publish(url)
    assert status == 500 and "중단" in (d.get("error") or ""), d
    assert calls["n"] == 1  # 자동 재시도 없이 한 번만 시도
    assert d.get("jobId")  # 수동 재시도(retryJob)용 스냅샷이 남는다

    # 수동 재시도: 스냅샷 그대로 다시 저장(이번엔 에디터가 멀쩡한 상황) → 성공
    calls2 = {"n": 0}
    monkeypatch.setattr(ed, "BlogPublisher", _make_fake_pub(0, calls2))
    status, d2 = _post_publish(url, {"retryJob": d["jobId"]})
    assert status == 200 and d2.get("ok"), d2
    assert calls2["n"] == 1


def test_retry_first_lock_priority():
    """점유 중 락에 일반→재시도 순서로 줄 서도, 풀리면 재시도가 먼저 잡는다."""
    import time

    lock = webui._RetryFirstLock()
    order: list[str] = []
    lock._acquire(False)  # 진행 중인 작업 상태로 시작

    def normal():
        with lock:
            order.append("normal")

    def retry():
        with lock.first():
            order.append("retry")

    t1 = threading.Thread(target=normal)
    t1.start()
    time.sleep(0.15)  # 일반이 먼저 줄 선다
    t2 = threading.Thread(target=retry)
    t2.start()
    time.sleep(0.15)  # 재시도가 뒤에 줄 선다
    lock.release()  # 진행 중이던 작업 종료 — 다음 차례는 재시도여야 함
    t1.join(3)
    t2.join(3)
    assert order == ["retry", "normal"]
