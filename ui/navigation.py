"""
RZ Autometadata - Navigation Bar UI
Narrow icon sidebar for switching between pages:
  - Metadata Generator
  - Bulk Rename
Mixed into the main RZAutometadata class.
"""

import customtkinter as ctk

from ui.theme import COLORS


class NavigationMixin:
    """Mixin that adds the left navigation icon bar to switch between pages."""

    def _build_navigation(self, parent):
        """Build the narrow icon navigation bar on the far left."""
        self.nav_bar = ctk.CTkFrame(
            parent, fg_color=COLORS["bg_dark"], corner_radius=0,
            border_width=0, width=80
        )
        self.nav_bar.grid(row=0, column=0, sticky="nsew")
        self.nav_bar.grid_propagate(False)

        # Right border glow
        glow = ctk.CTkFrame(self.nav_bar, fg_color=COLORS["border"], width=1, corner_radius=0)
        glow.place(relx=1.0, rely=0, relheight=1.0, anchor="ne")

        # Nav items container
        nav_items = ctk.CTkFrame(self.nav_bar, fg_color="transparent")
        nav_items.pack(fill="x", padx=6, pady=(12, 0))

        # ── Metadata button ──
        self.nav_metadata_btn = ctk.CTkButton(
            nav_items, text="📋", width=56, height=56, corner_radius=12,
            font=ctk.CTkFont(size=24),
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["neon_blue"],
            command=lambda: self._switch_page("metadata")
        )
        self.nav_metadata_btn.pack(padx=6, pady=(0, 3))

        self.nav_metadata_label = ctk.CTkLabel(
            nav_items, text="Metadata",
            font=ctk.CTkFont(size=10, weight="bold"), text_color="#FFFFFF"
        )
        self.nav_metadata_label.pack(pady=(0, 8))

        # ── Bulk Rename button ──
        self.nav_rename_btn = ctk.CTkButton(
            nav_items, text="📝", width=56, height=56, corner_radius=12,
            font=ctk.CTkFont(size=24),
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["bg_card_hover"],
            border_width=1, border_color=COLORS["border"],
            command=lambda: self._switch_page("rename")
        )
        self.nav_rename_btn.pack(padx=6, pady=(0, 3))

        self.nav_rename_label = ctk.CTkLabel(
            nav_items, text="Rename",
            font=ctk.CTkFont(size=10, weight="bold"), text_color=COLORS["text_secondary"]
        )
        self.nav_rename_label.pack(pady=(0, 8))

        # Track current page
        self._current_page = "metadata"

        # All nav buttons and labels for easy iteration
        self._nav_items = {
            "metadata": (self.nav_metadata_btn, self.nav_metadata_label),
            "rename": (self.nav_rename_btn, self.nav_rename_label),
        }

        # All page frames for easy iteration (set after pages are built)
        self._page_frames = {}

    def _register_page_frame(self, page_name, frame):
        """Register a page frame for switching."""
        self._page_frames[page_name] = frame

    def _switch_page(self, page_name):
        """Switch between pages."""
        if page_name == self._current_page:
            return

        self._current_page = page_name

        # Hide all pages, show selected
        for name, frame in self._page_frames.items():
            if name == page_name:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_forget()

        # Update nav button styles
        for name, (btn, label) in self._nav_items.items():
            if name == page_name:
                btn.configure(fg_color=COLORS["accent_blue"], border_width=0)
                label.configure(text_color="#FFFFFF")
            else:
                btn.configure(
                    fg_color=COLORS["bg_card"],
                    border_width=1, border_color=COLORS["border"]
                )
                label.configure(text_color=COLORS["text_secondary"])
