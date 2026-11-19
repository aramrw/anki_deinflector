from __future__ import annotations

import html
from html.parser import HTMLParser
import json
import os
import re
import shutil
import subprocess
import threading
import unicodedata
from typing import Iterable, Optional

WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
LATIN_LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿẞ]")
CJK_OR_KANA_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")
TAG_STRIP_RE = re.compile(r"<[^>]+>")

VOID_HTML_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})

SKIP_ANCESTOR_TAGS = frozenset({"span", "a", "script", "style", "ruby", "rt"})


def resolve_binary_path(configured_path: Optional[str] = None, addon_dir: Optional[str] = None) -> Optional[str]:
    candidates = []
    if configured_path:
        candidates.append(os.path.expanduser(configured_path))
    if addon_dir:
        candidates.append(os.path.join(addon_dir, "bin", "deinflector"))
    candidates.append(
        "/Users/aramsamifanni/Programming/yomichan/yomichan_rs_workspace/target/release/deinflector"
    )
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which("deinflector")


def strip_html_to_text(raw: str) -> str:
    if not raw:
        return ""
    return html.unescape(TAG_STRIP_RE.sub("", raw))


def is_latin_word(word: str) -> bool:
    if not word:
        return False
    if CJK_OR_KANA_RE.search(word):
        return False
    return bool(LATIN_LETTER_RE.search(word))


def is_latin_spanish_word(word: str) -> bool:
    return is_latin_word(word)


