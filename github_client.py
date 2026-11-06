"""
GitHub API client for searching repositories with hosted sites.
"""
import os
import json
import time
import re
import threading
import concurrent.futures
from typing import Dict, List, Optional, Tuple, Callable
import requests

GITHUB_API_BASE = "https://api.github.com"
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".github_pages_search_config.json")
HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".github_scanned_repos.txt")

DISCORD_WEBHOOK_PATTERN = re.compile(
    r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/[A-Za-z0-9_\-]+/[A-Za-z0-9_\-]+[^\s\"'`;<>()\[\]]*",
    re.IGNORECASE
)

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tiff",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv",
    ".mp3", ".wav", ".ogg", ".flac", ".m4a",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".iso", ".dat",
    ".pyc", ".class", ".o", ".a"
}


def extract_discord_webhooks(text: str) -> List[str]:
    """Extracts unique clean Discord webhook URLs from text."""
    if not text or "discord" not in text.lower():
        return []
    matches = DISCORD_WEBHOOK_PATTERN.findall(text)
    cleaned = []
    for m in matches:
        url = m.rstrip("\"'`;),>.]")
        if url and url not in cleaned:
            cleaned.append(url)
    return cleaned


def load_saved_token() -> str:
    """Load saved GitHub token from user profile config."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("token", "")
    except Exception:
        pass
    return ""


def save_token(token: str) -> None:
    """Save GitHub token to user profile config."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"token": token.strip()}, f)
    except Exception:
        pass


def load_scanned_history() -> set:
    """Load previously scanned repository names from user config disk file."""
    scanned = set()
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    name = line.strip()
                    if name:
                        scanned.add(name)
    except Exception:
        pass
    return scanned


def append_scanned_history(repo_full_name: str) -> None:
    """Append a scanned repository to history file on disk."""
    if not repo_full_name:
        return
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(repo_full_name.strip() + "\n")
    except Exception:
        pass


def clear_scanned_history() -> None:
    """Clear scanned repositories history file."""
    try:
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
    except Exception:
        pass


