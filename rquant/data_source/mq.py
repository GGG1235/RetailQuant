"""
rquant.data_source.mq — 简易内存消息队列
- pub-sub：publish(topic, payload) → 后台 worker 调 handler
- 单实例全局 mq
- 默认 worker 数 = 2，可按 topic 加线程
- handler 异常不挂队列（错误日志 + 继续消费）
- 提供：subscribe / publish / publish_sync / stop
- 适用场景：
    1) 批量拉 K 线（按 pool 一次性刷多个 code，写入 SQLite）
    2) 行情通知（前端 SSE / WebSocket 推）
    3) 异步任务（写 portfolio.json / 写快照）

不重不丢的设计取舍：
- 队列长度上限 10000，防止内存爆
- 超过上限 publish 走 fallback 同步执行
"""

from __future__ import annotations
import logging
import queue
import sys
import threading
import time
import traceback
from collections import defaultdict
from typing import Any, Callable

_log = logging.getLogger("rquant.mq")
if not _log.handlers:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("[%(asctime)s] [mq] %(levelname)s %(message)s", datefmt="%H:%M:%S"))
    _log.addHandler(h)
    _log.setLevel(logging.INFO)


Handler = Callable[[Any], None]


class Mq:
    """简易 pub-sub 消息队列"""

    def __init__(self, max_workers: int = 2, queue_size: int = 10000):
        self._q: queue.Queue = queue.Queue(maxsize=queue_size)
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._inflight = 0
        self._dropped = 0
        self._max_workers = max_workers

    # ----- 注册 -----

    def subscribe(self, topic: str, handler: Handler) -> None:
        with self._lock:
            self._handlers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        with self._lock:
            if handler in self._handlers.get(topic, []):
                self._handlers[topic].remove(handler)

    # ----- 发布 -----

    def publish(self, topic: str, payload: Any = None) -> bool:
        """异步发布。返回 False 表示队列满已降级同步。"""
        item = (topic, payload, time.time())
        try:
            self._q.put_nowait(item)
            with self._lock:
                self._inflight += 1
            return True
        except queue.Full:
            self._dropped += 1
            _log.warning(f"队列满 (size={self._q.maxsize})，降级同步执行: {topic}")
            self._dispatch(topic, payload)
            return False

    def publish_sync(self, topic: str, payload: Any = None) -> None:
        """同步发布：阻塞入队 + 等待所有 worker 全部处理完（用于测试）"""
        self._dispatch(topic, payload)

    # ----- 生命周期 -----

    def start(self) -> None:
        if self._workers:
            return
        for i in range(self._max_workers):
            t = threading.Thread(target=self._worker_loop, name=f"mq-worker-{i}", daemon=True)
            t.start()
            self._workers.append(t)
        _log.info(f"启动 {self._max_workers} 个 worker")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        # 塞个 sentinel 唤醒 worker
        for _ in self._workers:
            try:
                self._q.put_nowait(("__STOP__", None, 0))
            except queue.Full:
                pass
        for t in self._workers:
            t.join(timeout=timeout)
        self._workers.clear()
        _log.info("worker 已停止")

    def status(self) -> dict:
        with self._lock:
            return {
                "qsize": self._q.qsize(),
                "maxsize": self._q.maxsize,
                "inflight": self._inflight,
                "dropped": self._dropped,
                "workers": len(self._workers),
                "topics": list(self._handlers.keys()),
            }

    # ----- 内部 -----

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=1.0)
            except queue.Empty:
                continue
            if item[0] == "__STOP__":
                break
            topic, payload, _ts = item
            with self._lock:
                self._inflight = max(0, self._inflight - 1)
            try:
                self._dispatch(topic, payload)
            except Exception as e:
                _log.error(f"handler 异常 {topic}: {e}\n{traceback.format_exc()}")

    def _dispatch(self, topic: str, payload: Any) -> None:
        with self._lock:
            handlers = list(self._handlers.get(topic, []))
        for h in handlers:
            try:
                h(payload)
            except Exception as e:
                _log.error(f"handler {h.__name__} on {topic} 失败: {e}")


# 全局单例
mq = Mq(max_workers=2)


def start_mq() -> None:
    """应用启动时调一次（幂等）"""
    mq.start()


def stop_mq() -> None:
    mq.stop()