class DeinflectorClient:
    """Thread-safe wrapper around a persistent `deinflector serve` subprocess."""

    def __init__(self, binary_path: str) -> None:
        self.binary_path = binary_path
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen[str]] = None

    def _ensure_started(self) -> subprocess.Popen[str]:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        self._proc = subprocess.Popen(
            [self.binary_path, "serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        return self._proc

    def close(self) -> None:
        with self._lock:
            self._terminate_locked()

    def _terminate_locked(self) -> None:
        if self._proc is None:
            return
        proc = self._proc
        self._proc = None
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=1.0)
        except (OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
                proc.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                pass
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def match_tokens(self, lang: str, target: str, tokens: list[str]) -> list[int]:
        if not tokens or not target:
            return []
        payload = json.dumps(
            {"op": "match", "lang": lang, "target": target, "tokens": tokens},
            ensure_ascii=False,
        )
        with self._lock:
            for attempt in range(2):
                proc = self._ensure_started()
                try:
                    assert proc.stdin is not None and proc.stdout is not None
                    proc.stdin.write(payload + "\n")
                    proc.stdin.flush()
                    line = proc.stdout.readline()
                    if not line:
                        raise EOFError("deinflector serve closed stdout")
                    resp = json.loads(line)
                    if not resp.get("ok"):
                        return []
                    return list(resp.get("matched_indices", []))
                except (OSError, EOFError, ValueError):
                    self._terminate_locked()
                    if attempt == 1:
                        return []
        return []


def _format_start_tag(tag: str, attrs: list[tuple[str, Optional[str]]], self_closing: bool = False) -> str:
    parts = [tag]
    for name, value in attrs:
        if value is None:
            parts.append(name)
        else:
            parts.append(f'{name}="{html.escape(value, quote=True)}"')
    suffix = " />" if self_closing else ">"
    return "<" + " ".join(parts) + suffix


class _FragmentHighlighter(HTMLParser):
    def __init__(
        self,
        target_word: str,
        client: DeinflectorClient,
        lang: str,
        css_class: str,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.target_word = target_word
        self.client = client
        self.lang = lang
        self.css_class = css_class
        self.output: list[str] = []
        self.tag_stack: list[tuple[str, bool]] = []

    def _is_skipped(self) -> bool:
        return any(skip for _, skip in self.tag_stack)

    @staticmethod
    def _should_skip_tag(tag_lower: str, attrs: list[tuple[str, Optional[str]]]) -> bool:
        if tag_lower in SKIP_ANCESTOR_TAGS:
            return True
        for name, value in attrs:
            if name.lower() == "class" and value is not None and value.strip() != "":
                return True
        return False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag_lower = tag.lower()
        self.output.append(_format_start_tag(tag, attrs, self_closing=False))
        if tag_lower not in VOID_HTML_TAGS:
            skip = self._should_skip_tag(tag_lower, attrs)
            self.tag_stack.append((tag_lower, skip))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        self.output.append(_format_start_tag(tag, attrs, self_closing=True))

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        self.output.append(f"</{tag}>")
        for idx in range(len(self.tag_stack) - 1, -1, -1):
            if self.tag_stack[idx][0] == tag_lower:
                del self.tag_stack[idx:]
                break

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self._is_skipped():
            self.output.append(html.escape(data, quote=False))
            return

        normalized = unicodedata.normalize("NFC", data)
        matches = list(WORD_RE.finditer(normalized))
        if not matches:
            self.output.append(html.escape(normalized, quote=False))
            return

        tokens = [m.group(0) for m in matches]
        matched_indices = set(self.client.match_tokens(self.lang, self.target_word, tokens))
        if not matched_indices:
            self.output.append(html.escape(normalized, quote=False))
            return

        cls_escaped = html.escape(self.css_class, quote=True)
        cursor = 0
        for idx, match in enumerate(matches):
            start, end = match.span()
            if start > cursor:
                self.output.append(html.escape(normalized[cursor:start], quote=False))
            token_escaped = html.escape(normalized[start:end], quote=False)
            if idx in matched_indices:
                self.output.append(f'<span class="{cls_escaped}">{token_escaped}</span>')
            else:
                self.output.append(token_escaped)
            cursor = end
        if cursor < len(normalized):
            self.output.append(html.escape(normalized[cursor:], quote=False))

    def handle_comment(self, data: str) -> None:
        self.output.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self.output.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self.output.append(f"<?{data}>")


def highlight_html_fragment(
    fragment: str,
    target_word: str,
    client: DeinflectorClient,
    *,
    lang: str = "es",
    css_class: str = "highlight",
) -> str:
    if not fragment or not target_word:
        return fragment
    parser = _FragmentHighlighter(target_word, client, lang, css_class)
    parser.feed(fragment)
    parser.close()
    return "".join(parser.output)


_TAG_TOKEN_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9:-]*)([^>]*)>", re.DOTALL)
_ID_ATTR_RE = re.compile(r"""\bid\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""", re.IGNORECASE)


def _find_element_inner_spans(html_text: str, element_id: str) -> list[tuple[int, int]]:
    """Finds `(inner_start, inner_end)` spans for elements with `id == element_id`."""
    spans: list[tuple[int, int]] = []
    pos = 0
    n = len(html_text)
    while pos < n:
        match = _TAG_TOKEN_RE.search(html_text, pos)
        if not match:
            break
        is_close, tag_name, attrs_str = match.group(1), match.group(2).lower(), match.group(3)
        if is_close or attrs_str.rstrip().endswith("/") or tag_name in VOID_HTML_TAGS:
            pos = match.end()
            continue

        id_match = _ID_ATTR_RE.search(attrs_str)
        attr_id = None
        if id_match:
            attr_id = id_match.group(1) or id_match.group(2) or id_match.group(3)
        if attr_id != element_id:
            pos = match.end()
            continue

        inner_start = match.end()
        depth = 1
        scan_pos = inner_start
        while scan_pos < n and depth > 0:
            inner_match = _TAG_TOKEN_RE.search(html_text, scan_pos)
            if not inner_match:
                break
            m_close, m_tag, m_attrs = (
                inner_match.group(1),
                inner_match.group(2).lower(),
                inner_match.group(3),
            )
            if m_tag == tag_name:
                if m_close:
                    depth -= 1
                    if depth == 0:
                        spans.append((inner_start, inner_match.start()))
                        pos = inner_match.end()
                        break
                elif not m_attrs.rstrip().endswith("/") and m_tag not in VOID_HTML_TAGS:
                    depth += 1
            scan_pos = inner_match.end()
        else:
            pos = match.end()
    return spans


def highlight_card_html(
    card_html: str,
    raw_sentence: str,
    raw_word: str,
    client: DeinflectorClient,
    *,
    lang: str = "es",
    css_class: str = "highlight",
    sentence_element_id: str = "sentence",
) -> str:
    target_word = strip_html_to_text(raw_word).strip()
    if not target_word:
        return card_html
    if lang in ("es", "de", "en") and not is_latin_word(target_word):
        return card_html

    if sentence_element_id:
        spans = _find_element_inner_spans(card_html, sentence_element_id)
        if spans:
            pieces: list[str] = []
            cursor = 0
            for start, end in spans:
                pieces.append(card_html[cursor:start])
                pieces.append(
                    highlight_html_fragment(
                        card_html[start:end],
                        target_word,
                        client,
                        lang=lang,
                        css_class=css_class,
                    )
                )
                cursor = end
            pieces.append(card_html[cursor:])
            return "".join(pieces)

    # Fallback if template does not wrap the sentence in `#sentence`.
    if raw_sentence and raw_sentence.strip() != raw_word.strip() and raw_sentence in card_html:
        highlighted_sentence = highlight_html_fragment(
            raw_sentence,
            target_word,
            client,
            lang=lang,
            css_class=css_class,
        )
        if highlighted_sentence != raw_sentence:
            return card_html.replace(raw_sentence, highlighted_sentence)

    return card_html
