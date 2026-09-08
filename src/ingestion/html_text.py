"""Convert the HTML fragments served by content APIs into markdown.

Kept deliberately small and dependency-free: the input is machine-generated
CMS markup (paragraphs, lists, headings, links), not arbitrary web pages, so
stdlib `HTMLParser` is enough and adds no supply-chain surface. It is a real
parser, not a regex strip — tags inside attribute values and stray angle
brackets are handled correctly.
"""
import re
from html.parser import HTMLParser

_HEADINGS = {f"h{level}": level for level in range(1, 7)}

# Tags that end the current line of text.
_BLOCK_TAGS = {
    "p", "div", "section", "article", "ul", "ol", "table", "tr",
    "blockquote", "dl", "dt", "dd",
}

# Content that is markup machinery, never prose.
_SKIP_TAGS = {"script", "style", "head", "noscript"}


class _MarkdownExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if tag in _HEADINGS:
            self._parts.append("\n\n" + "#" * _HEADINGS[tag] + " ")
        elif tag == "li":
            self._parts.append("\n- ")
        elif tag == "br":
            self._parts.append("\n")
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return

        if tag in _HEADINGS or tag in _BLOCK_TAGS or tag == "li":
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        # Collapse intra-tag whitespace; block structure is carried by the
        # markers the tag handlers push, not by the source formatting.
        self._parts.append(re.sub(r"\s+", " ", data))

    def result(self) -> str:
        text = "".join(self._parts)
        # Trim spaces that ended up around the inserted line breaks.
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_markdown(html: str) -> str:
    """Render an HTML fragment as markdown-ish plain text."""
    parser = _MarkdownExtractor()
    parser.feed(html)
    parser.close()
    return parser.result()
