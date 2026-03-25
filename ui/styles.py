"""
Centralized styling and theme definitions for the ECTOFORM application.
"""
import sys
from pathlib import Path


def _get_assets_dir():
    """Return path to assets directory (works for dev and PyInstaller)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'assets'
    return Path(__file__).resolve().parent.parent / 'assets'


def _dropdown_arrow_url():
    """Return file URL for dropdown arrow image (Qt stylesheet image: url())."""
    p = _get_assets_dir() / 'dropdown_arrow.png'
    return str(p).replace('\\', '/')


class Theme:
    """Centralized theme with all color definitions."""
    
    # Background colors
    background = '#F8FAFC'
    card_background = '#F8FAFC'
    
    # Text colors
    text_primary = '#0F172A'
    text_secondary = '#475569'
    text_title = '#1E293B'
    text_subtext = '#64748B'
    text_white = 'white'
    
    # Button colors
    button_primary = '#5294E2'
    button_primary_hover = '#4080D0'
    button_primary_pressed = '#3570B8'
    button_default_bg = '#E2E8F0'
    button_default_border = '#CBD5E1'
    
    # Row colors
    row_bg_standard = '#F0F7FF'
    row_bg_hover = '#E0E7FF'
    row_bg_highlight = '#E0F7FA'
    row_bg_highlight_hover = '#B2EBF2'
    
    # Border and separator colors
    border_standard = '#E2E8F0'
    border_light = '#D1D5DB'
    border_medium = '#9CA3AF'
    border_highlight = '#2DA398'
    separator = '#E0E6ED'
    
    # Special colors
    icon_blue = '#4A90E2'
    icon_info_gray = '#718096'
    icon_warning = '#92400E'
    scrollbar_handle = '#CBD5E1'
    scrollbar_handle_hover = '#94A3B8'
    combobox_arrow = '#6B7280'
    
    # Footer colors
    footer_warning_bg = '#FFFBEB'
    footer_warning_border = '#FEF3C7'
    
    # Input colors
    input_bg = '#FFFFFF'
    input_border = '#D1D5DB'
    input_border_hover = '#9CA3AF'
    
    def get_color(self, color_name):
        """Get color by name."""
        return getattr(self, color_name, None)


# Create default theme instance
default_theme = Theme()

# Font Constants
FONTS = {
    'family': "'Calibri', 'Inter', 'Roboto', 'Segoe UI', sans-serif",
    'title_size': '16px',
    'subtitle_size': '14px',
    'body_size': '11px',
    'value_size': '13px',
}


def get_global_stylesheet(theme=None):
    """Get the complete global stylesheet for the application."""
    if theme is None:
        theme = default_theme
    
    return f"""
        QMainWindow {{
            background-color: {theme.background};
        }}
        * {{
            font-family: {FONTS['family']};
        }}
        /* General QPushButton style - default, won't override specific buttons */
        QPushButton {{
            background-color: {theme.button_default_bg};
            color: {theme.text_title};
            border: 1px solid {theme.button_default_border};
            border-radius: 6px;
            padding: 8px 16px;
            font-size: 14px;
        }}
        /* Specific upload button - highest specificity, must come after general QPushButton */
        QPushButton#uploadBtn {{
            background-color: {theme.button_primary};
            color: {theme.text_white};
            border: none;
            border-radius: 8px;
            padding: 12px 20px;
            font-size: 14px;
            font-weight: bold;
        }}
        QPushButton#uploadBtn:hover {{
            background-color: {theme.button_primary_hover};
        }}
        QPushButton#uploadBtn:pressed {{
            background-color: {theme.button_primary_pressed};
        }}
        /* Specific label styles - must come before general QLabel to override */
        QLabel#titleLabel {{
            color: {theme.text_title};
            font-family: {FONTS['family']};
            font-weight: bold;
            font-size: {FONTS['title_size']};
        }}
        QLabel#infoLabel {{
            color: {theme.text_subtext};
            font-family: {FONTS['family']};
        }}
        /* General QLabel style - less specific, won't override named labels */
        QLabel {{
            color: {theme.text_secondary};
            font-family: {FONTS['family']};
        }}
        QLabel#dimensionLabel {{
            color: {theme.text_secondary};
        }}
        QLabel#dimensionValue {{
            color: {theme.text_primary};
        }}
        QFrame#dimensionsCard {{
            background-color: {theme.card_background};
            border-radius: 12px;
            border: none;
        }}
        QFrame#dimensionRow {{
            background-color: {theme.row_bg_standard};
            border-radius: 8px;
        }}
        QFrame#surfaceAreaCard {{
            background-color: {theme.card_background};
            border-radius: 12px;
            border: none;
        }}
        QFrame#surfaceRowStandard {{
            background-color: {theme.row_bg_standard};
            border-radius: 8px;
        }}
        QFrame#surfaceRowHighlight {{
            background-color: {theme.row_bg_highlight};
            border-left: 4px solid {theme.border_highlight};
            border-top: none;
            border-right: none;
            border-bottom: none;
            border-radius: 8px;
        }}
        QFrame#surfaceFooter {{
            background-color: {theme.background};
            border: 1px solid {theme.border_standard};
            border-radius: 6px;
        }}
        QLabel#surfaceLabel {{
            color: {theme.text_secondary};
        }}
        QLabel#surfaceValue {{
            color: {theme.text_primary};
        }}
        QFrame#weightCard {{
            background-color: {theme.card_background};
            border-radius: 12px;
            border: none;
        }}
        QFrame#weightRowStandard {{
            background-color: {theme.row_bg_standard};
            border-radius: 8px;
        }}
        QFrame#weightRowHighlight {{
            background-color: {theme.row_bg_highlight};
            border: 1px solid {theme.border_highlight};
            border-radius: 8px;
        }}
        QLabel#weightLabel {{
            color: {theme.text_secondary};
        }}
        QLabel#weightValue {{
            color: {theme.text_primary};
        }}
        QComboBox#materialCombo {{
            background-color: {theme.input_bg};
            border: 1px solid {theme.input_border};
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 12px;
            color: {theme.text_primary};
        }}
        QComboBox#materialCombo:hover {{
            border: 1px solid {theme.input_border_hover};
        }}
        QComboBox#materialCombo::drop-down {{
            border: none;
            border-left: 1px solid {theme.input_border};
            width: 32px;
        }}
        QComboBox#materialCombo::down-arrow {{
            image: url({_dropdown_arrow_url()});
            width: 14px;
            height: 14px;
        }}
        QComboBox#materialCombo QAbstractItemView {{
            background-color: {theme.input_bg};
            border: 1px solid {theme.input_border};
            border-radius: 8px;
            selection-background-color: {theme.row_bg_standard};
            selection-color: {theme.text_primary};
            padding: 4px;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {theme.scrollbar_handle};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {theme.scrollbar_handle_hover};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
            background: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}
        QFrame#adjustWeightCard {{
            background-color: {theme.card_background};
            border-radius: 12px;
            border: none;
        }}
        QFrame#scaleRowStandard {{
            background-color: {theme.row_bg_standard};
            border-radius: 8px;
        }}
        QFrame#scaleRowHighlight {{
            background-color: {theme.row_bg_highlight};
            border: 1px solid {theme.border_highlight};
            border-radius: 8px;
        }}
        QFrame#scaleRowComparison {{
            background-color: #FFF7ED;
            border-left: 4px solid #FB923C;
            border-radius: 8px;
        }}
        QLineEdit#targetWeightInput {{
            background-color: {theme.input_bg};
            border: 1px solid {theme.input_border};
            border-radius: 8px;
            padding: 10px 14px;
            font-size: 13px;
            color: {theme.text_primary};
        }}
        QLineEdit#targetWeightInput:hover {{
            border: 1px solid {theme.input_border_hover};
        }}
        QLineEdit#targetWeightInput:focus {{
            border: 2px solid {theme.button_primary};
        }}
        QPushButton#calculateScaleBtn {{
            background-color: {theme.button_primary};
            color: {theme.text_white};
            border: none;
            border-radius: 8px;
            padding: 10px 16px;
            font-size: 13px;
            font-weight: bold;
        }}
        QPushButton#calculateScaleBtn:hover {{
            background-color: {theme.button_primary_hover};
        }}
        QPushButton#calculateScaleBtn:pressed {{
            background-color: {theme.button_primary_pressed};
        }}
        QPushButton#calculateScaleBtn:disabled {{
            background-color: {theme.button_default_bg};
            color: {theme.text_secondary};
        }}
        QPushButton#exportScaledBtn {{
            background-color: #10B981;
            color: {theme.text_white};
            border: none;
            border-radius: 8px;
            padding: 10px 16px;
            font-size: 13px;
            font-weight: bold;
        }}
        QPushButton#exportScaledBtn:hover {{
            background-color: #059669;
        }}
        QPushButton#exportScaledBtn:pressed {{
            background-color: #047857;
        }}
        QPushButton#exportScaledBtn:disabled {{
            background-color: {theme.button_default_bg};
            color: {theme.text_secondary};
        }}
        QFrame#pdfReportCard {{
            background-color: {theme.card_background};
            border-radius: 12px;
            border: none;
        }}
        QFrame#reportCheckboxRow {{
            background-color: {theme.row_bg_standard};
            border-radius: 6px;
            border: none;
        }}
        QPushButton#exportPdfBtn {{
            background-color: #6366F1;
            color: {theme.text_white};
            border: none;
            border-radius: 8px;
            padding: 10px 16px;
            font-size: 13px;
            font-weight: bold;
        }}
        QPushButton#exportPdfBtn:hover {{
            background-color: #4F46E5;
        }}
        QPushButton#exportPdfBtn:pressed {{
            background-color: #4338CA;
        }}
        QPushButton#exportPdfBtn:disabled {{
            background-color: {theme.button_default_bg};
            color: {theme.text_secondary};
        }}
        /* QMessageBox styling - ensure proper colors on Windows and macOS */
        QMessageBox {{
            background-color: {theme.background};
            color: {theme.text_primary};
        }}
        QMessageBox QLabel {{
            background-color: transparent;
            color: {theme.text_primary};
        }}
        QMessageBox QTextEdit {{
            background-color: {theme.input_bg};
            color: {theme.text_primary};
            border: 1px solid {theme.input_border};
            border-radius: 6px;
        }}
        QMessageBox QPushButton {{
            background-color: {theme.button_primary};
            color: {theme.text_white};
            border: none;
            border-radius: 6px;
            padding: 8px 20px;
            font-size: 13px;
            font-weight: bold;
            min-width: 80px;
        }}
        QMessageBox QPushButton:hover {{
            background-color: {theme.button_primary_hover};
            color: {theme.text_white};
        }}
        QMessageBox QPushButton:pressed {{
            background-color: {theme.button_primary_pressed};
            color: {theme.text_white};
        }}
        QMessageBox QPushButton:default {{
            background-color: {theme.button_primary};
            color: {theme.text_white};
        }}
        QMessageBox QPushButton:focus {{
            background-color: {theme.button_primary};
            color: {theme.text_white};
        }}
        /* ---- Tab Bar Styling ---- */
        QTabBar#ectoTabBar {{
            background: {theme.background};
            border: none;
            border-bottom: 1px solid {theme.border_standard};
        }}
        QTabBar#ectoTabBar::tab {{
            background: {theme.button_default_bg};
            color: {theme.text_secondary};
            border: 1px solid {theme.border_standard};
            border-bottom: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            padding: 6px 18px;
            margin-right: 2px;
            font-size: 12px;
            font-family: {FONTS['family']};
            min-width: 80px;
        }}
        QTabBar#ectoTabBar::tab:selected {{
            background: {theme.card_background};
            color: {theme.text_primary};
            font-weight: bold;
            border-bottom: 2px solid {theme.button_primary};
        }}
        QTabBar#ectoTabBar::tab:hover:!selected {{
            background: {theme.row_bg_hover};
        }}
        QTabBar#ectoTabBar::tab:last {{
            /* "+" tab styling */
            min-width: 32px;
            padding: 6px 10px;
            font-weight: bold;
            font-size: 16px;
            color: {theme.text_secondary};
        }}
        QTabBar#ectoTabBar::close-button {{
            image: none;
            subcontrol-position: right;
            padding: 2px;
        }}
    """


def get_button_style(object_name="uploadBtn", theme=None):
    """Get button-specific stylesheet."""
    if theme is None:
        theme = default_theme
    
    return f"""
        QPushButton#{object_name} {{
            background-color: {theme.button_primary};
            color: {theme.text_white};
            border: none;
            border-radius: 8px;
            padding: 12px 20px;
            font-size: 14px;
            font-weight: bold;
        }}
        QPushButton#{object_name}:hover {{
            background-color: {theme.button_primary_hover};
        }}
        QPushButton#{object_name}:pressed {{
            background-color: {theme.button_primary_pressed};
        }}
    """
