import re


def _split_long(paragraph: str, size: int, overlap: int) -> list[str]:
    out: list[str] = []
    start = 0
    n = len(paragraph)
    while start < n:
        end = min(start + size, n)
        if end < n:
            space = paragraph.rfind(" ", start + size // 2, end)
            if space != -1:
                end = space
        piece = paragraph[start:end].strip()
        if piece:
            out.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)  # always move forward
    return out


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    """Paragraph-aware chunking. Short paragraphs are packed together up to `size`
    characters; paragraphs longer than `size` are split with `overlap`."""
    text = text.replace("\r\n", "\n")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        if len(p) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long(p, size, overlap))
        elif current and len(current) + 2 + len(p) > size:
            chunks.append(current)
            current = p
        else:
            current = f"{current}\n\n{p}" if current else p
    if current:
        chunks.append(current)
    return chunks
