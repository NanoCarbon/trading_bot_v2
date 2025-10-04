# main.py
import argparse
import sys

from src.config import load_config
from src.collector import run_once


def print_section(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(description="Collect pillar votes and store to SQLite")
    ap.add_argument("--ticker", help="Override config.run.default_ticker")
    ap.add_argument("--config", default="config.toml", help="Path to config.toml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    ticker = args.ticker or cfg["run"]["default_ticker"]
    if not ticker:
        print("No ticker provided. Use --ticker or set run.default_ticker in config.toml")
        sys.exit(2)

    run_id, votes, meta = run_once(ticker, cfg)

    print_section(f"RUN {run_id}  [{meta['ticker']} @ {meta['asof']}]  close={meta['close']:.2f}")

    # Group by pillar for readability
    by_pillar = {}
    for v in votes:
        by_pillar.setdefault(v["pillar"], []).append(v)

    for pillar, items in by_pillar.items():
        print(f"\n--- {pillar.upper()} ---")
        for v in items:
            tool = v.get("tool", "?")
            sig = v.get("signal", "HOLD")
            vote = v.get("vote", 0)
            conf = v.get("confidence", 0.0)
            reason = v.get("reason", "")
            print(f"{tool:>18}: {sig:5}  vote={vote:+d}  conf={conf:.2f}  :: {reason[:120]}")

    print_section("STORAGE")
    print(f"Saved to SQLite: {cfg['run']['db_path']}")
    print("Use any SQLite browser, or try:")
    print(f'  sqlite3 "{cfg["run"]["db_path"]}" "SELECT pillar, tool, vote, signal, substr(payload,1,80) '
          f'FROM votes ORDER BY id DESC LIMIT 10;"')
    print(f'  sqlite3 "{cfg["run"]["db_path"]}" "SELECT COUNT(*) FROM votes;"')


if __name__ == "__main__":
    # line-buffered stdout so logs flush promptly
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    main()
