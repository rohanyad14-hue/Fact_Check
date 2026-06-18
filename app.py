"""
Main GUI Application — CustomTkinter window with sidebar navigation.

Manages screen switching and coordinates with the backend orchestrator.
"""

import asyncio
import threading
import logging
import customtkinter as ctk

import config
from scrape_runner import ScraperOrchestrator
from database import is_connected, setup_indexes
from scheduler import ScrapeScheduler

from gui.settings_screen import SettingsScreen
from gui.tender_list_screen import TenderListScreen
from gui.tender_detail_screen import TenderDetailScreen
from gui.supplier_match_screen import SupplierMatchScreen

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class TenderAgentApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.title("Tender Agent")
        self.geometry("1280x780")
        self.minsize(1000, 600)

        # Backend
        self.orchestrator = ScraperOrchestrator()
        self.scheduler = None
        self._current_filters = self._default_filters()
        self._current_tenders = []

        # Setup MongoDB indexes
        try:
            if is_connected():
                setup_indexes()
        except Exception:
            logger.warning("MongoDB not available")

        # Layout: sidebar + content area
        self._build_sidebar()
        self._build_content_area()
        self._build_status_bar()

        # Show settings screen first
        self.show_screen("settings")

    def _default_filters(self) -> dict:
        return {
            "keywords": [],
            "categories": [],
            "min_value": None,
            "max_value": None,
            "locations": [],
            "org_type": "all",
            "tender_type": "all",
            "enrich_top_n": 5,
        }

    # ─────────────────────────────────────────
    # Layout
    # ─────────────────────────────────────────
    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo / title
        title = ctk.CTkLabel(
            self.sidebar, text="Tender Agent",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title.pack(pady=(20, 5))

        subtitle = ctk.CTkLabel(
            self.sidebar, text="GeM + CPPP Scanner",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        subtitle.pack(pady=(0, 20))

        # Navigation buttons
        self.nav_buttons = {}
        nav_items = [
            ("settings", "Settings"),
            ("tenders", "Tender List"),
            ("detail", "Tender Detail"),
            ("suppliers", "Supplier Match"),
        ]
        for key, label in nav_items:
            btn = ctk.CTkButton(
                self.sidebar, text=label, height=40,
                fg_color="transparent", text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"),
                anchor="w", corner_radius=8,
                command=lambda k=key: self.show_screen(k),
            )
            btn.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[key] = btn

        # Spacer
        spacer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        # Action buttons at bottom
        self.scrape_btn = ctk.CTkButton(
            self.sidebar, text="Scrape Now",
            height=40, corner_radius=8,
            command=self._on_scrape_now,
        )
        self.scrape_btn.pack(fill="x", padx=10, pady=3)

        self.export_btn = ctk.CTkButton(
            self.sidebar, text="Export Excel",
            height=40, corner_radius=8,
            fg_color="#2d8a4e", hover_color="#236b3c",
            command=self._on_export,
        )
        self.export_btn.pack(fill="x", padx=10, pady=3)

        # DB status
        db_status = "Connected" if is_connected() else "Offline"
        db_color = "#2d8a4e" if is_connected() else "#c0392b"
        self.db_label = ctk.CTkLabel(
            self.sidebar, text=f"MongoDB: {db_status}",
            font=ctk.CTkFont(size=11), text_color=db_color,
        )
        self.db_label.pack(pady=(10, 15))

    def _build_content_area(self):
        self.content = ctk.CTkFrame(self, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)

        # Create all screens (stacked, only one visible at a time)
        self.screens = {}
        self.screens["settings"] = SettingsScreen(
            self.content, self._current_filters,
            on_save=self._on_settings_saved,
        )
        self.screens["tenders"] = TenderListScreen(
            self.content,
            on_select=self._on_tender_selected,
            on_match=self._on_match_supplier,
        )
        self.screens["detail"] = TenderDetailScreen(self.content)
        self.screens["suppliers"] = SupplierMatchScreen(self.content)

        for screen in self.screens.values():
            screen.pack(fill="both", expand=True)
            screen.pack_forget()  # hide all initially

    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(self, height=30, corner_radius=0)
        self.status_bar.pack(side="bottom", fill="x")

        self.status_label = ctk.CTkLabel(
            self.status_bar, text="Ready",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self.status_label.pack(side="left", padx=10)

        self.tender_count_label = ctk.CTkLabel(
            self.status_bar, text="Tenders: 0",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self.tender_count_label.pack(side="right", padx=10)

    # ─────────────────────────────────────────
    # Navigation
    # ─────────────────────────────────────────
    def show_screen(self, name: str):
        """Switch to the given screen."""
        for key, screen in self.screens.items():
            screen.pack_forget()
        self.screens[name].pack(fill="both", expand=True)

        # Highlight active nav button
        for key, btn in self.nav_buttons.items():
            if key == name:
                btn.configure(fg_color=("gray75", "gray25"))
            else:
                btn.configure(fg_color="transparent")

    def set_status(self, text: str):
        """Update the status bar text."""
        self.status_label.configure(text=text)

    # ─────────────────────────────────────────
    # Callbacks
    # ─────────────────────────────────────────
    def _on_settings_saved(self, filters: dict):
        """Called when user saves settings."""
        self._current_filters = filters
        self.set_status("Settings saved")
        logger.info(f"Filters updated: {filters}")

    def _on_scrape_now(self):
        """Run a scrape in a background thread."""
        self.scrape_btn.configure(state="disabled", text="Scraping...")
        self.set_status("Scraping GeM + CPPP...")

        def do_scrape():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(
                    self.orchestrator.scrape_all(
                        filters=self._current_filters,
                        save_to_db=True,
                    )
                )
                self._current_tenders = [t.to_dict() for t in results]
                # Update GUI from main thread
                self.after(0, self._scrape_complete, len(results))
            except Exception as e:
                logger.error(f"Scrape failed: {e}", exc_info=True)
                self.after(0, self._scrape_failed, str(e))
            finally:
                loop.close()

        thread = threading.Thread(target=do_scrape, daemon=True)
        thread.start()

    def _scrape_complete(self, count: int):
        """Update GUI after scrape finishes."""
        self.scrape_btn.configure(state="normal", text="Scrape Now")
        self.set_status(f"Scrape complete: {count} tenders found")
        self.tender_count_label.configure(text=f"Tenders: {count}")

        # Refresh tender list screen
        self.screens["tenders"].load_tenders(self._current_tenders)
        self.show_screen("tenders")

    def _scrape_failed(self, error: str):
        self.scrape_btn.configure(state="normal", text="Scrape Now")
        self.set_status(f"Scrape failed: {error[:80]}")

    def _on_tender_selected(self, tender: dict):
        """Called when user clicks a tender in the list."""
        self.screens["detail"].show_tender(tender)
        self.show_screen("detail")

    def _on_match_supplier(self, tender: dict):
        """Called when user clicks 'Match Suppliers' on a tender."""
        self.set_status("Matching suppliers...")
        self.screens["suppliers"].run_matching(tender)
        self.show_screen("suppliers")
        self.set_status("Supplier matching complete")

    def _on_export(self):
        """Export current tenders to Excel."""
        if not self._current_tenders:
            # Try loading from DB
            tenders = self.orchestrator.get_saved_tenders(
                keywords=self._current_filters.get("keywords"),
                min_value=self._current_filters.get("min_value"),
                max_value=self._current_filters.get("max_value"),
            )
            if not tenders:
                self.set_status("No tenders to export")
                return
            self._current_tenders = tenders

        try:
            filepath = self.orchestrator.export_to_excel(self._current_tenders)
            self.set_status(f"Exported to {filepath.name}")
            logger.info(f"Excel exported: {filepath}")
        except Exception as e:
            self.set_status(f"Export failed: {e}")
            logger.error(f"Export failed: {e}", exc_info=True)

    def on_closing(self):
        """Clean shutdown."""
        if self.scheduler and self.scheduler.is_running:
            self.scheduler.stop()
        self.destroy()
