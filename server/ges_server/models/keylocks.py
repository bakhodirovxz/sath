"""Kalit bo'yicha qulflar — chegaralangan LRU (OPS-04, SRV-04).

Ilgari har noyob kalit (sha, clash turlari) uchun `threading.Lock` lug'atga abadiy qo'shilardi — so'rov
parametrlari bilan xotirani to'ldirish mumkin edi. Endi eng ko'pi bilan `maxsize` ta; eskisi faqat bo'sh
(ushlanmagan) bo'lsa chiqariladi, shuning uchun ushlab turilgan qulf hech qachon ikkiga bo'linmaydi.
"""

from __future__ import annotations

import threading
from collections import OrderedDict


class KeyLocks:
    def __init__(self, maxsize: int = 256) -> None:
        self.maxsize = maxsize
        self._locks: OrderedDict[str, threading.Lock] = OrderedDict()
        self._guard = threading.Lock()

    def get(self, key: str) -> threading.Lock:
        with self._guard:
            lk = self._locks.get(key)
            if lk is not None:
                self._locks.move_to_end(key)
                return lk
            lk = self._locks[key] = threading.Lock()
            if len(self._locks) > self.maxsize:
                for k in list(self._locks):
                    if len(self._locks) <= self.maxsize:
                        break
                    if k != key and not self._locks[k].locked():
                        del self._locks[k]
            return lk

    def __len__(self) -> int:
        return len(self._locks)
