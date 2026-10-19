"""Текст потокового ответа (F1): ремарки заявителя в квадратных скобках не печатаются посимвольно, а приходят
целиком отдельным событием — как и в готовой реплике (`psy_render.parse_remarks`)."""

from __future__ import annotations

MAX_REMARK = 80  # «[» без закрывающей скобки дольше этого — не ремарка, а текст


class RemarkFilter:
    def __init__(self) -> None:
        self._buf = ""
        self.remarks: list[str] = []

    def feed(self, piece: str) -> str:
        """Кусок потока → видимый текст; найденные ремарки копятся в `remarks` (вызывающий их забирает)."""
        s, self._buf = self._buf + piece, ""
        out: list[str] = []
        i = 0
        while i < len(s):
            if s[i] == "[":
                j = s.find("]", i)
                if j == -1:
                    if len(s) - i <= MAX_REMARK:
                        self._buf = s[i:]
                        break
                    out.append(s[i])
                    i += 1
                    continue
                remark = s[i + 1 : j].strip()
                if remark:
                    self.remarks.append(remark)
                i = j + 1
                continue
            out.append(s[i])
            i += 1
        return "".join(out)

    def flush(self) -> str:
        rest, self._buf = self._buf, ""
        return rest

    def take_remarks(self) -> list[str]:
        out, self.remarks = self.remarks, []
        return out
