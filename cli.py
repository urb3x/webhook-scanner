#!/usr/bin/env python3
"""
CLI Interface for GitHub Hosted Site Searcher.
"""
import sys
import argparse
import csv
import json
import webbrowser
from typing import List
from github_client import (
    GitHubSiteSearcher,
    load_saved_token,
    clear_scanned_history,
    load_scanned_history
)

import os

# Safely enable UTF-8 and ANSI VT100 color support on Windows console
if sys.platform == "win32":
    try:
        os.system("")  # Triggers conhost VT100 processing
        import ctypes
        kernel32 = ctypes.windll.kernel32
        for h_id in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(h_id)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        if sys.stdout.encoding != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def print_table(results: List[dict]):
    has_webhooks = any(r.get("discord_webhooks") for r in results)
    try:
        from rich.console import Console
        from rich.table import Table
        console = Console(force_terminal=True, legacy_windows=False)
        table = Table(title="GitHub Repositories with Hosted Sites", show_lines=False)
        table.add_column("#", style="dim", width=4)
        table.add_column("Repository", style="cyan", no_wrap=True)
        table.add_column("Stars", style="yellow", justify="right")
        table.add_column("Language", style="magenta")
        table.add_column("Hosted Site URL", style="green bold")
        if has_webhooks:
            table.add_column("Discord Webhook", style="bright_blue")

        for idx, r in enumerate(results, start=1):
            row_items = [
                str(idx),
                r["full_name"],
                f"{r['stars']:,}",
                r["language"],
                r["site_url"] or "(None)"
            ]
            if has_webhooks:
                wh_list = r.get("discord_webhooks", [])
                wh_str = wh_list[0] if wh_list else ("Yes" if r.get("has_discord_webhook") else "—")
                row_items.append(wh_str)
            table.add_row(*row_items)
        console.print(table)
    except Exception:
        # Fallback to standard formatted output
        print("=" * 105 if has_webhooks else "=" * 90)
        hdr = f"{'#':<4} | {'Repository':<30} | {'Stars':<8} | {'Hosted Site URL':<35}"
        if has_webhooks:
            hdr += " | Discord Webhook"
        print(hdr)
        print("-" * 105 if has_webhooks else "-" * 90)
        for idx, r in enumerate(results, start=1):
            site = r["site_url"] or "N/A"
            line = f"{idx:<4} | {r['full_name']:<30} | {r['stars']:<8} | {site:<35}"
            if has_webhooks:
                wh_list = r.get("discord_webhooks", [])
                wh_str = wh_list[0] if wh_list else "N/A"
                line += f" | {wh_str}"
            print(line)
        print("=" * 105 if has_webhooks else "=" * 90)



