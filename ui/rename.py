"""
RZ Autometadata - Bulk Rename UI
Page for renaming multiple files at once with prefix + number pattern.
Example: prefix="bg" → bg1.jpg, bg2.jpg, bg3.jpg
Mixed into the main RZAutomedata class.
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
import os
import threading

from ui.theme import COLORS
from core.rename_engine import preview_rename, validate_rename, execute_rename, undo_rename


class RenameMixin:
    """Mixin that adds the Bulk Rename page to the application."""

    def _build_rename_page(self, parent):
        """Build the Bulk Rename page."""
        self.rename_page_frame = ctk.CTkFrame(parent, fg_color="transparent")
        # Don't grid yet — navigation handles visibility

        # State
        self._rename_files = []        # List of absolute file paths
        self._rename_preview = []      # List of (path, old_name, new_name) tuples
        self._rename_history = None    # For undo

        # ── Main layout: sidebar (left) + preview table (right) ──
        self.rename_page_frame.grid_rowconfigure(0, weight=1)
        self.rename_page_frame.grid_columnconfigure(0, weight=0)  # Sidebar
        self.rename_page_frame.grid_columnconfigure(1, weight=1)  # Preview table

        # ═══════════════════════════════════════════════════════════════
        # LEFT SIDEBAR
        # ═══════════════════════════════════════════════════════════════
        sidebar = ctk.CTkFrame(
            self.rename_page_frame, fg_color=COLORS["bg_dark"],
            corner_radius=0, width=290, border_width=0
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        # Right border glow
        ctk.CTkFrame(sidebar, fg_color=COLORS["border"], width=1, corner_radius=0
                     ).place(relx=1.0, rely=0, relheight=1.0, anchor="ne")

        # Scrollable content
        scroll = ctk.CTkScrollableFrame(
            sidebar, fg_color="transparent",
            scrollbar_button_color=COLORS["bg_card"],
            scrollbar_button_hover_color=COLORS["border"]
        )
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Title ──
        ctk.CTkLabel(
            scroll, text="✏️  Bulk Rename",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["neon_blue"]
        ).pack(padx=16, pady=(16, 4), anchor="w")

        ctk.CTkLabel(
            scroll, text="Rename banyak file sekaligus",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"]
        ).pack(padx=16, pady=(0, 12), anchor="w")

        # ── Upload Zone ──
        upload_frame = ctk.CTkFrame(
            scroll, fg_color=COLORS["bg_card"], corner_radius=12,
            border_width=1, border_color=COLORS["border"], height=100
        )
        upload_frame.pack(padx=16, pady=(0, 12), fill="x")
        upload_frame.pack_propagate(False)

        upload_inner = ctk.CTkFrame(upload_frame, fg_color="transparent")
        upload_inner.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            upload_inner, text="📁",
            font=ctk.CTkFont(size=28)
        ).pack(pady=(0, 4))

        ctk.CTkButton(
            upload_inner, text="Browse Files",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLORS["accent_blue"], hover_color=COLORS["neon_blue"],
            width=130, height=30, corner_radius=8,
            command=self._rename_browse_files
        ).pack()

        # ── Settings Card ──
        ctk.CTkLabel(
            scroll, text="⚙️  Settings",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(padx=16, pady=(4, 6), anchor="w")

        settings_card = ctk.CTkFrame(
            scroll, fg_color=COLORS["bg_card"], corner_radius=12,
            border_width=1, border_color=COLORS["border"]
        )
        settings_card.pack(padx=16, pady=(0, 12), fill="x")

        # Prefix input
        ctk.CTkLabel(
            settings_card, text="Prefix (nama file baru):",
            font=ctk.CTkFont(size=12), text_color=COLORS["text_secondary"]
        ).pack(padx=14, pady=(12, 4), anchor="w")

        self._rename_prefix_var = ctk.StringVar(value="bg")
        self._rename_prefix_entry = ctk.CTkEntry(
            settings_card, textvariable=self._rename_prefix_var,
            font=ctk.CTkFont(size=13), height=36,
            fg_color=COLORS["bg_input"], border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            placeholder_text="Contoh: bg, photo, vector"
        )
        self._rename_prefix_entry.pack(padx=14, pady=(0, 8), fill="x")

        # Bind prefix changes to auto-update preview
        self._rename_prefix_var.trace_add("write", lambda *_: self._rename_update_preview())

        # Start number
        ctk.CTkLabel(
            settings_card, text="Mulai dari angka:",
            font=ctk.CTkFont(size=12), text_color=COLORS["text_secondary"]
        ).pack(padx=14, pady=(4, 4), anchor="w")

        self._rename_start_var = ctk.StringVar(value="1")
        self._rename_start_entry = ctk.CTkEntry(
            settings_card, textvariable=self._rename_start_var,
            font=ctk.CTkFont(size=13), height=36, width=100,
            fg_color=COLORS["bg_input"], border_color=COLORS["border"],
            text_color=COLORS["text_primary"]
        )
        self._rename_start_entry.pack(padx=14, pady=(0, 14), anchor="w")

        # Bind start number changes to auto-update preview
        self._rename_start_var.trace_add("write", lambda *_: self._rename_update_preview())

        # ── Preview Info ──
        self._rename_counter_label = ctk.CTkLabel(
            scroll, text="📋 0 files loaded",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_secondary"]
        )
        self._rename_counter_label.pack(padx=16, pady=(4, 8), anchor="w")

        # ── Action Buttons ──
        self._rename_apply_btn = ctk.CTkButton(
            scroll, text="✅  Apply Rename",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLORS["accent_blue"], hover_color=COLORS["neon_blue"],
            text_color="white", height=42, corner_radius=10,
            command=self._rename_apply
        )
        self._rename_apply_btn.pack(padx=16, pady=(4, 6), fill="x")

        self._rename_undo_btn = ctk.CTkButton(
            scroll, text="↩️  Undo Last Rename",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="transparent", hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["text_secondary"],
            border_width=1, border_color=COLORS["border"],
            height=36, corner_radius=10,
            command=self._rename_undo,
            state="disabled"
        )
        self._rename_undo_btn.pack(padx=16, pady=(0, 6), fill="x")

        self._rename_clear_btn = ctk.CTkButton(
            scroll, text="🗑  Clear All",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="transparent", hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["clear_orange"],
            border_width=1, border_color=COLORS["border"],
            height=36, corner_radius=10,
            command=self._rename_clear
        )
        self._rename_clear_btn.pack(padx=16, pady=(0, 16), fill="x")

        # ═══════════════════════════════════════════════════════════════
        # RIGHT PANEL — Preview Table
        # ═══════════════════════════════════════════════════════════════
        right = ctk.CTkFrame(self.rename_page_frame, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 12), pady=(8, 12))
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # Header
        header_frame = ctk.CTkFrame(right, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(
            header_frame, text="📋  Preview",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(side="left")

        self._rename_status_label = ctk.CTkLabel(
            header_frame, text="",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["success"]
        )
        self._rename_status_label.pack(side="right", padx=(0, 8))

        # Table frame
        table_frame = ctk.CTkFrame(
            right, fg_color=COLORS["bg_card"], corner_radius=12,
            border_width=1, border_color=COLORS["border"]
        )
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # Treeview style
        style = ttk.Style()
        style.configure(
            "Rename.Treeview",
            background=COLORS["bg_card"],
            foreground=COLORS["text_primary"],
            fieldbackground=COLORS["bg_card"],
            borderwidth=0,
            font=("Segoe UI", 11),
            rowheight=32
        )
        style.configure(
            "Rename.Treeview.Heading",
            background=COLORS["table_header"],
            foreground=COLORS["neon_blue"],
            font=("Segoe UI", 11, "bold"),
            borderwidth=0
        )
        style.map("Rename.Treeview",
                  background=[("selected", COLORS["accent_blue"])],
                  foreground=[("selected", "#ffffff")])

        # Treeview
        columns = ("num", "original", "arrow", "newname")
        self._rename_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            style="Rename.Treeview", selectmode="none"
        )

        self._rename_tree.heading("num", text="#")
        self._rename_tree.heading("original", text="Nama Asli")
        self._rename_tree.heading("arrow", text="")
        self._rename_tree.heading("newname", text="Nama Baru")

        self._rename_tree.column("num", width=50, minwidth=40, stretch=False, anchor="center")
        self._rename_tree.column("original", width=300, minwidth=150)
        self._rename_tree.column("arrow", width=50, minwidth=40, stretch=False, anchor="center")
        self._rename_tree.column("newname", width=300, minwidth=150)

        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self._rename_tree.yview)
        self._rename_tree.configure(yscrollcommand=scrollbar.set)

        self._rename_tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8)

        # Row tags for alternating colors
        self._rename_tree.tag_configure("even", background=COLORS["table_row_even"])
        self._rename_tree.tag_configure("odd", background=COLORS["table_row_odd"])

        # Empty state label
        self._rename_empty_label = ctk.CTkLabel(
            table_frame, text="📁  Browse files untuk mulai rename",
            font=ctk.CTkFont(size=14), text_color=COLORS["text_muted"]
        )
        self._rename_empty_label.place(relx=0.5, rely=0.5, anchor="center")

    # ═══════════════════════════════════════════════════════════════════════
    # ACTIONS
    # ═══════════════════════════════════════════════════════════════════════

    def _rename_browse_files(self):
        """Open file dialog to select files for renaming."""
        filetypes = [
            ("All Supported", "*.jpg *.jpeg *.png *.eps *.svg *.mp4 *.mov"),
            ("Images", "*.jpg *.jpeg *.png"),
            ("Vectors", "*.eps *.svg"),
            ("Videos", "*.mp4 *.mov"),
            ("All Files", "*.*")
        ]
        paths = filedialog.askopenfilenames(
            title="Select Files to Rename",
            filetypes=filetypes
        )
        if not paths:
            return

        # Add new files (avoid duplicates)
        existing = set(self._rename_files)
        for p in paths:
            if p not in existing:
                self._rename_files.append(p)

        self._rename_update_preview()

    def _rename_update_preview(self):
        """Update the preview table based on current prefix and files."""
        if not self._rename_files:
            return

        prefix = self._rename_prefix_var.get().strip()
        if not prefix:
            prefix = "file"

        # Parse start number
        try:
            start = int(self._rename_start_var.get().strip())
            if start < 0:
                start = 1
        except (ValueError, TypeError):
            start = 1

        # Generate preview
        self._rename_preview = preview_rename(self._rename_files, prefix, start)

        # Validate
        validation = validate_rename(self._rename_preview)

        # Clear tree
        for item in self._rename_tree.get_children():
            self._rename_tree.delete(item)

        # Hide empty label
        self._rename_empty_label.place_forget()

        # Populate table
        for i, (path, old_name, new_name) in enumerate(self._rename_preview):
            tag = "even" if i % 2 == 0 else "odd"
            self._rename_tree.insert("", "end", values=(
                i + 1, old_name, "→", new_name
            ), tags=(tag,))

        # Update counter
        count = len(self._rename_preview)
        self._rename_counter_label.configure(text=f"📋 {count} files loaded")
        self._rename_status_label.configure(
            text=f"{count} files ready",
            text_color=COLORS["success"] if validation["valid"] else COLORS["error"]
        )

        if not validation["valid"]:
            self._rename_status_label.configure(
                text=f"⚠ {', '.join(validation['errors'])}"
            )

    def _rename_apply(self):
        """Execute the rename operation."""
        if not self._rename_preview:
            messagebox.showinfo("No Files", "Upload files dulu sebelum rename.")
            return

        prefix = self._rename_prefix_var.get().strip()
        if not prefix:
            messagebox.showwarning("Prefix Required", "Isi prefix dulu (contoh: bg, photo, vector)")
            return

        # Validate
        validation = validate_rename(self._rename_preview)
        if not validation["valid"]:
            messagebox.showerror("Validation Error", "\n".join(validation["errors"]))
            return

        # Confirm
        count = len(self._rename_preview)
        if not messagebox.askyesno("Confirm Rename",
                                    f"Rename {count} files?\n\n"
                                    f"Pattern: {prefix}1, {prefix}2, ... {prefix}{count}\n\n"
                                    f"⚠ Pastikan tidak ada file yang sedang dibuka."):
            return

        # Execute
        result = execute_rename(self._rename_preview)

        # Save history for undo
        if result["history"]:
            self._rename_history = result["history"]
            self._rename_undo_btn.configure(state="normal")

        # Show result
        if result["failed"]:
            fail_msgs = "\n".join([f"  • {name}: {err}" for name, err in result["failed"][:5]])
            messagebox.showwarning(
                "Rename Partial",
                f"✅ {result['success']} renamed\n"
                f"❌ {len(result['failed'])} failed:\n{fail_msgs}"
            )
        else:
            messagebox.showinfo("Rename Complete", f"✅ {result['success']} files renamed successfully!")

        # Update file list with new paths and refresh preview
        self._rename_files = [new_path for new_path, _ in result["history"]]
        self._rename_update_preview()
        self._rename_status_label.configure(
            text=f"✅ {result['success']} files renamed!",
            text_color=COLORS["success"]
        )

    def _rename_undo(self):
        """Undo the last rename operation."""
        if not self._rename_history:
            messagebox.showinfo("Nothing to Undo", "Tidak ada rename yang bisa di-undo.")
            return

        if not messagebox.askyesno("Confirm Undo",
                                    f"Undo rename {len(self._rename_history)} files?\n"
                                    "File akan kembali ke nama asli."):
            return

        result = undo_rename(self._rename_history)

        if result["failed"]:
            fail_msgs = "\n".join([f"  • {name}: {err}" for name, err in result["failed"][:5]])
            messagebox.showwarning("Undo Partial",
                                    f"✅ {result['success']} restored\n"
                                    f"❌ {len(result['failed'])} failed:\n{fail_msgs}")
        else:
            messagebox.showinfo("Undo Complete", f"✅ {result['success']} files restored!")

        # Restore original file list
        self._rename_files = [orig_path for _, orig_path in self._rename_history]
        self._rename_history = None
        self._rename_undo_btn.configure(state="disabled")
        self._rename_update_preview()
        self._rename_status_label.configure(
            text=f"↩️ {result['success']} files restored",
            text_color=COLORS["warning"]
        )

    def _rename_clear(self):
        """Clear all files from the rename list."""
        if not self._rename_files:
            return
        if not messagebox.askyesno("Clear All", "Hapus semua file dari daftar rename?"):
            return

        self._rename_files.clear()
        self._rename_preview.clear()

        # Clear tree
        for item in self._rename_tree.get_children():
            self._rename_tree.delete(item)

        # Show empty state
        self._rename_empty_label.place(relx=0.5, rely=0.5, anchor="center")
        self._rename_counter_label.configure(text="📋 0 files loaded")
        self._rename_status_label.configure(text="")
