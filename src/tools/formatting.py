from __future__ import annotations

from html.parser import HTMLParser


_LINE_BREAKS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _LINE_BREAKS or tag == "hr":
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _LINE_BREAKS:
            self._parts.append("\n")

    def text(self) -> str:
        return "".join(self._parts)


def html_to_text(value: object) -> str:
    """Ubah field HTML SonarQube (htmlDesc/htmlExample/fixRecommendations) jadi teks plain."""
    if value is None:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(str(value))
        parser.close()
    except Exception:
        return " ".join(str(value).split())
    lines = []
    for line in parser.text().splitlines():
        cleaned = " ".join(line.split())
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)