def run_cli(args_list=None):
    parser = argparse.ArgumentParser(
        description="Search GitHub repositories that have hosted websites (GitHub Pages or Custom Domains)."
    )
    parser.add_argument("query", nargs="?", default=None, help="Search query (e.g., 'portfolio', 'documentation', 'react', 'stars:>500')")
    parser.add_argument("-p", "--preset", choices=["stars", "webhook", "portfolio", "docs", "games", "tools"], help="Use a built-in search preset")
    parser.add_argument("-n", "--limit", type=int, default=30, help="Maximum number of repositories to return (default: 30)")
    parser.add_argument("-s", "--sort", choices=["stars", "forks", "updated", "best_match"], default="stars", help="Sort order (default: stars)")
    parser.add_argument("--all-sites", action="store_true", help="Include repos with custom homepages even if GitHub Pages is not explicitly enabled")
    parser.add_argument("--discord-webhook", action="store_true", help="Filter repositories to only those containing Discord webhooks (turn on/off)")
    parser.add_argument("-t", "--token", type=str, default=None, help="GitHub Personal Access Token for higher rate limits (30 req/min)")
    parser.add_argument("-o", "--export-csv", type=str, help="Export results to a CSV file")
    parser.add_argument("-j", "--export-json", type=str, help="Export results to a JSON file")
    parser.add_argument("-v", "--logs", action="store_true", help="Show real-time colorful live scanner logs (Green matches, Red skips)")
    parser.add_argument("--logs-only", action="store_true", help="Only stream colorful live logs without displaying the final summary table")
    parser.add_argument("-i", "--infinite", "--loop", action="store_true", dest="infinite", help="Run infinitely (restarts cycle after 1000 repos, auto-waits on rate limits)")
    parser.add_argument("--no-history", action="store_true", help="Do not save or load scanned repositories history")
    parser.add_argument("--clear-history", action="store_true", help="Clear previously scanned repositories history before running")
    parser.add_argument("-w", "--workers", "--threads", type=int, default=20, dest="workers", help="Number of concurrent multi-threaded workers (default: 20)")
    parser.add_argument("--urls-only", action="store_true", help="Output only the hosted site URLs (one per line, great for piping)")
    parser.add_argument("--open-first", action="store_true", help="Automatically open the first result in your default browser")

    args = parser.parse_args(args_list)

    if args.clear_history:
        clear_scanned_history()
        print("[+] Scanned repository history cleared.")

    preset_queries = {
        "stars": "stars:>1000",
        "webhook": "",
        "portfolio": "portfolio in:name,description",
        "docs": "topic:documentation",
        "games": "game in:name,description,topics",
        "tools": "tools in:name,description"
    }

    query = args.query
    if args.preset:
        query = preset_queries[args.preset]
        if args.preset == "webhook":
            query = ""
            args.discord_webhook = True
            args.sort = "updated"
            args.limit = 30
    elif not query:
        query = "stars:>100"

    token = args.token or load_saved_token()
    searcher = GitHubSiteSearcher(token=token)

    sort_param = args.sort if args.sort != "best_match" else None

    if not args.urls_only:
        disp_q = query if query else "(All Repositories)"
        print(f"[*] Searching GitHub for: '{disp_q}' (Max results: {args.limit}, Sort: {args.sort})...")

    try:
        def on_progress(current, total, msg):
            if not args.urls_only and sys.stderr.isatty():
                sys.stderr.write(f"\r\033[K[*] {msg}")
                sys.stderr.flush()

        def on_log(msg, tag):
            if not args.logs and not args.logs_only and not (args.discord_webhook and not args.urls_only):
                return
            if tag == "match":
                print(f"\033[1;92m{msg}\033[0m")
            elif tag == "skip":
                print(f"\033[1;91m{msg}\033[0m")
            elif tag == "info":
                print(f"\033[1;96m{msg}\033[0m")
            else:
                print(msg)

        results = searcher.search_repos(
            query=query,
            sort=sort_param,
            max_results=args.limit,
            only_pages=not args.all_sites,
            require_discord_webhook=args.discord_webhook,
            progress_callback=on_progress if not (args.logs or args.discord_webhook or args.logs_only or args.infinite) else None,
            log_callback=on_log,
            infinite=args.infinite,
            auto_wait=True,
            persist_history=not args.no_history,
            workers=args.workers
        )
        if not args.urls_only and sys.stderr.isatty():
            sys.stderr.write("\r\033[K")

    except KeyboardInterrupt:
        print("\n\n\033[1;93m[*] Infinite scan stopped by user (Ctrl+C).\033[0m")
    except Exception as e:
        print(f"\n[!] Error during search: {e}", file=sys.stderr)
        sys.exit(1)

    if args.urls_only:
        for r in results:
            if r["site_url"]:
                print(r["site_url"])
        return

    if not results:
        print("\n[-] No repositories with hosted sites found matching your query.")
        return

    if not args.logs_only:
        print()
        print_table(results)
    print(f"\n\033[1;92m[+] Total matching repositories found: {len(results)}\033[0m")

    if args.export_csv:
        try:
            with open(args.export_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "full_name", "site_url", "stars", "forks", "language", "html_url", "pages_url", "homepage_url", "discord_webhooks", "description"
                ])
                writer.writeheader()
                for r in results:
                    writer.writerow({
                        "full_name": r["full_name"],
                        "site_url": r["site_url"],
                        "stars": r["stars"],
                        "forks": r["forks"],
                        "language": r["language"],
                        "html_url": r["html_url"],
                        "pages_url": r["pages_url"],
                        "homepage_url": r["homepage_url"],
                        "discord_webhooks": "; ".join(r.get("discord_webhooks", [])),
                        "description": r["description"]
                    })
            print(f"[+] Exported CSV to: {args.export_csv}")
        except Exception as e:
            print(f"[!] Failed to save CSV: {e}", file=sys.stderr)

    if args.export_json:
        try:
            with open(args.export_json, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            print(f"[+] Exported JSON to: {args.export_json}")
        except Exception as e:
            print(f"[!] Failed to save JSON: {e}", file=sys.stderr)

    if args.open_first and results and results[0]["site_url"]:
        print(f"[*] Opening {results[0]['site_url']} in browser...")
        webbrowser.open(results[0]["site_url"])

if __name__ == "__main__":
    run_cli()

