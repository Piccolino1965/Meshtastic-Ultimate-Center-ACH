# i18n.py
# Gestione multilingua compatibile con esecuzione normale e PyInstaller
# aiutocomputerhelp.it
# Giovanni Popolizio - anon@m00n
#-----------------------------------------

import json
import sys
from pathlib import Path


DEFAULT_LANGUAGE = "it"
SUPPORTED_LANGUAGES = ("it", "en")


def is_frozen():
    """True quando l'applicazione è stata compilata con PyInstaller."""
    return getattr(sys, "frozen", False)


def get_app_dir():
    """
    Cartella reale dell'applicazione.
    In sviluppo coincide con la cartella dei file .py.
    Nel compilato coincide con la cartella dove si trova l'eseguibile.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_resource_dir():
    """
    Cartella delle risorse.
    In sviluppo coincide con la cartella dei file .py.
    Nel compilato onefile coincide con la cartella temporanea interna usata da PyInstaller.
    """
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


APP_DIR = get_app_dir()
RESOURCE_DIR = get_resource_dir()

LOCALES_DIR = RESOURCE_DIR / "locales"
SETTINGS_FILE = APP_DIR / "settings.json"

_current_language = DEFAULT_LANGUAGE
_translations = {}
_fallback = {}


def _load_json(path):
    try:
        path = Path(path)
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_json(path, data):
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        return True
    except Exception as error:
        try:
            print(f"Errore salvataggio JSON {path}: {error}")
        except Exception:
            pass
        return False


def _deep_get(data, dotted_key, default=None):
    try:
        current = data
        for part in str(dotted_key).split("."):
            if not isinstance(current, dict):
                return default
            current = current.get(part)
            if current is None:
                return default
        return current
    except Exception:
        return default


def _language_file(language_code):
    """
    Cerca prima nella cartella locales, poi nella cartella risorse.
    Questo permette di funzionare sia con una struttura pulita locales/it.json,
    sia con i file lingua lasciati per errore accanto ai sorgenti.
    """
    path_in_locales = LOCALES_DIR / f"{language_code}.json"
    if path_in_locales.exists():
        return path_in_locales

    path_near_resources = RESOURCE_DIR / f"{language_code}.json"
    if path_near_resources.exists():
        return path_near_resources

    return path_in_locales


def normalize_language(language_code):
    language_code = str(language_code or "").strip().lower()
    if language_code in SUPPORTED_LANGUAGES:
        return language_code
    return DEFAULT_LANGUAGE


def get_saved_language():
    settings = _load_json(SETTINGS_FILE)

    if not settings:
        settings = {"language": DEFAULT_LANGUAGE}
        _save_json(SETTINGS_FILE, settings)

    return normalize_language(settings.get("language", DEFAULT_LANGUAGE))


def save_language(language_code):
    language_code = normalize_language(language_code)

    settings = _load_json(SETTINGS_FILE)
    if not isinstance(settings, dict):
        settings = {}

    settings["language"] = language_code
    return _save_json(SETTINGS_FILE, settings)


def load_language(language_code=None):
    global _current_language, _translations, _fallback

    language_code = normalize_language(language_code or get_saved_language())

    fallback_path = _language_file(DEFAULT_LANGUAGE)
    language_path = _language_file(language_code)

    _fallback = _load_json(fallback_path)
    _translations = _load_json(language_path)

    if not _translations:
        _translations = _fallback
        language_code = DEFAULT_LANGUAGE

    _current_language = language_code
    return _current_language


def current_language():
    """Restituisce la lingua attualmente caricata."""
    return _current_language


def available_languages():
    found = []
    for code in SUPPORTED_LANGUAGES:
        data = _load_json(_language_file(code))
        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        found.append({
            "code": code,
            "name": meta.get("language_name", code),
            "native_name": meta.get("native_name", meta.get("language_name", code))
        })
    return found


def tr(key, **kwargs):
    text = _deep_get(_translations, key)
    if text is None:
        text = _deep_get(_fallback, key)

    if text is None:
        return f"[{key}]"

    if not isinstance(text, str):
        return str(text)

    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text

    return text


def has_translation(key):
    return _deep_get(_translations, key) is not None or _deep_get(_fallback, key) is not None


# Alias breve opzionale.
_ = tr


# Caricamento automatico al primo import.
load_language()
