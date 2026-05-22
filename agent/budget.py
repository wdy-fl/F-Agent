"""预算控制 + 中断信号"""

import threading


class IterationBudget:
    """线程安全的迭代预算控制器

    跟踪剩余可用迭代次数，支持中断信号。
    """

    def __init__(self, max_iterations: int = 50):
        self.max_iterations = max_iterations
        self._remaining = max_iterations
        self._interrupted = False
        self._lock = threading.Lock()

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
        """检查是否可以继续正常迭代"""
        with self._lock:
            return not self._interrupted and self._remaining > 0

    def interrupt(self) -> None:
        """发送中断信号"""
        self._interrupted = True

    def reset(self) -> None:
        """重置预算和中断状态"""
        with self._lock:
            self._remaining = self.max_iterations
            self._interrupted = False
