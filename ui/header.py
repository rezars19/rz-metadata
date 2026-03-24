"""
RZ Autometadata - Header UI
Builds the top header bar with app title and version badge.
No license info — this app is free/standalone.
Mixed into the main RZAutometadata class.
"""

import customtkinter as ctk

from ui.theme import COLORS
from core.auto_updater import CURRENT_VERSION


class HeaderMixin:
    """Mixin that adds header-building methods to the main app."""

    def _build_header(self):
        """Build the header bar."""
        header = ctk.CTkFrame(self.main_frame, fg_color=COLORS["bg_dark"], corner_radius=0, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        glow = ctk.CTkFrame(header, fg_color=COLORS["neon_blue"], height=2, corner_radius=0)
        glow.pack(fill="x", side="bottom")

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", padx=24, pady=10)

        ctk.CTkLabel(
            title_box, text="⚡ RZ Autometadata",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=COLORS["neon_blue"]
        ).pack(side="left")

        ctk.CTkLabel(
            title_box, text="  |  Metadata & Rename Tools",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["text_secondary"]
        ).pack(side="left", padx=(8, 0))

        # ── Version badge ──
        info_frame = ctk.CTkFrame(header, fg_color="transparent")
        info_frame.pack(side="right", padx=24)

        ctk.CTkLabel(
            info_frame, text=f" v{CURRENT_VERSION} ",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["neon_blue"],
            fg_color=COLORS["bg_card"], corner_radius=6
        ).pack(side="right", padx=(8, 0))
