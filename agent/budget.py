"""预算控制 + 中断信号"""

import threading


class IterationBudget:
    """线程安全的迭代预算控制器

    跟踪剩余可用迭代次数，支持中断信号和 grace call。
    """

    def __init__(self, max_iterations: int = 50):
        self.max_iterations = max_iterations
        self._remaining = max_iterations
        self._interrupted = False
        self._lock = threading.Lock()
        self._grace_call_used = False

    @property
    def remaining(self) -> int:
        """剩余可用迭代次数"""
        with self._lock:
            return self._remaining

    @property
    def is_interrupted(self) -> bool:
        """是否收到中断信号"""
        return self._interrupted

    def consume(self) -> bool:
        """消耗一次迭代预算

        Returns:
            True 如果预算仍有剩余，False 如果已耗尽
        """
        with self._lock:
            if self._remaining > 0:
                self._remaining -= 1
                return True
            return False

    def can_continue(self) -> bool:
        """检查是否可以继续迭代

        包括 grace call 的可能性
        """
        with self._lock:
            if self._interrupted:
                return False
            if self._remaining > 0:
                return True
            # 预算耗尽，允许一次 grace call
            if not self._grace_call_used:
                self._grace_call_used = True
                return True
            return False

    def interrupt(self) -> None:
        """发送中断信号"""
        self._interrupted = True

    def reset(self) -> None:
        """重置预算和中断状态"""
        with self._lock:
            self._remaining = self.max_iterations
            self._interrupted = False
            self._grace_call_used = False
