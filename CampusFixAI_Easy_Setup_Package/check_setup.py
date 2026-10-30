import importlib
import sys
print("Python:", sys.version)
for name in ("flask", "flask_wtf", "PIL"):
    try:
        mod = importlib.import_module(name)
        print(name + ": OK", getattr(mod, "__version__", ""))
    except Exception as exc:
        print(name + ": ERROR", exc)
