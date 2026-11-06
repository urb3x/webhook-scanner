#!/usr/bin/env python3
"""
Main entry point for GitHub Hosted Site Searcher.
Launches the GUI application by default, or the CLI/CMD interface if command line arguments are provided.
"""
import sys

def main():
    # Check for interactive CMD shell request
    cmd_flags = {"--cmd", "-c", "--shell", "--interactive", "-i"}
    if any(arg in cmd_flags for arg in sys.argv[1:]):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.AttachConsole(-1)
            except Exception:
                pass
        from github_cmd import run_cmd
        run_cmd()
        return

    # If launched with arguments like --cli, -h, --help, --query, etc., run CLI mode
    cli_flags = {
        "--cli", "-h", "--help", "-n", "--limit", "-s", "--sort",
        "-o", "--export-csv", "-j", "--export-json", "--urls-only",
        "--all-sites", "--discord-webhook", "--preset", "-p"
    }
    has_cli_args = any(arg in cli_flags for arg in sys.argv[1:]) or (len(sys.argv) > 1 and not sys.argv[1].startswith("-"))

    if has_cli_args:
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.AttachConsole(-1)
            except Exception:
                pass
        clean_args = [a for a in sys.argv[1:] if a != "--cli"]
        from cli import run_cli
        run_cli(clean_args)
    else:
        # Launch modern GUI (with automatic fallback to CMD if GUI cannot run)
        try:
            from gui import run_gui
            run_gui()
        except Exception as e:
            print(f"[*] GUI could not be initialized ({e}). Switching to CMD mode...")
            from github_cmd import run_cmd
            run_cmd()


if __name__ == "__main__":
    main()