class GitHubSiteSearcher:
    def __init__(self, token: Optional[str] = None):
        self.token = token.strip() if token and token.strip() else None
        self.last_rate_limit = {"limit": 10, "remaining": 10, "reset": 0}

    def set_token(self, token: Optional[str]):
        self.token = token.strip() if token and token.strip() else None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Hosted-Site-Searcher/1.0"
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def update_rate_limit_from_headers(self, response_headers) -> None:
        try:
            if "X-RateLimit-Limit" in response_headers:
                self.last_rate_limit["limit"] = int(response_headers.get("X-RateLimit-Limit", 10))
                self.last_rate_limit["remaining"] = int(response_headers.get("X-RateLimit-Remaining", 10))
                self.last_rate_limit["reset"] = int(response_headers.get("X-RateLimit-Reset", 0))
        except Exception:
            pass

    def check_rate_limit(self) -> Dict[str, int]:
        try:
            resp = requests.get(f"{GITHUB_API_BASE}/rate_limit", headers=self._get_headers(), timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("resources", {}).get("search", {})
                self.last_rate_limit["limit"] = data.get("limit", 10)
                self.last_rate_limit["remaining"] = data.get("remaining", 10)
                self.last_rate_limit["reset"] = data.get("reset", 0)
        except Exception:
            pass
        return self.last_rate_limit

    @staticmethod
    def resolve_site_urls(repo: dict) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Determines the hosted website URLs for a repository.
        Returns: (primary_url, pages_url, homepage_url)
        """
        owner = repo.get("owner", {}).get("login", "")
        name = repo.get("name", "")
        has_pages = bool(repo.get("has_pages", False))
        raw_homepage = (repo.get("homepage") or "").strip()

        pages_url = None
        if has_pages and owner and name:
            if name.lower() == f"{owner.lower()}.github.io":
                pages_url = f"https://{owner}.github.io/"
            else:
                pages_url = f"https://{owner}.github.io/{name}/"

        homepage_url = None
        if raw_homepage:
            if raw_homepage.startswith("http://") or raw_homepage.startswith("https://"):
                homepage_url = raw_homepage
            elif "." in raw_homepage:
                homepage_url = f"https://{raw_homepage}"

        # Primary URL preference: custom homepage if available, else pages URL
        primary_url = homepage_url if homepage_url else pages_url
        return primary_url, pages_url, homepage_url

    def check_repo_for_discord_webhook(self, repo: dict, site_url: Optional[str] = None) -> List[str]:
        """
        Inspects repository metadata, live site, and ALL repository files via Git trees & raw files
        to determine if it contains Discord webhook URLs.
        Returns a list of unique webhook URLs found.
        """
        full_name = repo.get("full_name", "")
        if not full_name:
            return []

        found_webhooks: List[str] = []

        # 1. Check repository description & homepage metadata (instant, 0ms)
        meta_text = f"{repo.get('description') or ''} {repo.get('homepage') or ''}"
        found_webhooks.extend(extract_discord_webhooks(meta_text))
        if found_webhooks:
            return list(dict.fromkeys(found_webhooks))

        # 2. Check live site HTML and any script tags if site_url is available
        if site_url:
            try:
                resp = requests.get(site_url, timeout=3.5, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                if resp.status_code == 200:
                    found_webhooks.extend(extract_discord_webhooks(resp.text))
                    if found_webhooks:
                        return list(dict.fromkeys(found_webhooks))
                    # Also look for script src tags in HTML (e.g. <script src="logger.js">)
                    script_srcs = re.findall(r'<script[^>]+src=[\'"]([^\'"]+)[\'"]', resp.text, re.IGNORECASE)
                    for s_src in script_srcs[:5]:
                        if not s_src.startswith("http://") and not s_src.startswith("https://") and not s_src.startswith("//"):
                            s_url = site_url.rstrip("/") + "/" + s_src.lstrip("/")
                            try:
                                s_resp = requests.get(s_url, timeout=2.5, headers={"User-Agent": "Mozilla/5.0"})
                                if s_resp.status_code == 200 and "discord" in s_resp.text.lower():
                                    found_webhooks.extend(extract_discord_webhooks(s_resp.text))
                                    if found_webhooks:
                                        return list(dict.fromkeys(found_webhooks))
                            except Exception:
                                pass
            except Exception:
                pass

        default_branch = repo.get("default_branch") or "main"
        branches_to_try = list(dict.fromkeys([default_branch, "main", "master", "gh-pages"]))

        # 3. Retrieve ALL files from the repository via GitHub Git Trees API
        all_text_files: List[str] = []
        for branch in branches_to_try:
            try:
                tree_resp = requests.get(
                    f"{GITHUB_API_BASE}/repos/{full_name}/git/trees/{branch}?recursive=1",
                    headers=self._get_headers(),
                    timeout=5
                )
                self.update_rate_limit_from_headers(tree_resp.headers)
                if tree_resp.status_code == 200:
                    tree_data = tree_resp.json().get("tree", [])
                    for item in tree_data:
                        if item.get("type") == "blob":
                            path = item.get("path", "")
                            ext = os.path.splitext(path)[1].lower()
                            if ext not in BINARY_EXTENSIONS:
                                all_text_files.append(path)
                    if all_text_files:
                        break
            except Exception:
                pass

        # Fallback candidate files if git/trees returned empty or failed
        if not all_text_files:
            all_text_files = [
                "worker.js", "logger.js", "index.html", "script.js", "main.js", "app.js",
                "contact.js", "webhook.js", "send.js", "api.js", "bot.js", "server.py",
                "config.js", "config.json", "settings.json", ".env.example", ".env",
                "main.py", "webhook.py", "bot.py", "README.md", "contact.html", "form.html"
            ]

        # Prioritize files most likely to contain scripts, webhooks, or configs
        def _file_priority(path: str) -> int:
            lowered = path.lower()
            if any(k in lowered for k in ("webhook", "discord", "worker", "logger", "api", "send", "contact", "bot", "config", "env")):
                return 0
            if lowered.endswith((".js", ".mjs", ".ts", ".html", ".htm", ".json", ".py", ".php", ".sh")):
                return 1
            return 2

        sorted_files = sorted(list(dict.fromkeys(all_text_files)), key=_file_priority)

        # 4. Fetch raw content of all files in parallel (up to 120 files per repo, prioritized)
        def _fetch_file(fpath: str) -> List[str]:
            for b in branches_to_try:
                raw_url = f"https://raw.githubusercontent.com/{full_name}/{b}/{fpath}"
                try:
                    r = requests.get(raw_url, timeout=3.0)
                    if r.status_code == 200:
                        if "discord" in r.text.lower():
                            matches = extract_discord_webhooks(r.text)
                            if matches:
                                return matches
                except Exception:
                    pass
            return []

        # Check in batches of 12 with ThreadPoolExecutor so we stop as soon as a webhook is found
        batch_size = 12
        for i in range(0, min(len(sorted_files), 120), batch_size):
            batch = sorted_files[i:i + batch_size]
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(batch))) as executor:
                    for res in executor.map(_fetch_file, batch):
                        if res:
                            found_webhooks.extend(res)
                if found_webhooks:
                    return list(dict.fromkeys(found_webhooks))
            except Exception:
                pass

        # 5. Fallback to GitHub Code Search API if token is configured
        if self.token:
            try:
                code_resp = requests.get(
                    f"{GITHUB_API_BASE}/search/code",
                    headers=self._get_headers(),
                    params={"q": f"discord.com/api/webhooks repo:{full_name}"},
                    timeout=5
                )
                if code_resp.status_code == 200:
                    code_data = code_resp.json()
                    items = code_data.get("items", [])
                    if items:
                        for itm in items[:3]:
                            path = itm.get("path")
                            branch = default_branch
                            try:
                                r_raw = requests.get(
                                    f"https://raw.githubusercontent.com/{full_name}/{branch}/{path}",
                                    timeout=3
                                )
                                if r_raw.status_code == 200:
                                    w = extract_discord_webhooks(r_raw.text)
                                    if w:
                                        found_webhooks.extend(w)
                            except Exception:
                                pass
                        if found_webhooks:
                            return list(dict.fromkeys(found_webhooks))
                        return [items[0].get("html_url")]
            except Exception:
                pass

        return list(dict.fromkeys(found_webhooks))

    def search_repos(
        self,
        query: str,
        sort: str = "stars",
        order: str = "desc",
        max_results: int = 50,
        only_pages: bool = True,
        include_homepage_only: bool = True,
        require_discord_webhook: bool = False,
        stop_check: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
        infinite: bool = False,
        auto_wait: bool = True,
        persist_history: bool = True,
        workers: int = 20
    ) -> List[dict]:
        """
        Searches GitHub repositories and filters those with hosted sites.
        If require_discord_webhook is True, only repos containing Discord webhooks are returned.
        log_callback(message, tag) receives live scanner lines with tag 'match' (green), 'skip' (red), or 'info'.
        If infinite is True, runs continuously across batches, resetting after 1,000 results and auto-waiting on rate limits.
        If persist_history is True, remembers scanned repositories across sessions to prevent duplicates.
        workers: number of concurrent threads scanning repositories simultaneously for full speed.
        """
        clean_query = query.strip()
        if clean_query in ('""', "''"):
            clean_query = ""
        if not clean_query:
            clean_query = "stars:>=0"

        results: List[dict] = []
        seen_repos: set = load_scanned_history() if persist_history else set()
        seen_lock = threading.Lock()
        results_lock = threading.Lock()

        if log_callback and seen_repos:
            log_callback(f"[*] Loaded {len(seen_repos):,} previously scanned repositories from history (skipping duplicate scans).", "info")
        page = 1
        per_page = 100 if infinite else min(100, max(10, max_results))

        def _process_repo(item: dict) -> Optional[dict]:
            if stop_check and stop_check():
                return None

            full_name = item.get("full_name", "")
            if not full_name:
                return None

            with seen_lock:
                if full_name in seen_repos:
                    return None
                seen_repos.add(full_name)
                if persist_history:
                    append_scanned_history(full_name)
                if len(seen_repos) > 100000:
                    seen_repos.difference_update(list(seen_repos)[:50000])

            has_pages = bool(item.get("has_pages", False))
            primary_url, pages_url, homepage_url = self.resolve_site_urls(item)

            if only_pages:
                if not has_pages:
                    if log_callback:
                        log_callback(f"[-] [NO PAGES] {full_name} (has_pages=false)", "skip")
                    return None
            else:
                if not has_pages and (not include_homepage_only or not homepage_url):
                    if log_callback:
                        log_callback(f"[-] [NO HOSTED SITE] {full_name} (no pages/homepage)", "skip")
                    return None

            webhooks: List[str] = []
            has_webhook = False
            if require_discord_webhook:
                if progress_callback:
                    progress_callback(len(results), max_results, f"Checking {full_name} for Discord webhooks...")
                webhooks = self.check_repo_for_discord_webhook(item, primary_url)
                if not webhooks:
                    if log_callback:
                        log_callback(f"[-] [NO WEBHOOK] {full_name} — No Discord webhook found", "skip")
                    return None
                has_webhook = True
                if log_callback:
                    wh_sample = webhooks[0] if webhooks else "Detected"
                    log_callback(f"[+] [FOUND WEBHOOK] {full_name} -> {wh_sample}", "match")
            else:
                if log_callback:
                    log_callback(f"[+] [FOUND HOSTED SITE] {full_name} -> {primary_url}", "match")

            return {
                "id": item.get("id"),
                "full_name": item.get("full_name"),
                "owner": item.get("owner", {}).get("login"),
                "name": item.get("name"),
                "html_url": item.get("html_url"),
                "site_url": primary_url,
                "pages_url": pages_url,
                "homepage_url": homepage_url,
                "has_pages": has_pages,
                "has_discord_webhook": has_webhook,
                "discord_webhooks": webhooks,
                "description": item.get("description") or "No description provided.",
                "stars": item.get("stargazers_count", 0),
                "forks": item.get("forks_count", 0),
                "language": item.get("language") or "Other",
                "updated_at": (item.get("updated_at") or "")[:10],
                "topics": item.get("topics", [])
            }

        while infinite or len(results) < max_results:
            if stop_check and stop_check():
                break

            # GitHub Search API hard cap: only the first 1,000 results are accessible per query
            if (page - 1) * per_page >= 1000:
                if infinite:
                    if log_callback:
                        log_callback("[*] Completed batch of 1,000 repositories. Waiting 10s before restarting scan cycle for newly updated repos...", "info")
                    for _ in range(10):
                        if stop_check and stop_check():
                            break
                        time.sleep(1)
                    page = 1
                    continue
                else:
                    if log_callback:
                        log_callback("[-] Reached GitHub Search API limit (first 1,000 results ceiling).", "info")
                    break

            if progress_callback:
                progress_callback(len(results), max_results, f"Fetching page {page} from GitHub...")

            params = {
                "q": clean_query,
                "sort": sort,
                "order": order,
                "page": page,
                "per_page": per_page
            }

            try:
                resp = requests.get(
                    f"{GITHUB_API_BASE}/search/repositories",
                    headers=self._get_headers(),
                    params=params,
                    timeout=15
                )
                self.update_rate_limit_from_headers(resp.headers)

                if resp.status_code in (403, 429):
                    reset_time = int(resp.headers.get("X-RateLimit-Reset", 0)) or self.last_rate_limit.get("reset", 0)
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        wait_sec = int(retry_after) + 2
                    else:
                        wait_sec = max(5, int(reset_time - time.time()) + 2) if reset_time else 60

                    msg = f"GitHub API token quota exhausted. Waiting {wait_sec}s for token reset... (Auto-resumes once tokens are available)"
                    if log_callback:
                        log_callback(f"[*] {msg}", "info")
                    for remaining in range(wait_sec, 0, -1):
                        if stop_check and stop_check():
                            break
                        if remaining % 15 == 0 or remaining <= 5:
                            if log_callback:
                                log_callback(f"[*] Tokens reset in {remaining}s...", "info")
                        time.sleep(1)
                    if log_callback:
                        log_callback("[+] Token quota refreshed! Resuming scan at full speed...", "match")
                    continue

                if resp.status_code == 422:
                    err_json = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    err_msg = err_json.get("message", resp.text)
                    if "1000" in err_msg:
                        if infinite:
                            if log_callback:
                                log_callback("[*] Reached GitHub 1,000-result ceiling. Waiting 10s before refreshing...", "info")
                            for _ in range(10):
                                if stop_check and stop_check():
                                    break
                                time.sleep(1)
                            page = 1
                            continue
                        else:
                            if log_callback:
                                log_callback("[-] Reached GitHub Search API 1,000-result limit.", "info")
                            break
                    raise RuntimeError(f"GitHub API (422): {err_msg}")

                if resp.status_code != 200:
                    err_json = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    err_msg = err_json.get("message", resp.text)
                    raise RuntimeError(f"GitHub API ({resp.status_code}): {err_msg}")

                data = resp.json()
                items = data.get("items", [])
                if not items:
                    if infinite:
                        if log_callback:
                            log_callback("[*] No more repositories returned on this pass. Waiting 10s before refreshing...", "info")
                        for _ in range(10):
                            if stop_check and stop_check():
                                break
                            time.sleep(1)
                        page = 1
                        continue
                    else:
                        if log_callback:
                            log_callback("[*] No more repositories returned by GitHub for this query.", "info")
                        break

                if log_callback:
                    log_callback(f"[*] Page {page}: multi-thread scanning {len(items)} repositories with {workers} threads...", "info")

                actual_workers = max(1, min(workers, len(items)))
                with concurrent.futures.ThreadPoolExecutor(max_workers=actual_workers) as executor:
                    futures = [executor.submit(_process_repo, item) for item in items]
                    for future in concurrent.futures.as_completed(futures):
                        if stop_check and stop_check():
                            break
                        try:
                            item_res = future.result()
                            if item_res:
                                with results_lock:
                                    results.append(item_res)
                                    if progress_callback:
                                        progress_callback(
                                            len(results),
                                            max_results,
                                            f"Found match: {item_res['full_name']} ({len(results)}/{max_results})..."
                                        )
                                if not infinite and len(results) >= max_results:
                                    break
                        except Exception:
                            pass

                total_count = data.get("total_count", 0)
                if page * per_page >= total_count or page * per_page >= 1000:
                    break

                page += 1
                time.sleep(0.4)

            except requests.RequestException as e:
                raise RuntimeError(f"Network error: {str(e)}")

        if progress_callback:
            if (page * per_page >= 1000 or (page - 1) * per_page >= 1000) and len(results) < max_results:
                msg = f"Search completed (reached GitHub's 1,000 result limit). Found {len(results)} repositories."
            else:
                msg = f"Search completed. Found {len(results)} repositories."
            progress_callback(len(results), max_results, msg)

        return results
