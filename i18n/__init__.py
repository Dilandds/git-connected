"""
Lightweight i18n engine for ECTOFORM.

Usage:
    from i18n import t, set_language, on_language_changed, get_language

    label.setText(t("sidebar.upload"))
    on_language_changed(self.retranslate)
"""
import json
import os
import logging
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)

_translations: Dict[str, dict] = {}
_current_lang: str = "en"
_listeners: List[Callable] = []


def _load_translations():
    """Load all JSON translation files from the i18n directory."""
    global _translations
    i18n_dir = os.path.dirname(os.path.abspath(__file__))
    for lang in ("en", "fr"):
        path = os.path.join(i18n_dir, f"{lang}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                _translations[lang] = json.load(f)
        except Exception as e:
            logger.warning(f"i18n: Could not load {path}: {e}")
            _translations[lang] = {}


def t(key: str) -> str:
    """Look up a dotted key (e.g. 'sidebar.upload') in the current language.
    Returns the key itself if not found."""
    if not _translations:
        _load_translations()
    data = _translations.get(_current_lang, {})
    for part in key.split("."):
        if isinstance(data, dict):
            data = data.get(part)
        else:
            return key
        if data is None:
            return key
    if isinstance(data, str):
        return data
    return key


def get_language() -> str:
    return _current_lang


def set_language(lang: str):
    """Switch language and notify all listeners."""
    global _current_lang
    if lang not in ("en", "fr"):
        return
    if lang == _current_lang:
        return
    _current_lang = lang
    logger.info(f"i18n: Language changed to {lang}")
    # Copy list to avoid issues if a listener registers/unregisters during iteration
    for cb in list(_listeners):
        try:
            cb()
        except Exception as e:
            logger.error(f"i18n: Listener error: {e}")


def on_language_changed(callback: Callable):
    """Register a callback to be invoked when language changes."""
    if callback not in _listeners:
        _listeners.append(callback)


def remove_language_listener(callback: Callable):
    """Unregister a language-change callback."""
    try:
        _listeners.remove(callback)
    except ValueError:
        pass


# Pre-load on import
_load_translations()
