#!/usr/bin/env python3
"""
Interactive and Scriptable CMD Interface for GitHub Hosted Site Searcher.
Built using Python's standard `cmd` module with Rich/ANSI terminal formatting.

Usage:
  - Interactive Shell:
      python github_cmd.py
  - Direct Search (CLI mode):
      python github_cmd.py "portfolio" -n 25
      python github_cmd.py --preset games
"""

import sys
import os
import cmd
import shlex
import argparse
import webbrowser
import subprocess
import csv
import json
import time
from typing import List, Optional

# Enable UTF-8 and ANSI support in Windows CMD / PowerShell
if sys.platform == "win32":
    try:
        os.system("")  # Enables VT100 / ANSI escape sequences in Windows cmd.exe
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

from github_client import (
    GitHubSiteSearcher,
    load_saved_token,
    save_token,
    clear_scanned_history,
    load_scanned_history
)
from cli import print_table


PRESETS = {
    "1": ("stars", "stars:>1000", "Top Starred Sites"),
    "2": ("webhook", '"" --webhook -s updated -n 30', "Discord Webhooks (All Repos, Newest Updated)"),
    "3": ("portfolio", "portfolio in:name,description", "Developer Portfolios"),
    "4": ("docs", "topic:documentation", "Technical Documentation"),
    "5": ("games", "game in:name,description,topics", "Web Games"),
    "6": ("tools", "tools in:name,description", "Tools & Utilities"),
}


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard across Windows/Linux/macOS."""
    if not text:
        return False
    # Try Windows native clip.exe first
    if sys.platform == "win32":
        try:
            p = subprocess.Popen(["clip.exe"], stdin=subprocess.PIPE, shell=True)
            p.communicate(text.encode("utf-16le"))
            if p.returncode == 0:
                return True
        except Exception:
            pass

    # Try pyperclip
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        pass

    # Try tkinter fallback
    try:
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        return True
    except Exception:
        pass

    return False


class GitHubSearchCMD(cmd.Cmd):
    """
    Interactive CMD Shell for searching GitHub repositories with hosted sites.
    """
    intro = (
        "\n"
        "========================================================================\n"
        " 🌐 GitHub Hosted Site Searcher - CMD Shell\n"
        "========================================================================\n"
        " Type 'help' or '?' to list commands.\n"
        " Quick start: 'search portfolio' or 'preset' or 'webhook on'\n"
        "========================================================================\n"
    )
    prompt = "github-search> "

    def __init__(self, searcher: Optional[GitHubSiteSearcher] = None):
        super().__init__()
        token = load_saved_token()
        self.searcher = searcher or GitHubSiteSearcher(token=token)
        self.last_results: List[dict] = []
        self.require_webhook = False
        self.only_pages = True
        self.default_limit = 25
        self.default_sort = "stars"

    def emptyline(self):
        """Do nothing on empty line."""
        pass

    def default(self, line: str):
        """Intelligently interpret non-command inputs as search queries."""
        stripped = line.strip()
        if not stripped:
            return
        if stripped in ("q", "quit", "exit"):
            return self.do_exit(stripped)
        if stripped in ("cls", "clear"):
            return self.do_clear(stripped)
        
        # Treat raw input as search query
        print(f"[*] Searching for '{stripped}'...")
        self.do_search(stripped)

    # -------------------------------------------------------------------------
    # Command: search
    # -------------------------------------------------------------------------
    def do_search(self, arg: str):
        """
        Search GitHub for repositories with hosted sites.
        Usage:
          search <query> [-n LIMIT] [-s SORT] [--webhook] [--all-sites]
        Examples:
          search portfolio
          search stars:>500 -n 15
          search "three.js" -s updated
          search bot --webhook -n 20
        """
        parser = argparse.ArgumentParser(prog="search", add_help=False)
        parser.add_argument("query", nargs="*", default=[])
        parser.add_argument("-n", "--limit", type=int, default=self.default_limit)
        parser.add_argument("-s", "--sort", choices=["stars", "forks", "updated", "best_match"], default=self.default_sort)
        parser.add_argument("--webhook", action="store_true", default=self.require_webhook)
        parser.add_argument("-v", "--logs", action="store_true", default=False)
        parser.add_argument("-i", "--infinite", "--loop", action="store_true", dest="infinite", default=False)
        parser.add_argument("-w", "--workers", "--threads", type=int, default=20, dest="workers", help="Concurrent threads")
        parser.add_argument("--all-sites", action="store_true", default=not self.only_pages)

        try:
            tokens = shlex.split(arg) if arg else []
            args, unknown = parser.parse_known_args(tokens)
        except Exception as e:
            print(f"[!] Invalid arguments: {e}")
            return

        query_str = " ".join(args.query).strip()
        if not args.query and not query_str:
            query_str = "" if args.webhook else "stars:>50"

        sort_param = args.sort if args.sort != "best_match" else None
        webhook_filter = args.webhook or self.require_webhook
        only_pages = not args.all_sites
        show_logs = args.logs or webhook_filter

        display_query = query_str if query_str else "(All Repositories)"
        print(f"\n[*] Query: '{display_query}' | Limit: {args.limit} | Sort: {args.sort} | Discord Webhook Filter: {'ON' if webhook_filter else 'OFF'}")
        if show_logs:
            print("[*] Streaming real-time scanner logs (Green = Match, Red = Skip):")
        else:
            print("[*] Fetching matching repositories...")

        def on_progress(curr, total, msg):
            if sys.stderr.isatty():
                sys.stderr.write(f"\r\033[K[*] {msg}")
                sys.stderr.flush()

        def on_log(msg, tag):
            if not show_logs:
                return
            if tag == "match":
                print(f"\033[1;92m{msg}\033[0m")
            elif tag == "skip":
                print(f"\033[1;91m{msg}\033[0m")
            elif tag == "info":
                print(f"\033[1;96m{msg}\033[0m")
            else:
                print(msg)

        try:
            results = self.searcher.search_repos(
                query=query_str,
                sort=sort_param,
                max_results=args.limit,
                only_pages=only_pages,
                require_discord_webhook=webhook_filter,
                progress_callback=on_progress if not (show_logs or args.infinite) else None,
                log_callback=on_log,
                infinite=args.infinite,
                auto_wait=True,
                persist_history=True,
                workers=args.workers
            )
            if sys.stderr.isatty():
                sys.stderr.write("\r\033[K")
        except KeyboardInterrupt:
            print("\n\n\033[1;93m[*] Infinite scan stopped by user (Ctrl+C).\033[0m")
            results = self.searcher.last_results if hasattr(self.searcher, "last_results") else []
        except Exception as e:
            print(f"\n[!] Error during search: {e}")
            return

        self.last_results = results

        if not results:
            print("[-] No matching repositories with hosted websites found.\n")
            return

        print()
        print_table(results)
        print(f"\n[+] Found {len(results)} hosted site(s).")
        print("    Tips: Type 'open <#>' to open in browser, 'details <#>' to inspect, 'export csv' to save.\n")

    # -------------------------------------------------------------------------
    # Command: preset
    # -------------------------------------------------------------------------
    def do_preset(self, arg: str):
        """
        Choose or run a quick search preset.
        Usage:
          preset               -> displays preset menu
          preset <name or #>   -> immediately runs chosen preset
        Available:
          1 / stars       : Top Starred Sites (stars:>1000)
          2 / webhook     : search "" --webhook -s updated -n 30
          3 / portfolio   : Developer Portfolios
          4 / docs        : Technical Documentation
          5 / games       : Web Games
          6 / tools       : Tools & Utilities
        """
        arg_clean = arg.strip().lower()

        target_cmd = None
        target_name = None

        if arg_clean:
            # Check by number or alias
            for num, (alias, cmd_str, title) in PRESETS.items():
                if arg_clean in (num, alias):
                    target_cmd = cmd_str
                    target_name = title
                    break
            if not target_cmd:
                print(f"[!] Unknown preset '{arg}'. Type 'preset' to view available presets.")
                return
        else:
            print("\nAvailable Presets:")
            print("-" * 65)
            for num, (alias, cmd_str, title) in PRESETS.items():
                print(f" [{num}] {title:<30} -> search {cmd_str}")
            print("-" * 65)
            try:
                choice = input("Select a preset (1-6) or press Enter to cancel: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print()
                return

            if not choice:
                return

            for num, (alias, cmd_str, title) in PRESETS.items():
                if choice in (num, alias):
                    target_cmd = cmd_str
                    target_name = title
                    break

            if not target_cmd:
                print("[!] Invalid selection.")
                return

        print(f"\n[*] Running preset: {target_name}")
        print(f"github-search> search {target_cmd}")
        self.do_search(target_cmd)

    # -------------------------------------------------------------------------
    # Command: details / view
    # -------------------------------------------------------------------------
    def do_details(self, arg: str):
        """
        Show complete details for a search result item number.
        Usage:
          details <#>
        Example:
          details 1
        """
        if not self.last_results:
            print("[!] No search results in memory. Run 'search <query>' first.")
            return

        arg_clean = arg.strip()
        if not arg_clean.isdigit():
            print("[!] Please specify a valid item number, e.g.: details 1")
            return

        idx = int(arg_clean)
        if idx < 1 or idx > len(self.last_results):
            print(f"[!] Item #{idx} is out of range (1 - {len(self.last_results)}).")
            return

        r = self.last_results[idx - 1]
        print("\n" + "=" * 65)
        print(f" #{idx} : {r['full_name']}")
        print("=" * 65)
        print(f"  Description    : {r.get('description') or '(No description provided)'}")
        print(f"  Stars          : {r.get('stars', 0):,}")
        print(f"  Forks          : {r.get('forks', 0):,}")
        print(f"  Language       : {r.get('language') or 'Unknown'}")
        print(f"  Repository URL : {r.get('html_url')}")
        print(f"  Hosted Site    : {r.get('site_url') or '(None)'}")
        if r.get('pages_url'):
            print(f"  GitHub Pages   : {r.get('pages_url')}")
        if r.get('homepage_url'):
            print(f"  Custom Domain  : {r.get('homepage_url')}")

        webhooks = r.get("discord_webhooks", [])
        if webhooks:
            print(f"  Discord Webhooks ({len(webhooks)} found):")
            for w in webhooks:
                print(f"    - {w}")
        else:
            print("  Discord Webhook: None found")
        print("=" * 65)
        print(f"  Commands: 'open {idx}', 'open-repo {idx}', 'copy-webhook {idx}'\n")

    def do_view(self, arg: str):
        """Alias for details."""
        self.do_details(arg)

    # -------------------------------------------------------------------------
    # Command: open
    # -------------------------------------------------------------------------
    def do_open(self, arg: str):
        """
        Open the hosted website for result # in your default browser.
        Usage:
          open <#>
        Example:
          open 1
        """
        if not self.last_results:
            print("[!] No search results in memory. Run 'search <query>' first.")
            return

        arg_clean = arg.strip()
        if not arg_clean.isdigit():
            print("[!] Please specify a valid item number, e.g.: open 1")
            return

        idx = int(arg_clean)
        if idx < 1 or idx > len(self.last_results):
            print(f"[!] Item #{idx} is out of range (1 - {len(self.last_results)}).")
            return

        r = self.last_results[idx - 1]
        url = r.get("site_url")
        if not url:
            print(f"[-] No hosted site URL found for #{idx}.")
            return

        print(f"[*] Opening {url} in your browser...")
        webbrowser.open(url)

    # -------------------------------------------------------------------------
    # Command: open-repo / repo
    # -------------------------------------------------------------------------
    def do_open_repo(self, arg: str):
        """
        Open the GitHub repository page in your default browser.
        Usage:
          open-repo <#>
        """
        if not self.last_results:
            print("[!] No search results in memory. Run 'search <query>' first.")
            return

        arg_clean = arg.strip()
        if not arg_clean.isdigit():
            print("[!] Please specify an item number, e.g.: open-repo 1")
            return

        idx = int(arg_clean)
        if idx < 1 or idx > len(self.last_results):
            print(f"[!] Item #{idx} is out of range.")
            return

        r = self.last_results[idx - 1]
        url = r.get("html_url")
        if url:
            print(f"[*] Opening repository {url} in browser...")
            webbrowser.open(url)

    def do_repo(self, arg: str):
        """Alias for open-repo."""
        self.do_open_repo(arg)

    # -------------------------------------------------------------------------
    # Command: copy-webhook / copy
    # -------------------------------------------------------------------------
    def do_copy_webhook(self, arg: str):
        """
        Copy the Discord webhook URL from result # to your clipboard.
        Usage:
          copy-webhook <#>
        """
        if not self.last_results:
            print("[!] No search results in memory.")
            return

        arg_clean = arg.strip()
        if not arg_clean.isdigit():
            print("[!] Please specify an item number, e.g.: copy-webhook 1")
            return

        idx = int(arg_clean)
        if idx < 1 or idx > len(self.last_results):
            print(f"[!] Item #{idx} is out of range.")
            return

        r = self.last_results[idx - 1]
        webhooks = r.get("discord_webhooks", [])
        if not webhooks:
            print(f"[-] Repository #{idx} has no Discord webhooks.")
            return

        wh_url = webhooks[0]
        if copy_to_clipboard(wh_url):
            print(f"[+] Copied Discord webhook to clipboard:\n    {wh_url}")
        else:
            print(f"[+] Discord webhook URL:\n    {wh_url}")

    def do_copy(self, arg: str):
        """Alias for copy-webhook."""
        self.do_copy_webhook(arg)

    # -------------------------------------------------------------------------
    # Command: webhook
    # -------------------------------------------------------------------------
    def do_webhook(self, arg: str):
        """
        Toggle or set the Discord Webhook filter.
        Usage:
          webhook          -> toggles between ON and OFF
          webhook on       -> turns filter ON
          webhook off      -> turns filter OFF
          webhook status   -> displays current setting
        """
        clean = arg.strip().lower()
        if clean == "on":
            self.require_webhook = True
        elif clean == "off":
            self.require_webhook = False
        elif clean == "status":
            pass
        elif not clean:
            self.require_webhook = not self.require_webhook
        else:
            print("[!] Usage: webhook [on|off|status]")
            return

        state = "ON (Only repos with Discord webhooks)" if self.require_webhook else "OFF (All repos with hosted sites)"
        print(f"[*] Discord Webhook Filter is now: {state}")

    # -------------------------------------------------------------------------
    # Command: export
    # -------------------------------------------------------------------------
    def do_export(self, arg: str):
        """
        Export the latest search results to CSV or JSON.
        Usage:
          export csv [filename]
          export json [filename]
        Examples:
          export csv
          export csv my_sites.csv
          export json results.json
        """
        if not self.last_results:
            print("[!] No search results to export. Run a search first.")
            return

        tokens = shlex.split(arg) if arg else []
        fmt = tokens[0].lower() if tokens else "csv"
        filename = tokens[1] if len(tokens) > 1 else None

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        if fmt == "csv":
            filename = filename or f"github_sites_{timestamp}.csv"
            try:
                with open(filename, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        "full_name", "site_url", "stars", "forks", "language",
                        "html_url", "pages_url", "homepage_url", "discord_webhooks", "description"
                    ])
                    writer.writeheader()
                    for r in self.last_results:
                        writer.writerow({
                            "full_name": r.get("full_name", ""),
                            "site_url": r.get("site_url", ""),
                            "stars": r.get("stars", 0),
                            "forks": r.get("forks", 0),
                            "language": r.get("language", ""),
                            "html_url": r.get("html_url", ""),
                            "pages_url": r.get("pages_url", ""),
                            "homepage_url": r.get("homepage_url", ""),
                            "discord_webhooks": "; ".join(r.get("discord_webhooks", [])),
                            "description": r.get("description", "")
                        })
                print(f"[+] Successfully exported {len(self.last_results)} results to: {os.path.abspath(filename)}")
            except Exception as e:
                print(f"[!] Failed to export CSV: {e}")

        elif fmt == "json":
            filename = filename or f"github_sites_{timestamp}.json"
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(self.last_results, f, indent=2, ensure_ascii=False)
                print(f"[+] Successfully exported {len(self.last_results)} results to: {os.path.abspath(filename)}")
            except Exception as e:
                print(f"[!] Failed to export JSON: {e}")
        else:
            print("[!] Unsupported format. Use 'export csv' or 'export json'.")

    # -------------------------------------------------------------------------
    # Command: list / results
    # -------------------------------------------------------------------------
    def do_list(self, arg: str):
        """Re-print the current search results table."""
        if not self.last_results:
            print("[-] No results in memory. Run 'search <query>' to find hosted sites.")
            return
        print_table(self.last_results)
        print(f"\n[+] Total hosted sites: {len(self.last_results)}")

    def do_results(self, arg: str):
        """Alias for list."""
        self.do_list(arg)

    # -------------------------------------------------------------------------
    # Command: token
    # -------------------------------------------------------------------------
    def do_token(self, arg: str):
        """
        View or set GitHub Personal Access Token (PAT).
        Usage:
          token                -> view current token status & rate limits
          token <your_token>   -> save new token
          token clear          -> remove saved token
        """
        clean = arg.strip()
        if not clean:
            curr = load_saved_token()
            if curr:
                masked = curr[:4] + "*" * (len(curr) - 8) + curr[-4:] if len(curr) > 8 else "***"
                print(f"[*] Current GitHub Token: {masked}")
            else:
                print("[-] No GitHub token currently configured (Unauthenticated: 10 req/min).")
            self.do_ratelimit("")
            return

        if clean.lower() == "clear":
            save_token("")
            self.searcher.set_token(None)
            print("[+] Token cleared. Rate limit is now unauthenticated (10 req/min).")
            return

        save_token(clean)
        self.searcher.set_token(clean)
        print("[+] GitHub Token successfully saved!")
        self.do_ratelimit("")

    # -------------------------------------------------------------------------
    # Command: ratelimit
    # -------------------------------------------------------------------------
    def do_ratelimit(self, arg: str):
        """Check GitHub API rate limit for search requests."""
        print("[*] Checking GitHub API rate limit...")
        info = self.searcher.check_rate_limit()
        rem = info.get("remaining", 0)
        limit = info.get("limit", 10)
        reset_ts = info.get("reset", 0)
        reset_in = max(0, int(reset_ts - time.time())) if reset_ts else 0

        print(f"    - Search Rate Limit: {rem} / {limit} requests remaining")
        if reset_in > 0:
            print(f"    - Resets in        : {reset_in} seconds ({reset_in // 60}m {reset_in % 60}s)")

    # -------------------------------------------------------------------------
    # Command: history
    # -------------------------------------------------------------------------
    def do_history(self, arg: str):
        """
        View or manage scanned repositories history.
        Usage:
          history        -> displays count of repositories saved in history
          history clear  -> reset and clear scanned history
        """
        clean = arg.strip().lower()
        if clean == "clear":
            clear_scanned_history()
            print("[+] Scanned repository history cleared.")
            return

        hist = load_scanned_history()
        print(f"[*] Total previously scanned repositories stored in history: {len(hist):,}")
        print("    These repositories are automatically skipped across sessions.")
        print("    Type 'history clear' to reset history.")

    # -------------------------------------------------------------------------
    # Command: clear / cls
    # -------------------------------------------------------------------------
    def do_clear(self, arg: str):
        """Clear the console screen."""
        os.system("cls" if os.name == "nt" else "clear")

    def do_cls(self, arg: str):
        """Alias for clear."""
        self.do_clear(arg)

    # -------------------------------------------------------------------------
    # Command: exit / quit
    # -------------------------------------------------------------------------
    def do_exit(self, arg: str):
        """Exit the CMD shell."""
        print("Goodbye!")
        return True

    def do_quit(self, arg: str):
        """Exit the CMD shell."""
        return self.do_exit(arg)


def run_cmd():
    """Start the interactive GitHub Hosted Site Searcher CMD shell."""
    try:
        app = GitHubSearchCMD()
        app.cmdloop()
    except (KeyboardInterrupt, EOFError):
        print("\n\nGoodbye!")


def main():
    # If arguments are passed on command line, check if user requested interactive or direct search
    if len(sys.argv) > 1:
        first = sys.argv[1].lower()
        if first in ("-i", "--interactive", "interactive", "shell"):
            run_cmd()
            return
        
        # Check if user invoked preset via CLI flag
        if first in ("--preset", "-p") and len(sys.argv) > 2:
            app = GitHubSearchCMD()
            app.do_preset(sys.argv[2])
            return

        # Direct search execution via cli.py
        from cli import run_cli
        run_cli(sys.argv[1:])
    else:
        # No arguments: launch interactive CMD shell!
        run_cmd()


if __name__ == "__main__":
    main()
