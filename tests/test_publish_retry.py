"""/api/publish 자동 재시도 — 안전 중단(PublishAborted)은 실패로 끝내지 않고 재시도한다.

실사고(2026-08-11): 일시적 에디터 상태로 저장 전 검증이 중단됐을 때, 사람이 다시
누르지 않아도 서버가 새 브라우저로 자동 재시도해 성공해야 한다(최대 3회).
가짜 퍼블리셔로 편집기 없이 재시도 루프만 검증한다(time.sleep은 무력화).
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
def ui(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)  # 재시도 대기 무력화(테스트 속도)
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


def test_auto_retry_recovers(ui, monkeypatch):
    """2번 안전 중단 후 3번째 성공 — 응답은 성공 + 자동 재시도 안내 info."""
    import autoblog.publish.editor as ed

    server, url = ui
    server.state["last"] = _FakeResult()
    calls = {"n": 0}
    monkeypatch.setattr(ed, "BlogPublisher", _make_fake_pub(2, calls))
    status, d = _post_publish(url)
    assert status == 200 and d.get("ok"), d
    assert calls["n"] == 3
    assert any("다시 시도" in m for m in d.get("infos", [])), d.get("infos")
    assert d.get("warnings") == ["경고1"]


def test_auto_retry_exhausted_then_manual(ui, monkeypatch):
    """3번 전부 안전 중단 → 실패 + 스냅샷(jobId). 그 jobId로 수동 재시도하면 성공."""
    import autoblog.publish.editor as ed

    server, url = ui
    server.state["last"] = _FakeResult()
    calls = {"n": 0}
    monkeypatch.setattr(ed, "BlogPublisher", _make_fake_pub(99, calls))
    status, d = _post_publish(url)
    assert status == 500 and "중단" in (d.get("error") or ""), d
    assert calls["n"] == 3  # 자동 재시도 소진 후 멈춤
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
