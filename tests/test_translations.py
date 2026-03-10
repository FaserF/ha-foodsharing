import json
import os

def test_translations_synchronized():
    """Verify that all translation files have the same keys as strings.json."""
    base_path = "custom_components/foodsharing"
    strings_path = os.path.join(base_path, "strings.json")
    
    with open(strings_path, encoding="utf-8") as f:
        strings = json.load(f)
        
    translation_dir = os.path.join(base_path, "translations")
    for lang_file in os.listdir(translation_dir):
        if not lang_file.endswith(".json"):
            continue
            
        with open(os.path.join(translation_dir, lang_file), encoding="utf-8") as f:
            translations = json.load(f)
            
        # Basic check: root keys should match (config, options, issues, services)
        # Note: services might not be in strings.json if they don't have descriptions there,
        # but in this project they are in all files.
        for key in strings:
            assert key in translations, f"Key '{key}' missing in {lang_file}"
            
        # Check config steps
        if "config" in strings and "step" in strings["config"]:
            for step in strings["config"]["step"]:
                assert step in translations["config"]["step"], f"Config step '{step}' missing in {lang_file}"
                
        # Check errors
        if "config" in strings and "error" in strings["config"]:
            for err in strings["config"]["error"]:
                assert err in translations["config"]["error"], f"Config error '{err}' missing in {lang_file}"

        # Check issues
        if "issues" in strings:
            for issue in strings["issues"]:
                assert issue in translations["issues"], f"Issue '{issue}' missing in {lang_file}"
