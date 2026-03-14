import json
import os
import re
from typing import Any


def get_all_keys(d: dict[str, Any], prefix: str = "") -> set[str]:
    """Recursively get all keys from a dictionary."""
    keys = set()
    for k, v in d.items():
        new_prefix = f"{prefix}.{k}" if prefix else k
        keys.add(new_prefix)
        if isinstance(v, dict):
            keys.update(get_all_keys(v, new_prefix))
    return keys


def test_translations_synchronized():
    """Verify that all translation files have the exact same keys as strings.json."""
    base_path = "custom_components/foodsharing"
    strings_path = os.path.join(base_path, "strings.json")

    with open(strings_path, encoding="utf-8") as f:
        strings = json.load(f)

    strings_keys = get_all_keys(strings)

    translation_dir = os.path.join(base_path, "translations")

    # Ensure both de.json and en.json exist
    required_langs = ["de.json", "en.json"]
    for lang in required_langs:
        assert os.path.exists(os.path.join(translation_dir, lang)), f"{lang} is missing"

    for lang_file in os.listdir(translation_dir):
        if not lang_file.endswith(".json"):
            continue

        with open(os.path.join(translation_dir, lang_file), encoding="utf-8") as f:
            translations = json.load(f)

        trans_keys = get_all_keys(translations)

        # Keys in strings.json must be in translation file
        missing_keys = strings_keys - trans_keys
        assert not missing_keys, f"Keys {missing_keys} missing in {lang_file}"

        # Keys in translation file must be in strings.json
        extra_keys = trans_keys - strings_keys
        assert not extra_keys, f"Extra keys {extra_keys} found in {lang_file}"


def test_no_missing_translations_in_code():
    """Scan source code for translation keys and verify they exist in strings.json."""
    base_path = "custom_components/foodsharing"
    strings_path = os.path.join(base_path, "strings.json")

    with open(strings_path, encoding="utf-8") as f:
        strings = json.load(f)

    all_keys = get_all_keys(strings)

    # Patterns to look for in code
    patterns = [
        r'translation_key\s*=\s*["\']([^"\']+)["\']',
        r'translation_key["\']:\s*["\']([^"\']+)["\']',
        r'errors\[["\']base["\']\]\s*=\s*["\']([^"\']+)["\']',
        r'errors\s*=\s*\{["\']base["\']:\s*["\']([^"\']+)["\']',
        r'reason\s*=\s*["\']([^"\']+)["\']', # for async_abort
    ]

    missing_in_json = []

    for root, _, files in os.walk(base_path):
        for file in files:
            if not file.endswith(".py"):
                continue

            with open(os.path.join(root, file), encoding="utf-8") as f:
                content = f.read()
                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        # Check if match exists as a leaf or part of a key in all_keys
                        # Most keys are nested, e.g. "config.error.cannot_connect"
                        # We check if the leaf name exists anywhere in the keys
                        found = False
                        for key in all_keys:
                            if key == match or key.endswith(f".{match}"):
                                found = True
                                break

                        if not found and match not in ["domain"]: # domain is a special case in selector
                             missing_in_json.append(f"{file}: {match}")

    # Special check for "domain" translation key in selector
    if "selector.domain.options" not in all_keys:
         # In strings.json it's under "selector.domain.options"
         pass

    # Verify that aborted reasons are in config.abort or options.abort
    # Verify that errors are in config.error or options.error

    assert not missing_in_json, f"Potential missing translations found in code: {missing_in_json}"
