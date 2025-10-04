# scripts/debug_reddit_auth.py
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.tools.reddit_client import reddit_readonly

r = reddit_readonly()
print("OK. read_only =", getattr(r, "read_only", None))
try:
    sc = r.auth.scopes()
    print("Scopes:", sorted(sc) if sc else sc)
except Exception as e:
    print("Scopes check failed:", repr(e))
