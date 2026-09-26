"""Учебный материал (п. 4.4): инструкция, памятка, классификатор, регламент. Тип файла определяется по содержимому,
а не по расширению. Текст режется на выдержки; поиск выдержек по теме — лексический (RAG на эмбеддингах — P2)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from aiskra.shared.errors import DomainError

MAX_BYTES = 25 * 2**20
PASSAGE_CHARS = 700


class MaterialKind(StrEnum):
    INSTRUCTION = "instruction"
    MEMO = "memo"
    CLASSIFIER = "classifier"
    REGULATION = "regulation"
    OTHER = "other"


class FileType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    TEXT = "txt"


CONTENT_TYPES = {
    FileType.PDF: "application/pdf",
    FileType.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    FileType.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FileType.TEXT: "text/plain; charset=utf-8",
}


def detect_type(filename: str, head: bytes) -> FileType:
    """Тип по сигнатуре: %PDF, ZIP (DOCX/XLSX — по расширению внутри ZIP-семейства), текст — валидный UTF-8."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if head.startswith(b"%PDF"):
        return FileType.PDF
    if head.startswith(b"PK\x03\x04"):
        if ext == "docx":
            return FileType.DOCX
        if ext == "xlsx":
            return FileType.XLSX
        raise DomainError("Из архивных форматов поддерживаются DOCX и XLSX", code="bad_file_type")
    if ext in ("txt", "md"):
        try:  # последние байты могут оборвать многобайтовый символ — их не проверяем
            head[: max(len(head) - 3, 1)].decode("utf-8")
        except UnicodeDecodeError as e:
            raise DomainError("Текстовый файл должен быть в UTF-8", code="bad_file_type") from e
        return FileType.TEXT
    raise DomainError("Поддерживаются PDF, DOCX, XLSX, TXT и MD", code="bad_file_type")


@dataclass
class Material:
    title: str
    kind: MaterialKind
    filename: str
    file_type: FileType
    size_bytes: int
    sha256: str
    uploaded_by: UUID
    text: str = ""
    visible: bool = True  # видно обучающимся
    use_in_prompts: bool = False  # выдержки подаются в генерацию сценариев
    created_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        self.title = " ".join(self.title.split())
        if not 3 <= len(self.title) <= 200:
            raise DomainError("Название — от 3 до 200 символов", code="bad_title")
        if self.size_bytes > MAX_BYTES:
            raise DomainError(f"Файл больше {MAX_BYTES // 2**20} МБ", code="file_too_large")
        if self.size_bytes == 0:
            raise DomainError("Пустой файл", code="empty_file")


def safe_filename(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[^\w .()\-]+", "_", base, flags=re.UNICODE).strip(" .")
    return (base or "file")[:150]


def passages(text: str, size: int = PASSAGE_CHARS) -> list[str]:
    """Выдержки по абзацам, не длиннее `size` символов (длинный абзац режется по предложениям)."""
    out: list[str] = []
    buf = ""
    for para in (p.strip() for p in re.split(r"\n\s*\n|\n", text)):
        if not para:
            continue
        pieces = [para] if len(para) <= size else re.split(r"(?<=[.!?;])\s+", para)
        for piece in pieces:
            piece = piece[:size]
            if buf and len(buf) + len(piece) + 1 > size:
                out.append(buf)
                buf = ""
            buf = f"{buf} {piece}".strip()
    if buf:
        out.append(buf)
    return out


_WORD = re.compile(r"[a-zа-яё0-9]{3,}")


def _stems(text: str) -> set[str]:
    """Грубая основа слова — первые 5 букв: «пожар», «пожара», «пожарный» совпадают."""
    return {w[:5] for w in _WORD.findall(text.lower().replace("ё", "е"))}


def best_passages(query: str, texts: list[tuple[str, str]], limit: int = 3) -> list[tuple[str, str]]:
    """Самые близкие к запросу выдержки: [(название материала, выдержка)]. Счёт — доля слов запроса в выдержке."""
    q = _stems(query)
    if not q:
        return []
    scored = []
    for title, text in texts:
        for p in passages(text):
            hit = len(q & _stems(p))
            if hit:
                scored.append((hit / len(q), -len(p), title, p))
    scored.sort(reverse=True)
    return [(t, p) for _, _, t, p in scored[:limit]]
