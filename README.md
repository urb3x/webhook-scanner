# 🌐 GitHub Hosted Site Searcher

A powerful application and CMD utility to search GitHub for repositories that host an active website (GitHub Pages or Custom Domains), inspect their details, open sites with a single click, extract Discord webhooks, and export results to CSV or JSON.

---

## 🚀 Features

- **🔍 Search Repositories with Hosted Sites:** Find GitHub Pages sites (`https://<user>.github.io/<repo>`) and repositories configured with custom domain websites (`homepage`).
- **🎣 Discord Webhook Filter (Toggle On/Off):** Filter repositories to strictly only those that contain active Discord webhook URLs in their code, configuration, or hosted sites. Includes one-click webhook copying.
- **⚡ Live Scanner Logs:** Dedicated streaming inspection logs with real-time feedback when webhooks or hosted sites are identified.
- **⚡ Instant Presets:** Quick filters for Top Starred Sites, Discord Webhooks, Developer Portfolios, Technical Documentation, Web Games, and Tools & Utilities.
- **✨ Multi-Mode Execution:**
  - **Interactive CMD Shell (`github_cmd.py`):** Dedicated terminal REPL with tab help, live searches, detail inspect, browser opening, and exports directly in Windows Command Prompt.
  - **CLI Mode (`cli.py` / `github_cmd.py <query>`):** Fast terminal output with formatted tables, JSON/CSV exports, and `--urls-only` mode for command-line scripting and piping.
  - **GUI Mode (`gui.py`):** Sleek dark-mode interface with a real-time searchable table, detailed repo previews, direct browser links, and rate-limit monitoring.
  - **Windows `.cmd` Launcher (`github_search.cmd`):** Direct double-click or cmd.exe execution with auto-Python detection.
- **💾 Export Options:** Export search results directly to `.csv` or `.json`, or copy all site URLs to clipboard with one click.
- **🔑 GitHub Token Support:** Optional personal access token (PAT) input to increase GitHub API rate limits from 10 to 30 search requests per minute.

---

## 💻 CMD Python File & Shell (`github_cmd.py`)

Run directly inside Windows Command Prompt (`cmd.exe`) or PowerShell:

```powershell
# Start the interactive CMD shell
python github_cmd.py

# Or use the Windows CMD batch file
.\github_search.cmd
```

### Interactive CMD Commands:
| Command | Description | Example |
|---|---|---|
| `search <query>` | Search repositories with hosted sites | `search portfolio -n 20` |
| `preset [name]` | Run a quick preset (stars, webhook, portfolio, docs, games, tools) | `preset webhook` *(runs `search "" --webhook -s updated -n 30`)* |
| `webhook [on\|off]` | Toggle Discord webhook filter | `webhook on` |
| `details <#>` | View detailed repository & webhook info | `details 1` |
| `open <#>` | Open hosted website in browser | `open 1` |
| `open-repo <#>` | Open GitHub repository page in browser | `open-repo 1` |
| `copy-webhook <#>` | Copy Discord webhook URL to clipboard | `copy-webhook 1` |
| `export <csv\|json>` | Export current search results | `export csv results.csv` |
| `token [pat]` | View or set GitHub Personal Access Token | `token ghp_yourToken` |
| `ratelimit` | Check remaining GitHub API requests | `ratelimit` |
| `history [clear]` | View or clear scanned repositories history | `history` or `history clear` |
| `cls` / `clear` | Clear the console screen | `clear` |
| `exit` / `quit` | Exit the shell | `exit` |

### Direct CLI Search via `github_cmd.py`:
```powershell
# Direct search with table output
python github_cmd.py "portfolio" -n 25

# Preset search
python github_cmd.py --preset games

# Search repos with Discord webhooks (Streams live colorful GREEN/RED logs)
python github_cmd.py "discord webhook" --webhook -s updated -n 25

# Stream only the colorful scanner logs (Green for webhook found, Red for skipped)
python cli.py "discord webhook" --discord-webhook -s updated --logs-only

# Run infinitely (Continuous scanner: auto-restarts after 1000 repos, auto-waits on rate limits)
python cli.py "" --discord-webhook -s updated --infinite --logs-only
```

---

## 🖥️ Standalone Executable

The compiled standalone executable is located at:
```
dist\GitHubSiteSearcher.exe
```

### Running the GUI:
Simply **double-click `GitHubSiteSearcher.exe`** in Windows Explorer or run:
```powershell
python main.py
```

---

## 🐍 Running from Python Source

```powershell
# Launch Interactive CMD Shell
python github_cmd.py

# Launch GUI
python main.py

# Run CLI search
python cli.py "portfolio" -n 20
```

### Dependencies:
- `requests`
- `rich`
- `customtkinter` (for GUI mode)
- `pillow` (for GUI mode)
- `pyinstaller` (for compiling)
