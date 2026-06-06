#!/usr/bin/env python3
import os, sys

stub_dir = os.path.join(os.getcwd(), "oneminai-venv", "lib", "python3.12", "site-packages", "litellm")
os.makedirs(stub_dir, exist_ok=True)
stub_path = os.path.join(stub_dir, "__init__.py")

with open("/data/data/com.termux/files/home/litellm_stub_proot.py") as f:
    content = f.read()

with open(stub_path, "w") as f:
    f.write(content)

print(f"Stub installed at: {stub_path}")

# Verify
sys.path.insert(0, stub_dir)
try:
    import litellm
    print("Import OK - has acompletion:", hasattr(litellm, 'acompletion'))
except Exception as e:
    print(f"Import failed: {e}")
