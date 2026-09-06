#!/usr/bin/env python3
"""
refresh_politician_list.py — Weekly job to re-backtest all congressional traders
and auto-update ELITE_CONGRESSIONAL_TRADERS in insider_alerts.py.

Usage:
    python refresh_politician_list.py              # Full backtest + patch files
    python refresh_politician_list.py --dry-run    # Show new list, don't write
    python refresh_politician_list.py --min-trades 8  # Stricter minimum

Schedule: Run weekly (Sunday night) via Windows Task Scheduler:
    Action: python "C:\...\refresh_politician_list.py"

Criteria for "elite" status (configurable via args):
    - avg 30d return > +3%
    - Win rate (30d) > 55%
    - 10+ qualifying trades in DB
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

INSIDER_ALERTS_FILE = SCRIPT_DIR / "insider_alerts.py"
BACKTEST_FILE = SCRIPT_DIR / "backtest_congressional.py"

# Elite thresholds
MIN_AVG30 = 3.0    # minimum 30d average return %
MIN_WR30 = 55.0    # minimum 30d win rate %
MIN_TRADES = 10    # minimum number of qualifying trades


def run_backtest_and_get_stats(max_signals: int, min_trades: int) -> list:
    """Run the full backtest and return politician_stats sorted by avg30d."""
    try:
        from backtest_congressional import run_backtest
    except ImportError as e:
        print(f"ERROR: Could not import backtest_congressional.py: {e}")
        sys.exit(1)

    print("[refresh] Running full-universe congressional backtest...")
    print(f"[refresh] This downloads price data for all traded tickers — may take 5-15 min.\n")
    stats = run_backtest(elite_only=False, max_signals=max_signals, min_trades=min_trades)
    return stats or []


def filter_elite(politician_stats: list, min_avg30: float, min_wr30: float,
                 min_trades: int) -> list:
    """Filter politicians to those meeting elite criteria."""
    elite = [
        ps for ps in politician_stats
        if ps['avg30'] >= min_avg30
        and ps['wr30'] >= min_wr30
        and ps['n'] >= min_trades
    ]
    # Sort by avg30d descending
    elite.sort(key=lambda x: x['avg30'], reverse=True)
    return elite


def build_elite_list_code(elite: list) -> str:
    """Generate the Python list literal for ELITE_CONGRESSIONAL_TRADERS."""
    lines = []
    for ps in elite:
        comment = (f"# {ps['n']} trades, {ps['wr30']:.0f}% WR, "
                   f"{ps['avg30']:+.1f}% avg30d")
        lines.append(f'    "{ps["name"]}",         {comment}')
    return "\n".join(lines)


def patch_file(filepath: Path, new_list_code: str, dry_run: bool,
               list_name: str = "ELITE_CONGRESSIONAL_TRADERS") -> bool:
    """Replace the ELITE list in a Python file using regex."""
    content = filepath.read_text(encoding="utf-8")

    # Match the full list assignment (single or multi-line)
    pattern = re.compile(
        rf'{re.escape(list_name)}\s*=\s*\[.*?\]',
        re.DOTALL
    )

    header = (
        f'{list_name} = [\n'
        f'{new_list_code}\n'
        f']'
    )

    if not pattern.search(content):
        print(f"  WARNING: Could not find {list_name} in {filepath.name}")
        return False

    new_content = pattern.sub(header, content)

    if dry_run:
        print(f"\n[dry-run] Would patch {filepath.name}:\n{header}\n")
        return True

    filepath.write_text(new_content, encoding="utf-8")
    print(f"  Patched {list_name} in {filepath.name}")
    return True


def save_report(elite: list, all_stats: list, log_path: Path,
                min_avg30: float, min_wr30: float, min_trades_thresh: int):
    """Save a human-readable refresh report to logs/."""
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "=" * 70,
        f"POLITICIAN LIST REFRESH REPORT — {date_str}",
        "=" * 70,
        f"\nCriteria: avg30 ≥ +{min_avg30}%, WR ≥ {min_wr30}%, n ≥ {min_trades_thresh} trades",
        f"Politicians in DB with enough trades: {len(all_stats)}",
        f"Qualified as elite: {len(elite)}",
        "",
        "ELITE LIST (sorted by avg30d):",
        f"  {'Politician':<35s} {'Trades':>6s} {'WR':>6s} {'Avg30':>7s} {'Med30':>7s} {'Avg90':>7s}",
        f"  {'─'*35} {'─'*6} {'─'*6} {'─'*7} {'─'*7} {'─'*7}",
    ]
    for ps in elite:
        lines.append(
            f"  {ps['name']:<35s} {ps['n']:>6d} {ps['wr30']:>5.1f}% "
            f"{ps['avg30']:>+6.1f}% {ps['med30']:>+6.1f}% {ps['avg90']:>+6.1f}%"
        )

    dropped = [ps for ps in all_stats
               if not any(e['name'] == ps['name'] for e in elite)]
    if dropped:
        lines += [
            "",
            "DROPPED FROM PREVIOUS CRITERIA (if any — not distinguished here):",
        ]
        for ps in sorted(dropped, key=lambda x: x['avg30'], reverse=True)[:20]:
            lines.append(
                f"  {ps['name']:<35s} {ps['n']:>6d} {ps['wr30']:>5.1f}% {ps['avg30']:>+6.1f}%"
            )

    lines += ["", "=" * 70]
    report = "\n".join(lines)
    log_path.write_text(report, encoding="utf-8")
    print(f"\n[refresh] Report saved to {log_path}")
    print("\n" + report)


def main():
    parser = argparse.ArgumentParser(
        description="Weekly refresh of ELITE_CONGRESSIONAL_TRADERS from live backtest"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change, don't write files")
    parser.add_argument("--max", type=int, default=5000,
                        help="Max signals in backtest (default 5000)")
    parser.add_argument("--min-trades", type=int, default=MIN_TRADES,
                        help=f"Min trades to qualify (default {MIN_TRADES})")
    parser.add_argument("--min-avg30", type=float, default=MIN_AVG30,
                        help=f"Min 30d avg return %% (default {MIN_AVG30})")
    parser.add_argument("--min-wr30", type=float, default=MIN_WR30,
                        help=f"Min 30d win rate %% (default {MIN_WR30})")
    args = parser.parse_args()

    print("=" * 70)
    print("WEEKLY POLITICIAN ELITE LIST REFRESH")
    print("=" * 70)
    print(f"Thresholds: avg30 ≥ +{args.min_avg30}%, WR ≥ {args.min_wr30}%, "
          f"n ≥ {args.min_trades} trades")
    if args.dry_run:
        print("MODE: DRY RUN — no files will be written")
    print()

    # 1. Run backtest and get full stats
    all_stats = run_backtest_and_get_stats(
        max_signals=args.max,
        min_trades=args.min_trades
    )

    if not all_stats:
        print("ERROR: Backtest returned no stats. Nothing to update.")
        sys.exit(1)

    # 2. Filter to elite
    elite = filter_elite(
        all_stats,
        min_avg30=args.min_avg30,
        min_wr30=args.min_wr30,
        min_trades=args.min_trades
    )

    print(f"\n[refresh] Found {len(elite)} elite politicians "
          f"(from {len(all_stats)} with enough trades)")

    if not elite:
        print("WARNING: No politicians met the criteria. Keeping current list.")
        sys.exit(0)

    # 3. Build new list code
    new_code = build_elite_list_code(elite)

    # 4. Patch files
    success = True
    for filepath, list_name in [
        (INSIDER_ALERTS_FILE, "ELITE_CONGRESSIONAL_TRADERS"),
        (BACKTEST_FILE, "ELITE_POLITICIANS"),
    ]:
        if filepath.exists():
            ok = patch_file(filepath, new_code, dry_run=args.dry_run,
                            list_name=list_name)
            success = success and ok
        else:
            print(f"  SKIP: {filepath.name} not found")

    # 5. Save report
    log_filename = f"politician_refresh_{datetime.now().strftime('%Y-%m-%d')}.txt"
    log_path = LOG_DIR / log_filename
    save_report(elite, all_stats, log_path,
                args.min_avg30, args.min_wr30, args.min_trades)

    if not args.dry_run and success:
        print("\n[refresh] ✓ Elite list updated successfully.")
        print("[refresh] Commit suggestion:")
        print(f"  git add insider_alerts.py backtest_congressional.py")
        print(f"  git commit -m 'auto: refresh elite politicians {datetime.now().strftime(\"%Y-%m-%d\")}'")
    elif args.dry_run:
        print("\n[refresh] Dry run complete — no files modified.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
