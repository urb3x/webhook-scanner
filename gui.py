"""
Modern Graphical User Interface for GitHub Hosted Site Searcher.
Built with CustomTkinter.
"""
import os
import sys
import csv
import json
import time
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk

from github_client import (
    GitHubSiteSearcher,
    load_saved_token,
    save_token
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class TokenDialog(ctk.CTkToplevel):
    def __init__(self, parent, current_token: str, on_save_callback):
        super().__init__(parent)
        self.title("GitHub Personal Access Token")
        self.geometry("520x280")
        self.resizable(False, False)
        self.on_save_callback = on_save_callback
        self.transient(parent)
        self.grab_set()

        # Center on parent
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        self.geometry(f"+{parent_x + 100}+{parent_y + 80}")

        lbl = ctk.CTkLabel(
            self,
            text="GitHub Personal Access Token (Optional)",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        lbl.pack(pady=(20, 5))

        info_lbl = ctk.CTkLabel(
            self,
            text=(
                "Adding a GitHub token increases the rate limit from 10 to 30 requests/min\n"
                "and prevents 'Rate Limit Exceeded' errors.\n"
                "Tokens need no special scopes (public repo access only)."
            ),
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        info_lbl.pack(pady=(0, 15), padx=20)

        self.token_entry = ctk.CTkEntry(
            self,
            width=420,
            placeholder_text="Paste your GitHub token (ghp_...)",
            show="*"
        )
        self.token_entry.pack(pady=5)
        if current_token:
            self.token_entry.insert(0, current_token)

        self.show_var = tk.BooleanVar(value=False)
        show_check = ctk.CTkCheckBox(
            self,
            text="Show Token",
            variable=self.show_var,
            command=self._toggle_show
        )
        show_check.pack(pady=(5, 15))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=5)

        save_btn = ctk.CTkButton(btn_frame, text="Save Token", width=120, command=self._on_save)
        save_btn.pack(side="left", padx=10)

        clear_btn = ctk.CTkButton(btn_frame, text="Clear Token", width=100, fg_color="#c0392b", hover_color="#962d22", command=self._on_clear)
        clear_btn.pack(side="left", padx=10)

        cancel_btn = ctk.CTkButton(btn_frame, text="Close", width=90, fg_color="#4a4a4a", hover_color="#3a3a3a", command=self.destroy)
        cancel_btn.pack(side="left", padx=10)

    def _toggle_show(self):
        self.token_entry.configure(show="" if self.show_var.get() else "*")

    def _on_save(self):
        new_token = self.token_entry.get().strip()
        save_token(new_token)
        if self.on_save_callback:
            self.on_save_callback(new_token)
        self.destroy()

    def _on_clear(self):
        self.token_entry.delete(0, tk.END)
        save_token("")
        if self.on_save_callback:
            self.on_save_callback("")
        self.destroy()


class GitHubSearchApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("GitHub Hosted Site Searcher")
        self.geometry("1120x760")
        self.minsize(920, 640)

        self.token = load_saved_token()
        self.searcher = GitHubSiteSearcher(token=self.token)

        self.is_searching = False
        self.cancel_flag = False
        self.search_thread = None
        self.results = []
        self.selected_item = None
        self.scanned_count = 0
        self.found_count = 0
        self.skipped_count = 0

        self._setup_styles()
        self._build_ui()
        self._refresh_rate_limit()

    def _setup_styles(self):
        # Configure ttk.Treeview dark theme
        style = ttk.Style(self)
        style.theme_use("clam")

        bg_color = "#181824"
        fg_color = "#e0e0e0"
        header_bg = "#252538"
        header_fg = "#ffffff"
        selected_bg = "#3a4a75"

        style.configure(
            "Custom.Treeview",
            background=bg_color,
            foreground=fg_color,
            fieldbackground=bg_color,
            rowheight=28,
            font=("Segoe UI", 10),
            borderwidth=0
        )
        style.map(
            "Custom.Treeview",
            background=[("selected", selected_bg)],
            foreground=[("selected", "#ffffff")]
        )
        style.configure(
            "Custom.Treeview.Heading",
            background=header_bg,
            foreground=header_fg,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padding=(8, 6)
        )
        style.map(
            "Custom.Treeview.Heading",
            background=[("active", "#32324b")]
        )

    def _build_ui(self):
        # Top Header Bar
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#181825", height=60)
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=20, pady=10)

        title_lbl = ctk.CTkLabel(
            title_box,
            text="🌐 GitHub Hosted Site Searcher",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_lbl.pack(side="left")

        subtitle_lbl = ctk.CTkLabel(
            title_box,
            text="Find repositories with live GitHub Pages or active websites",
            font=ctk.CTkFont(size=12),
            text_color="#8c8fa1"
        )
        subtitle_lbl.pack(side="left", padx=(15, 0), pady=(3, 0))

        header_right = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_right.pack(side="right", padx=20, pady=10)

        self.rate_limit_lbl = ctk.CTkLabel(
            header_right,
            text="Rate Limit: Checking...",
            font=ctk.CTkFont(size=12),
            text_color="#a6adc8"
        )
        self.rate_limit_lbl.pack(side="left", padx=10)

        self.token_btn = ctk.CTkButton(
            header_right,
            text="🔑 GitHub Token" if not self.token else "🔑 Token: Configured",
            width=130,
            height=30,
            fg_color="#313244" if not self.token else "#1e66f5",
            hover_color="#45475a" if not self.token else "#2a7bf8",
            command=self._open_token_dialog
        )
        self.token_btn.pack(side="left")

        # Query Controls Frame
        controls_frame = ctk.CTkFrame(self, fg_color="#1e1e2e", corner_radius=10)
        controls_frame.pack(fill="x", padx=15, pady=(10, 5))

        # Row 1: Search Entry + Buttons
        search_row = ctk.CTkFrame(controls_frame, fg_color="transparent")
        search_row.pack(fill="x", padx=15, pady=(12, 6))

        self.search_entry = ctk.CTkEntry(
            search_row,
            placeholder_text="Enter query (e.g. portfolio, game, docs, stars:>500, user:facebook, react)...",
            height=38,
            font=ctk.CTkFont(size=13)
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.bind("<Return>", lambda event: self._start_search())
        self.search_entry.insert(0, "portfolio")

        self.search_btn = ctk.CTkButton(
            search_row,
            text="🔍 Search",
            width=110,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_search
        )
        self.search_btn.pack(side="left", padx=(0, 10))

        self.cancel_btn = ctk.CTkButton(
            search_row,
            text="⏹ Stop",
            width=80,
            height=38,
            fg_color="#e78284",
            hover_color="#d20f39",
            state="disabled",
            command=self._cancel_search
        )
        self.cancel_btn.pack(side="left")

        # Row 2: Quick Preset Chips
        preset_row = ctk.CTkFrame(controls_frame, fg_color="transparent")
        preset_row.pack(fill="x", padx=15, pady=(0, 8))

        preset_lbl = ctk.CTkLabel(preset_row, text="Quick Presets:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#a6adc8")
        preset_lbl.pack(side="left", padx=(0, 8))

        presets = [
            ("⭐ Top Starred Sites", "stars:>1000"),
            ("🎣 Discord Webhooks", "discord webhook"),
            ("🎨 Portfolios", "portfolio in:name,description"),
            ("📚 Documentation", "topic:documentation"),
            ("🎮 Web Games", "game in:name,description,topics"),
            ("🛠️ Tools & Apps", "tools in:name,description")
        ]

        for title, query in presets:
            btn = ctk.CTkButton(
                preset_row,
                text=title,
                height=24,
                font=ctk.CTkFont(size=11),
                fg_color="#313244",
                hover_color="#45475a",
                command=lambda q=query: self._apply_preset(q)
            )
            btn.pack(side="left", padx=4)

        # Row 3: Filters and Options
        options_row = ctk.CTkFrame(controls_frame, fg_color="transparent")
        options_row.pack(fill="x", padx=15, pady=(4, 12))

        self.only_pages_var = tk.BooleanVar(value=True)
        self.only_pages_check = ctk.CTkCheckBox(
            options_row,
            text="Only GitHub Pages",
            variable=self.only_pages_var,
            font=ctk.CTkFont(size=12)
        )
        self.only_pages_check.pack(side="left", padx=(0, 16))

        self.include_homepage_var = tk.BooleanVar(value=True)
        self.include_homepage_check = ctk.CTkCheckBox(
            options_row,
            text="Include Custom Homepage",
            variable=self.include_homepage_var,
            font=ctk.CTkFont(size=12)
        )
        self.include_homepage_check.pack(side="left", padx=(0, 16))

        self.discord_webhook_var = tk.BooleanVar(value=False)
        self.discord_webhook_check = ctk.CTkCheckBox(
            options_row,
            text="🎣 Discord Webhook Only",
            variable=self.discord_webhook_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#5865F2",
            hover_color="#4752C4"
        )
        self.discord_webhook_check.pack(side="left", padx=(0, 20))

        sort_lbl = ctk.CTkLabel(options_row, text="Sort by:", font=ctk.CTkFont(size=12))
        sort_lbl.pack(side="left", padx=(0, 6))

        self.sort_combo = ctk.CTkComboBox(
            options_row,
            values=["Stars (Most ⭐)", "Best Match", "Recently Updated", "Most Forks"],
            width=160,
            state="readonly"
        )
        self.sort_combo.set("Stars (Most ⭐)")
        self.sort_combo.pack(side="left", padx=(0, 25))

        limit_lbl = ctk.CTkLabel(options_row, text="Max Results:", font=ctk.CTkFont(size=12))
        limit_lbl.pack(side="left", padx=(0, 6))

        self.limit_combo = ctk.CTkComboBox(
            options_row,
            values=["20", "50", "100", "200"],
            width=85,
            state="readonly"
        )
        self.limit_combo.set("50")
        self.limit_combo.pack(side="left")

        # Progress / Status Strip
        status_strip = ctk.CTkFrame(self, fg_color="transparent")
        status_strip.pack(fill="x", padx=18, pady=(4, 4))

        self.status_lbl = ctk.CTkLabel(
            status_strip,
            text="Ready. Enter keywords and click Search to list repos with hosted websites.",
            font=ctk.CTkFont(size=12),
            text_color="#cdd6f4"
        )
        self.status_lbl.pack(side="left")

        self.progress_bar = ctk.CTkProgressBar(status_strip, width=180, height=10)
        self.progress_bar.set(0)
        self.progress_bar.pack(side="right", padx=(10, 0))

        # Main Tabview holding Results Table and Live Scanner Logs
        self.tabview = ctk.CTkTabview(
            self,
            fg_color="#181825",
            segmented_button_fg_color="#1e1e2e",
            segmented_button_selected_color="#313244",
            segmented_button_selected_hover_color="#45475a",
            segmented_button_unselected_hover_color="#252538",
            corner_radius=10
        )
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(2, 4))

        self.tab_table = self.tabview.add("📊 Repositories")
        self.tab_logs = self.tabview.add("⚡ Live Scanner Logs")

        # --- Tab 1: Repositories Table & Detail ---
        table_frame = ctk.CTkFrame(self.tab_table, fg_color="#181825", corner_radius=8)
        table_frame.pack(fill="both", expand=True, padx=5, pady=(4, 4))

        columns = ("idx", "repo", "webhook", "site", "stars", "forks", "language", "pages", "updated")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            style="Custom.Treeview",
            selectmode="browse"
        )

        self.tree.heading("idx", text="#")
        self.tree.heading("repo", text="Repository")
        self.tree.heading("webhook", text="Webhook 🎣")
        self.tree.heading("site", text="Hosted Site URL (Double click to open)")
        self.tree.heading("stars", text="Stars ⭐")
        self.tree.heading("forks", text="Forks 🍴")
        self.tree.heading("language", text="Language")
        self.tree.heading("pages", text="Pages?")
        self.tree.heading("updated", text="Updated")

        self.tree.column("idx", width=40, minwidth=35, stretch=False, anchor="center")
        self.tree.column("repo", width=200, minwidth=140)
        self.tree.column("webhook", width=115, minwidth=90, anchor="center")
        self.tree.column("site", width=310, minwidth=180)
        self.tree.column("stars", width=75, minwidth=60, anchor="e")
        self.tree.column("forks", width=70, minwidth=55, anchor="e")
        self.tree.column("language", width=85, minwidth=65)
        self.tree.column("pages", width=60, minwidth=50, anchor="center")
        self.tree.column("updated", width=90, minwidth=75, anchor="center")

        tree_scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set)

        tree_scroll_y.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        # Selected Repository Detail Pane (Inside Tab 1)
        self.detail_frame = ctk.CTkFrame(self.tab_table, fg_color="#1e1e2e", corner_radius=10, height=135)
        self.detail_frame.pack(fill="x", padx=5, pady=(2, 4))
        self.detail_frame.pack_propagate(False)

        detail_content = ctk.CTkFrame(self.detail_frame, fg_color="transparent")
        detail_content.pack(fill="both", expand=True, padx=15, pady=8)

        # Top row of detail: repo title & actions
        detail_top = ctk.CTkFrame(detail_content, fg_color="transparent")
        detail_top.pack(fill="x")

        self.detail_title_lbl = ctk.CTkLabel(
            detail_top,
            text="Select a repository above to preview details and access site links",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#89b4fa"
        )
        self.detail_title_lbl.pack(side="left")

        self.detail_meta_lbl = ctk.CTkLabel(
            detail_top,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#a6adc8"
        )
        self.detail_meta_lbl.pack(side="left", padx=15)

        detail_buttons = ctk.CTkFrame(detail_top, fg_color="transparent")
        detail_buttons.pack(side="right")

        self.open_site_btn = ctk.CTkButton(
            detail_buttons,
            text="🌐 Open Hosted Site",
            width=140,
            height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
            state="disabled",
            fg_color="#a6e3a1",
            text_color="#11111b",
            hover_color="#94e2d5",
            command=self._open_selected_site
        )
        self.open_site_btn.pack(side="left", padx=4)

        self.open_repo_btn = ctk.CTkButton(
            detail_buttons,
            text="🐱 GitHub Repo",
            width=105,
            height=28,
            font=ctk.CTkFont(size=12),
            state="disabled",
            command=self._open_selected_repo
        )
        self.open_repo_btn.pack(side="left", padx=4)

        self.copy_site_btn = ctk.CTkButton(
            detail_buttons,
            text="📋 Copy Site URL",
            width=110,
            height=28,
            font=ctk.CTkFont(size=12),
            state="disabled",
            fg_color="#313244",
            hover_color="#45475a",
            command=self._copy_selected_site
        )
        self.copy_site_btn.pack(side="left", padx=4)

        self.copy_webhook_btn = ctk.CTkButton(
            detail_buttons,
            text="🎣 Copy Webhook",
            width=115,
            height=28,
            font=ctk.CTkFont(size=12),
            state="disabled",
            fg_color="#5865F2",
            hover_color="#4752C4",
            command=self._copy_selected_webhook
        )
        self.copy_webhook_btn.pack(side="left", padx=4)

        # Middle row of detail: site url and webhook url
        self.detail_site_lbl = ctk.CTkLabel(
            detail_content,
            text="Hosted Site: None",
            font=ctk.CTkFont(size=12),
            text_color="#a6e3a1",
            anchor="w"
        )
        self.detail_site_lbl.pack(fill="x", pady=(3, 1))

        self.detail_webhook_lbl = ctk.CTkLabel(
            detail_content,
            text="🎣 Discord Webhook: None detected",
            font=ctk.CTkFont(size=12),
            text_color="#6c7086",
            anchor="w"
        )
        self.detail_webhook_lbl.pack(fill="x", pady=(1, 2))

        self.detail_desc_lbl = ctk.CTkLabel(
            detail_content,
            text="Select an item from the list above.",
            font=ctk.CTkFont(size=11),
            text_color="#bac2de",
            anchor="w"
        )
        self.detail_desc_lbl.pack(fill="x")

        # --- Tab 2: Live Scanner Logs ---
        stats_header = ctk.CTkFrame(self.tab_logs, fg_color="#1e1e2e", corner_radius=8, height=44)
        stats_header.pack(fill="x", padx=6, pady=(6, 4))

        self.scanned_stat_lbl = ctk.CTkLabel(
            stats_header,
            text="🔄 Checked: 0",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#89b4fa"
        )
        self.scanned_stat_lbl.pack(side="left", padx=(15, 20), pady=8)

        self.found_stat_lbl = ctk.CTkLabel(
            stats_header,
            text="✅ Found: 0",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#2ecc71"
        )
        self.found_stat_lbl.pack(side="left", padx=(0, 20), pady=8)

        self.skipped_stat_lbl = ctk.CTkLabel(
            stats_header,
            text="❌ Skipped: 0",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#e74c3c"
        )
        self.skipped_stat_lbl.pack(side="left", padx=(0, 20), pady=8)

        self.autoscroll_var = tk.BooleanVar(value=True)
        autoscroll_check = ctk.CTkCheckBox(
            stats_header,
            text="Auto-scroll",
            variable=self.autoscroll_var,
            font=ctk.CTkFont(size=11)
        )
        autoscroll_check.pack(side="right", padx=(10, 15))

        clear_btn = ctk.CTkButton(
            stats_header,
            text="🗑️ Clear Logs",
            width=95,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#313244",
            hover_color="#45475a",
            command=self._clear_logs
        )
        clear_btn.pack(side="right", padx=5)

        self.log_textbox = ctk.CTkTextbox(
            self.tab_logs,
            font=("Consolas", 11),
            fg_color="#11111b",
            corner_radius=8,
            wrap="none"
        )
        self.log_textbox.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # Colored tags: matches are GREEN, skipped/no match are RED
        self.log_textbox.tag_config("match", foreground="#2ecc71")
        self.log_textbox.tag_config("skip", foreground="#e74c3c")
        self.log_textbox.tag_config("info", foreground="#89b4fa")
        self.log_textbox.tag_config("warn", foreground="#f39c12")

        # Bottom Action Bar
        bottom_bar = ctk.CTkFrame(self, fg_color="transparent", height=45)
        bottom_bar.pack(fill="x", padx=15, pady=(2, 10))

        self.results_counter_lbl = ctk.CTkLabel(
            bottom_bar,
            text="0 repositories listed",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#89b4fa"
        )
        self.results_counter_lbl.pack(side="left")

        export_box = ctk.CTkFrame(bottom_bar, fg_color="transparent")
        export_box.pack(side="right")

        self.copy_all_btn = ctk.CTkButton(
            export_box,
            text="📋 Copy All URLs",
            width=120,
            height=32,
            fg_color="#313244",
            hover_color="#45475a",
            state="disabled",
            command=self._copy_all_urls
        )
        self.copy_all_btn.pack(side="left", padx=5)

        self.export_csv_btn = ctk.CTkButton(
            export_box,
            text="💾 Export CSV",
            width=110,
            height=32,
            fg_color="#313244",
            hover_color="#45475a",
            state="disabled",
            command=self._export_csv
        )
        self.export_csv_btn.pack(side="left", padx=5)

        self.export_json_btn = ctk.CTkButton(
            export_box,
            text="💾 Export JSON",
            width=110,
            height=32,
            fg_color="#313244",
            hover_color="#45475a",
            state="disabled",
            command=self._export_json
        )
        self.export_json_btn.pack(side="left", padx=5)

    def _open_token_dialog(self):
        TokenDialog(self, self.token, self._on_token_updated)

    def _on_token_updated(self, new_token: str):
        self.token = new_token
        self.searcher.set_token(new_token)
        if self.token:
            self.token_btn.configure(text="🔑 Token: Configured", fg_color="#1e66f5", hover_color="#2a7bf8")
        else:
            self.token_btn.configure(text="🔑 GitHub Token", fg_color="#313244", hover_color="#45475a")
        self._refresh_rate_limit()

    def _refresh_rate_limit(self):
        def _check():
            try:
                rl = self.searcher.check_rate_limit()
                rem = rl.get("remaining", 10)
                lim = rl.get("limit", 10)
                reset_time = rl.get("reset", 0)
                secs = max(0, int(reset_time - time.time())) if reset_time else 0
                txt = f"Rate Limit: {rem}/{lim}"
                if secs > 0 and rem < lim:
                    txt += f" ({secs}s reset)"
                self.after(0, lambda: self.rate_limit_lbl.configure(text=txt))
            except Exception:
                self.after(0, lambda: self.rate_limit_lbl.configure(text="Rate: Unknown"))
        threading.Thread(target=_check, daemon=True).start()

    def _apply_preset(self, query: str):
        self.search_entry.delete(0, tk.END)
        if query == "discord webhook":
            self.discord_webhook_var.set(True)
            self.sort_combo.set("Recently Updated")
            self.limit_combo.set("30")
        else:
            self.search_entry.insert(0, query)
        self._start_search()

    def _start_search(self):
        if self.is_searching:
            return

        query = self.search_entry.get().strip()
        if not query and not self.discord_webhook_var.get():
            query = "stars:>10"

        sort_display = self.sort_combo.get()
        sort_map = {
            "Stars (Most ⭐)": "stars",
            "Best Match": None,
            "Recently Updated": "updated",
            "Most Forks": "forks"
        }
        sort_param = sort_map.get(sort_display, "stars")
        max_results = int(self.limit_combo.get())
        only_pages = self.only_pages_var.get()
        include_homepage = self.include_homepage_var.get()
        require_discord_webhook = self.discord_webhook_var.get()

        self.is_searching = True
        self.cancel_flag = False
        self.search_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress_bar.set(0)
        status_text = f"Searching GitHub for: '{query}'..."
        if require_discord_webhook:
            status_text += " [Discord Webhook filter: ON]"
        self.status_lbl.configure(text=status_text, text_color="#cdd6f4")

        # Clear previous results & reset counters
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.results = []
        self._reset_detail_view()
        self.results_counter_lbl.configure(text="Searching...")

        self.scanned_count = 0
        self.found_count = 0
        self.skipped_count = 0
        self.scanned_stat_lbl.configure(text="🔄 Checked: 0")
        self.found_stat_lbl.configure(text="✅ Found: 0")
        self.skipped_stat_lbl.configure(text="❌ Skipped: 0")

        self._append_log(
            f"[*] Starting search for: '{query}' (Target: {max_results}, Discord filter: {'ON' if require_discord_webhook else 'OFF'})...",
            "info"
        )

        def _worker():
            try:
                def progress(current, total, msg):
                    ratio = min(1.0, current / max(1, total)) if total > 0 else 0
                    self.after(0, lambda: (
                        self.progress_bar.set(ratio),
                        self.status_lbl.configure(text=msg)
                    ))

                def log_cb(msg: str, tag: str):
                    self.after(0, lambda m=msg, t=tag: self._append_log(m, t))

                results = self.searcher.search_repos(
                    query=query,
                    sort=sort_param,
                    max_results=max_results,
                    only_pages=only_pages,
                    include_homepage_only=include_homepage,
                    require_discord_webhook=require_discord_webhook,
                    stop_check=lambda: self.cancel_flag,
                    progress_callback=progress,
                    log_callback=log_cb
                )

                self.after(0, lambda: self._on_search_complete(results, None))
            except Exception as e:
                self.after(0, lambda: self._on_search_complete([], str(e)))

        self.search_thread = threading.Thread(target=_worker, daemon=True)
        self.search_thread.start()

    def _cancel_search(self):
        self.cancel_flag = True
        self.status_lbl.configure(text="Stopping search...")
        self._append_log("[-] Search stopped by user.", "warn")

    def _append_log(self, text: str, tag: str = "info"):
        if tag in ("match", "skip"):
            self.scanned_count += 1
            if tag == "match":
                self.found_count += 1
            elif tag == "skip":
                self.skipped_count += 1

            self.scanned_stat_lbl.configure(text=f"🔄 Checked: {self.scanned_count}")
            self.found_stat_lbl.configure(text=f"✅ Found: {self.found_count}")
            self.skipped_stat_lbl.configure(text=f"❌ Skipped: {self.skipped_count}")

        now_str = time.strftime("%H:%M:%S")
        line = f"[{now_str}] {text}\n"
        self.log_textbox.insert("end", line, tag)
        if self.autoscroll_var.get():
            self.log_textbox.see("end")

    def _clear_logs(self):
        self.log_textbox.delete("1.0", "end")

    def _on_search_complete(self, results, error_msg):
        self.is_searching = False
        self.search_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.progress_bar.set(1.0)
        self._refresh_rate_limit()

        if error_msg:
            self.status_lbl.configure(text=f"Error: {error_msg}", text_color="#f38ba8")
            self._append_log(f"[!] Error: {error_msg}", "skip")
            messagebox.showerror("Search Error", error_msg)
            return

        self.results = results
        self.results_counter_lbl.configure(
            text=f"Showing {len(results)} repositories | Checked {self.scanned_count} repos"
        )
        self._append_log(
            f"[+] Finished! Yielded {len(results)} matching repositories out of {self.scanned_count} checked.",
            "info"
        )

        for idx, r in enumerate(results, start=1):
            pages_icon = "✅" if r.get("has_pages") else "—"
            site_display = r.get("site_url") or "(None)"
            webhooks = r.get("discord_webhooks", [])
            if webhooks:
                webhook_disp = f"🎣 Found ({len(webhooks)})"
            elif r.get("has_discord_webhook"):
                webhook_disp = "🎣 Found"
            else:
                webhook_disp = "—"

            self.tree.insert(
                "",
                "end",
                iid=str(idx - 1),
                values=(
                    idx,
                    r.get("full_name"),
                    webhook_disp,
                    site_display,
                    f"{r.get('stars', 0):,}",
                    f"{r.get('forks', 0):,}",
                    r.get("language") or "N/A",
                    pages_icon,
                    r.get("updated_at")
                )
            )

        if results:
            self.status_lbl.configure(text=f"Done! Found {len(results)} repositories with hosted sites.", text_color="#a6e3a1")
            self.copy_all_btn.configure(state="normal")
            self.export_csv_btn.configure(state="normal")
            self.export_json_btn.configure(state="normal")
            # Select first item by default
            first_id = self.tree.get_children()[0]
            self.tree.selection_set(first_id)
            self._on_tree_select(None)
        else:
            self.status_lbl.configure(text="No repositories found matching your query and filter criteria.", text_color="#fab387")
            self.copy_all_btn.configure(state="disabled")
            self.export_csv_btn.configure(state="disabled")
            self.export_json_btn.configure(state="disabled")

    def _on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected:
            self._reset_detail_view()
            return

        idx = int(selected[0])
        if idx < 0 or idx >= len(self.results):
            return

        item = self.results[idx]
        self.selected_item = item

        self.detail_title_lbl.configure(text=item.get("full_name", ""))
        self.detail_meta_lbl.configure(
            text=f"⭐ {item.get('stars', 0):,} stars  •  🍴 {item.get('forks', 0):,} forks  •  {item.get('language')}"
        )

        site_url = item.get("site_url")
        if site_url:
            self.detail_site_lbl.configure(text=f"🌐 Hosted Site: {site_url}")
            self.open_site_btn.configure(state="normal")
            self.copy_site_btn.configure(state="normal")
        else:
            self.detail_site_lbl.configure(text="🌐 Hosted Site: None")
            self.open_site_btn.configure(state="disabled")
            self.copy_site_btn.configure(state="disabled")

        webhooks = item.get("discord_webhooks", [])
        if webhooks:
            wh_text = f"🎣 Discord Webhook ({len(webhooks)}): {webhooks[0]}"
            if len(webhooks) > 1:
                wh_text += f" (+{len(webhooks) - 1} more)"
            self.detail_webhook_lbl.configure(text=wh_text, text_color="#7289da")
            self.copy_webhook_btn.configure(state="normal")
        elif item.get("has_discord_webhook"):
            self.detail_webhook_lbl.configure(text="🎣 Discord Webhook: Detected in repository", text_color="#7289da")
            self.copy_webhook_btn.configure(state="disabled")
        else:
            self.detail_webhook_lbl.configure(text="🎣 Discord Webhook: None detected", text_color="#6c7086")
            self.copy_webhook_btn.configure(state="disabled")

        desc = item.get("description") or "No description provided."
        if len(desc) > 180:
            desc = desc[:177] + "..."
        self.detail_desc_lbl.configure(text=desc)

        self.open_repo_btn.configure(state="normal")

    def _on_tree_double_click(self, event):
        selected = self.tree.selection()
        if selected:
            idx = int(selected[0])
            if 0 <= idx < len(self.results):
                item = self.results[idx]
                url = item.get("site_url") or item.get("html_url")
                if url:
                    webbrowser.open(url)

    def _reset_detail_view(self):
        self.selected_item = None
        self.detail_title_lbl.configure(text="Select a repository above to preview details and access site links")
        self.detail_meta_lbl.configure(text="")
        self.detail_site_lbl.configure(text="Hosted Site: None")
        self.detail_webhook_lbl.configure(text="🎣 Discord Webhook: None detected", text_color="#6c7086")
        self.detail_desc_lbl.configure(text="Select an item from the list above.")
        self.open_site_btn.configure(state="disabled")
        self.open_repo_btn.configure(state="disabled")
        self.copy_site_btn.configure(state="disabled")
        self.copy_webhook_btn.configure(state="disabled")

    def _copy_selected_webhook(self):
        if self.selected_item and self.selected_item.get("discord_webhooks"):
            webhook_url = self.selected_item["discord_webhooks"][0]
            self.clipboard_clear()
            self.clipboard_append(webhook_url)
            messagebox.showinfo("Copied", f"Copied Discord Webhook URL to clipboard:\n{webhook_url}")

    def _open_selected_site(self):
        if self.selected_item and self.selected_item.get("site_url"):
            webbrowser.open(self.selected_item["site_url"])

    def _open_selected_repo(self):
        if self.selected_item and self.selected_item.get("html_url"):
            webbrowser.open(self.selected_item["html_url"])

    def _copy_selected_site(self):
        if self.selected_item and self.selected_item.get("site_url"):
            self.clipboard_clear()
            self.clipboard_append(self.selected_item["site_url"])
            messagebox.showinfo("Copied", f"Copied site URL to clipboard:\n{self.selected_item['site_url']}")

    def _copy_all_urls(self):
        urls = [r["site_url"] for r in self.results if r.get("site_url")]
        if not urls:
            messagebox.showwarning("Empty", "No hosted site URLs to copy.")
            return

        text = "\n".join(urls)
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", f"Copied {len(urls)} site URLs to clipboard!")

    def _export_csv(self):
        if not self.results:
            return
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            title="Save Results as CSV"
        )
        if not filename:
            return

        try:
            with open(filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "full_name", "site_url", "stars", "forks", "language", "html_url", "pages_url", "homepage_url", "discord_webhooks", "description", "updated_at"
                ])
                writer.writeheader()
                for r in self.results:
                    writer.writerow({
                        "full_name": r.get("full_name"),
                        "site_url": r.get("site_url"),
                        "stars": r.get("stars"),
                        "forks": r.get("forks"),
                        "language": r.get("language"),
                        "html_url": r.get("html_url"),
                        "pages_url": r.get("pages_url"),
                        "homepage_url": r.get("homepage_url"),
                        "discord_webhooks": "; ".join(r.get("discord_webhooks", [])),
                        "description": r.get("description"),
                        "updated_at": r.get("updated_at")
                    })
            messagebox.showinfo("Export Successful", f"Saved {len(self.results)} entries to:\n{filename}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def _export_json(self):
        if not self.results:
            return
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            title="Save Results as JSON"
        )
        if not filename:
            return

        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(self.results, f, indent=2)
            messagebox.showinfo("Export Successful", f"Saved {len(self.results)} entries to:\n{filename}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))


def run_gui():
    app = GitHubSearchApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
