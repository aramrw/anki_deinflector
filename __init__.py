from __future__ import annotations

import atexit
import os
from typing import Any, Optional

from aqt import gui_hooks, mw
from aqt.qt import QAction

from .highlighter import DeinflectorClient, highlight_card_html, resolve_binary_path

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "language": "es",
    "deck_languages": {
        "deutch": "de",
        "deutsch": "de",
        "german": "de",
        "espanol": "es",
        "español": "es",
        "spanish": "es",
    },
    "word_field": "wordDictionaryForm",
    "sentence_field": "sentence",
    "sentence_element_id": "sentence",
    "highlight_class": "highlight",
    "deck_prefixes": [],
    "binary_path": "/Users/aramsamifanni/Programming/yomichan/yomichan_rs_workspace/target/release/deinflector",
}

_client: Optional[DeinflectorClient] = None
_client_bin_path: Optional[str] = None
_config_cache: Optional[dict[str, Any]] = None
_toggle_action: Optional[QAction] = None


def _get_config() -> dict[str, Any]:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    cfg = dict(DEFAULT_CONFIG)
    if mw is not None and mw.addonManager is not None:
        loaded = mw.addonManager.getConfig(__name__)
        if isinstance(loaded, dict):
            cfg.update(loaded)
    _config_cache = cfg
    return cfg


def _get_client(cfg: dict[str, Any]) -> Optional[DeinflectorClient]:
    global _client, _client_bin_path
    resolved = resolve_binary_path(cfg.get("binary_path"), ADDON_DIR)
    if not resolved:
        return None
    if _client is not None and _client_bin_path == resolved:
        return _client
    if _client is not None:
        _client.close()
    _client = DeinflectorClient(resolved)
    _client_bin_path = resolved
    return _client


def _shutdown_client() -> None:
    global _client, _client_bin_path
    if _client is not None:
        _client.close()
        _client = None
        _client_bin_path = None


def _get_deck_name(card: Any) -> str:
    try:
        return mw.col.decks.name(card.did)
    except Exception:
        return ""


def _deck_matches(deck_name: str, deck_prefixes: list[str]) -> bool:
    if not deck_prefixes:
        return True
    if not deck_name:
        return True
    return any(deck_name == prefix or deck_name.startswith(prefix + "::") for prefix in deck_prefixes)


def _resolve_language(deck_name: str, cfg: dict[str, Any]) -> str:
    deck_languages = cfg.get("deck_languages")
    if isinstance(deck_languages, dict) and deck_name:
        deck_lower = deck_name.lower()
        best_prefix = ""
        best_lang = None
        for prefix, lang in deck_languages.items():
            if not isinstance(prefix, str) or not isinstance(lang, str):
                continue
            prefix_lower = prefix.lower()
            if (deck_lower == prefix_lower or deck_lower.startswith(prefix_lower + "::")) and len(prefix_lower) > len(best_prefix):
                best_prefix = prefix_lower
                best_lang = lang
        if best_lang:
            return best_lang
    return cfg.get("language", "es")


def on_card_will_show(text: str, card: Any, kind: str) -> str:
    cfg = _get_config()
    if not cfg.get("enabled", True):
        return text

    deck_name = _get_deck_name(card)
    deck_prefixes = cfg.get("deck_prefixes") or []
    if not _deck_matches(deck_name, deck_prefixes):
        return text

    try:
        note = card.note()
    except Exception:
        return text

    word_field = cfg.get("word_field", "wordDictionaryForm")
    sentence_field = cfg.get("sentence_field", "sentence")
    if word_field not in note or sentence_field not in note:
        return text

    raw_word = note[word_field]
    raw_sentence = note[sentence_field]
    if not raw_word or not raw_sentence:
        return text

    client = _get_client(cfg)
    if client is None:
        return text

    return highlight_card_html(
        text,
        raw_sentence,
        raw_word,
        client,
        lang=_resolve_language(deck_name, cfg),
        css_class=cfg.get("highlight_class", "highlight"),
        sentence_element_id=cfg.get("sentence_element_id", "sentence"),
    )


def _on_config_updated(new_config: dict[str, Any]) -> None:
    global _config_cache
    merged = dict(DEFAULT_CONFIG)
    if isinstance(new_config, dict):
        merged.update(new_config)
    _config_cache = merged
    if _toggle_action is not None:
        _toggle_action.setChecked(bool(merged.get("enabled", True)))


def _toggle_enabled(checked: bool) -> None:
    cfg = dict(_get_config())
    cfg["enabled"] = bool(checked)
    _on_config_updated(cfg)
    if mw is not None and mw.addonManager is not None:
        mw.addonManager.writeConfig(__name__, cfg)


def _setup_menu() -> None:
    global _toggle_action
    if mw is None or mw.form is None:
        return
    action = QAction("Deinflector Sentence Highlighter", mw)
    action.setCheckable(True)
    action.setChecked(bool(_get_config().get("enabled", True)))
    action.triggered.connect(_toggle_enabled)
    mw.form.menuTools.addAction(action)
    _toggle_action = action


gui_hooks.card_will_show.append(on_card_will_show)
gui_hooks.profile_will_close.append(_shutdown_client)
gui_hooks.main_window_did_init.append(_setup_menu)
if mw is not None and mw.addonManager is not None:
    mw.addonManager.setConfigUpdatedAction(__name__, _on_config_updated)
atexit.register(_shutdown_client)
