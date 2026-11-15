"""Same new mutants, but run against the new test PLUS the Qt-less existing modules that could notice (defense in depth)."""
import importlib.util

spec = importlib.util.spec_from_file_location("my_mut_ap15", "C:/work/ai/verify_app15_2/my_mut_ap15.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

MODULES = ["test_ui_sentence_color", "test_ui_core", "test_ui_c1a_core"]
MUTATIONS = {}
for key in ("NM1", "NM2", "NM4", "NM5", "NM6", "NM10", "NM13"):
    MUTATIONS[key + "s"] = {**base.MUTATIONS[key], "modules": MODULES}
