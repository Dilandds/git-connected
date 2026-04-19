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
    
    # Background colors – dark palette
    background = '#22262c'
    card_background = '#2a2e34'
    # Upload card (sidebar): subtle grey gradient + shadow — distinct from flat cards
    upload_card_gradient_top = '#383d46'
    upload_card_gradient_mid = '#2d323a'
    upload_card_gradient_bottom = '#1f2329'
    gradient_start = '#22262c'
    gradient_mid = '#3a3e48'
    gradient_end = '#717584'
    
    # Text colors
    text_primary = '#E0ECF4'
    text_secondary = '#8FAABE'
    text_title = '#F0F6FA'
    text_subtext = '#7A98AE'
    text_white = 'white'
    # Dark text for light surfaces (e.g. Help FAQ answer pane on white)
    text_on_light = '#1c2129'
    text_on_light_muted = '#4a5568'
    separator_on_light = '#d1d5db'
    
    # Button colors
    button_primary = '#2596BE'
    button_primary_hover = '#1E7FA3'
    button_primary_pressed = '#186A8A'
    button_default_bg = '#2e323a'
    button_default_border = '#3a3e48'
    
    # Row colors
    row_bg_standard = '#2a2e34'
    row_bg_hover = '#32363e'
    row_bg_highlight = '#2e3840'
    row_bg_highlight_hover = '#364048'
    
    # Border and separator colors
    border_standard = '#32363e'
    border_light = '#3a3e48'
    border_medium = '#4a4e58'
    border_highlight = '#2596BE'
    separator = '#32363e'
    
    # Special colors
    icon_blue = '#2596BE'
    icon_info_gray = '#8a8e98'
    icon_warning = '#E8A040'
    scrollbar_handle = '#3a3e48'
    scrollbar_handle_hover = '#4a4e58'
    combobox_arrow = '#8a8e98'
    
    # Footer colors
    footer_warning_bg = '#2e2a20'
    footer_warning_border = '#3a3628'
    
    # Input colors
    input_bg = '#2a2e34'
    input_border = '#3a3e48'
    input_border_hover = '#4a4e58'
    
    # Estimated Weight card: material combo + three rows
    weight_panel_bg = '#636877'
    weight_panel_hover = '#6F7588'
    
    # Total Surface Area — "Total area" row only
    surface_total_area_bg = '#3d5a9b'
    surface_total_area_hover = '#4568a8'
    
    def get_color(self, color_name):
        """Get color by name."""
        return getattr(self, color_name, None)


# Create default theme instance
default_theme = Theme()


def sidebar_section_card_stylesheet(theme):
    """Gradient + border shared by all left sidebar section cards.

    Glossy / dimensional look (same palette as Theme): top highlight stop, deeper
    vertical shading, and per-side borders for a light top/left vs dark bottom/right bevel.
    """
    return (
        f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
        f"stop:0 {theme.border_medium}, "
        f"stop:0.12 {theme.upload_card_gradient_top}, "
        f"stop:0.52 {theme.upload_card_gradient_mid}, "
        f"stop:1 {theme.upload_card_gradient_bottom}); "
        f"border-top: 1px solid {theme.border_medium}; "
        f"border-left: 1px solid {theme.border_light}; "
        f"border-right: 1px solid {theme.border_standard}; "
        f"border-bottom: 1px solid {theme.upload_card_gradient_bottom}; "
        f"border-radius: 14px;"
    )

# Font Constants
FONT_FAMILY = 'Calibri'
FONT_FAMILY_CSS = "'Calibri', 'Inter', 'Roboto', 'Segoe UI', sans-serif"
FONTS = {
    'family': FONT_FAMILY_CSS,
    'title_size': '16px',
    'subtitle_size': '14px',
    'body_size': '11px',
    'value_size': '13px',
}


def make_font(size=None, bold=False, pixel_size=None, weight=None):
    """Create a QFont with the app's standard family for cross-platform consistency.
    
    Args:
        size: Point size (use for most UI text)
        bold: Whether to set bold
        pixel_size: Pixel size (use instead of size when pixel-perfect control needed)
        weight: QFont weight (e.g. 600 for semi-bold). Overrides bold if set.
    """
    from PyQt5.QtGui import QFont as _QFont
    f = _QFont(FONT_FAMILY)
    if pixel_size is not None:
        f.setPixelSize(pixel_size)
    elif size is not None:
        f.setPointSize(size)
    if weight is not None:
        f.setWeight(weight)
    elif bold:
        f.setBold(True)
    return f


def get_global_stylesheet(theme=None):
    """Get the complete global stylesheet for the application."""
    if theme is None:
        theme = default_theme

    _sc = sidebar_section_card_stylesheet(theme)

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
        /* Specific upload button - glossy blue with rounded corners */
        QPushButton#uploadBtn {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #5DADE2,
                stop:0.4 #3B8ED0,
                stop:0.6 #2E78B8,
                stop:1 #1A5F9E);
            color: {theme.text_white};
            border: 1px solid #1A5F9E;
            border-radius: 22px;
            padding: 12px 20px;
            font-size: 15px;
            font-weight: bold;
            margin-top: 2px;
            margin-bottom: 14px;
        }}
        QPushButton#uploadBtn:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #6BB8E8,
                stop:0.4 #4A9AD8,
                stop:0.6 #3888C8,
                stop:1 #2068A8);
        }}
        QPushButton#uploadBtn:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2E78B8,
                stop:0.4 #1A5F9E,
                stop:0.6 #155288,
                stop:1 #104572);
        }}
        /* Specific label styles - must come before general QLabel to override */
        QLabel#titleLabel {{
            color: {theme.text_title};
            font-family: {FONTS['family']};
            font-weight: bold;
            font-size: {FONTS['title_size']};
        }}
        QLabel#infoLabel {{
            color: {theme.text_white};
            font-family: {FONTS['family']};
        }}
        QWidget#adjustWeightHeader {{
            background-color: transparent;
            border: none;
        }}
        QLabel#adjustWeightCollapseArrow {{
            color: {theme.text_secondary};
            background-color: transparent;
            border: none;
            padding: 0px;
            margin: 0px;
        }}
        QLabel#helpAnswerTitle {{
            color: {theme.text_on_light};
            background-color: transparent;
            border: none;
        }}
        QLabel#helpAnswerBody {{
            color: {theme.text_on_light_muted};
            background-color: transparent;
            border: none;
        }}
        /* General QLabel style - less specific, won't override named labels */
        QLabel {{
            color: {theme.text_secondary};
            font-family: {FONTS['family']};
        }}
        QLabel#dimensionLabel {{
            color: #000000;
        }}
        QLabel#dimensionValue {{
            color: #000000;
        }}
        QFrame#uploadCard {{
            {_sc}
        }}
        QFrame#dimensionsCard {{
            {_sc}
        }}
        QFrame#dimensionRow {{
            background-color: #ffffff;
            border-radius: 8px;
        }}
        QFrame#surfaceAreaCard {{
            {_sc}
        }}
        QFrame#surfaceRowStandard {{
            background-color: #ffffff;
            border-radius: 8px;
        }}
        QFrame#surfaceRowTotalArea {{
            background-color: {theme.surface_total_area_bg};
            border-radius: 8px;
            border: none;
        }}
        QFrame#surfaceRowHighlight {{
            background-color: #ffffff;
            border-left: 4px solid {theme.border_highlight};
            border-top: none;
            border-right: none;
            border-bottom: none;
            border-radius: 8px;
        }}
        QLabel#surfaceTotalLabel {{
            color: {theme.text_white};
        }}
        QLabel#surfaceTotalValue {{
            color: {theme.text_white};
        }}
        QFrame#surfaceFooter {{
            background-color: #ffffff;
            border: 1px solid #d0d0d0;
            border-radius: 6px;
        }}
        QLabel#surfaceLabel {{
            color: #000000;
        }}
        QLabel#surfaceValue {{
            color: #000000;
        }}
        QFrame#weightCard {{
            {_sc}
        }}
        QFrame#weightRowStandard {{
            background-color: {theme.weight_panel_bg};
            border-radius: 8px;
        }}
        QFrame#weightRowHighlight {{
            background-color: {theme.weight_panel_bg};
            border: 1px solid {theme.border_highlight};
            border-radius: 8px;
        }}
        QLabel#weightLabel {{
            color: {theme.text_white};
        }}
        QLabel#weightValue {{
            color: {theme.text_white};
        }}
        QComboBox#materialCombo {{
            background-color: {theme.weight_panel_bg};
            border: 1px solid {theme.border_medium};
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 12px;
            color: {theme.text_white};
        }}
        QComboBox#materialCombo:hover {{
            border: 1px solid {theme.input_border_hover};
        }}
        QComboBox#materialCombo::drop-down {{
            border: none;
            border-left: 1px solid {theme.border_medium};
            width: 32px;
            background-color: transparent;
        }}
        QComboBox#materialCombo::down-arrow {{
            image: url({_dropdown_arrow_url()});
            width: 14px;
            height: 14px;
        }}
        QComboBox#materialCombo QAbstractItemView {{
            background-color: {theme.weight_panel_bg};
            border: 1px solid {theme.border_medium};
            border-radius: 8px;
            color: {theme.text_white};
            selection-background-color: {theme.weight_panel_hover};
            selection-color: {theme.text_white};
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
            {_sc}
        }}
        QFrame#scaleRowStandard {{
            background-color: {theme.weight_panel_bg};
            border: 1px solid transparent;
            border-radius: 8px;
        }}
        QFrame#scaleRowHighlight {{
            background-color: {theme.row_bg_highlight};
            border: 1px solid {theme.border_highlight};
            border-radius: 8px;
        }}
        QFrame#scaleRowComparison {{
            background-color: {theme.row_bg_standard};
            border: none;
            border-left: 4px solid #FB923C;
            border-radius: 8px;
        }}
        QFrame#scaleRowVolume {{
            background-color: {theme.weight_panel_bg};
            border: 1px solid {theme.border_medium};
            border-radius: 8px;
        }}
        QLabel#scaleLabel {{
            color: {theme.text_primary};
        }}
        QLabel#scaleValue {{
            color: {theme.text_primary};
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
            background-color: {theme.input_bg};
            border: 1px solid {theme.input_border_hover};
        }}
        QLineEdit#targetWeightInput:focus {{
            background-color: {theme.input_bg};
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
            border: 1px solid {theme.border_standard};
            border-radius: 8px;
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
            border: 1px solid {theme.border_standard};
            border-radius: 8px;
        }}
        QFrame#pdfReportCard {{
            {_sc}
        }}
        QFrame#exportAnnotationsCard {{
            {_sc}
        }}
        QFrame#converterCard {{
            {_sc}
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
        /* QDialog styling - ensures white text on dark backgrounds for ALL dialogs (Windows fix).
           On macOS, native theming handles this; on Windows, default text is dark on our dark bg. */
        QDialog {{
            background-color: {theme.background};
            color: {theme.text_primary};
        }}
        QDialog QLabel {{
            color: {theme.text_primary};
            background-color: transparent;
        }}
        QDialog QLineEdit, QDialog QTextEdit, QDialog QPlainTextEdit, QDialog QSpinBox, QDialog QDoubleSpinBox, QDialog QComboBox {{
            background-color: {theme.input_bg};
            color: {theme.text_primary};
            border: 1px solid {theme.input_border};
            border-radius: 6px;
            padding: 6px 8px;
            selection-background-color: {theme.button_primary};
            selection-color: {theme.text_white};
        }}
        QDialog QLineEdit:focus, QDialog QTextEdit:focus, QDialog QPlainTextEdit:focus, QDialog QSpinBox:focus, QDialog QDoubleSpinBox:focus, QDialog QComboBox:focus {{
            border: 2px solid {theme.button_primary};
        }}
        QDialog QPushButton {{
            background-color: {theme.button_primary};
            color: {theme.text_white};
            border: none;
            border-radius: 6px;
            padding: 8px 20px;
            font-size: 13px;
            font-weight: bold;
            min-width: 80px;
        }}
        QDialog QPushButton:hover {{
            background-color: {theme.button_primary_hover};
            color: {theme.text_white};
        }}
        QDialog QPushButton:pressed {{
            background-color: {theme.button_primary_pressed};
            color: {theme.text_white};
        }}
        QDialog QCheckBox, QDialog QRadioButton {{
            color: {theme.text_primary};
            background-color: transparent;
        }}
        QDialog QGroupBox {{
            color: {theme.text_primary};
            background-color: transparent;
        }}
        /* QInputDialog: same dark bg + white text (Windows fix for native dialog text) */
        QInputDialog {{
            background-color: {theme.background};
            color: {theme.text_primary};
        }}
        QInputDialog QLabel {{
            color: {theme.text_primary};
            background-color: transparent;
        }}
        QInputDialog QLineEdit, QInputDialog QTextEdit, QInputDialog QSpinBox, QInputDialog QDoubleSpinBox, QInputDialog QComboBox {{
            background-color: {theme.input_bg};
            color: {theme.text_primary};
            border: 1px solid {theme.input_border};
            border-radius: 6px;
            padding: 6px 8px;
            selection-background-color: {theme.button_primary};
            selection-color: {theme.text_white};
        }}
        QInputDialog QPushButton {{
            background-color: {theme.button_primary};
            color: {theme.text_white};
            border: none;
            border-radius: 6px;
            padding: 8px 20px;
            font-size: 13px;
            font-weight: bold;
            min-width: 80px;
        }}
        QInputDialog QPushButton:hover {{
            background-color: {theme.button_primary_hover};
        }}
        QInputDialog QPushButton:pressed {{
            background-color: {theme.button_primary_pressed};
        }}
        /* QFileDialog: ensure list/tree views are readable on Windows */
        QFileDialog {{
            background-color: {theme.background};
            color: {theme.text_primary};
        }}
        QFileDialog QLabel, QFileDialog QToolButton {{
            color: {theme.text_primary};
            background-color: transparent;
        }}
        QFileDialog QListView, QFileDialog QTreeView, QFileDialog QComboBox, QFileDialog QLineEdit {{
            background-color: {theme.input_bg};
            color: {theme.text_primary};
            border: 1px solid {theme.input_border};
            selection-background-color: {theme.button_primary};
            selection-color: {theme.text_white};
        }}
        QFileDialog QPushButton {{
            background-color: {theme.button_primary};
            color: {theme.text_white};
            border: none;
            border-radius: 6px;
            padding: 6px 16px;
            font-weight: bold;
        }}
        QFileDialog QPushButton:hover {{
            background-color: {theme.button_primary_hover};
        }}
        /* Tooltips: white text on dark background */
        QToolTip {{
            color: {theme.text_white};
            background-color: {theme.card_background};
            border: 1px solid {theme.border_medium};
            padding: 4px 8px;
            border-radius: 4px;
        }}
        /* ---- Tab Bar: glossy / dimensional (same palette as mode switcher + sidebar cards) ---- */
        QTabBar#ectoTabBar {{
            background: {theme.background};
            border: none;
            border-bottom: 1px solid {theme.border_standard};
            min-height: 30px;
            padding-left: 4px;
        }}
        QTabBar#ectoTabBar::tab {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {theme.border_medium},
                stop:0.18 {theme.card_background},
                stop:1 {theme.background});
            color: {theme.text_white};
            border-top: 1px solid {theme.border_light};
            border-left: 1px solid {theme.border_light};
            border-right: 1px solid {theme.border_standard};
            border-bottom: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            padding-top: 5px;
            padding-right: 14px;
            padding-bottom: 6px;
            padding-left: 28px;
            margin-right: 2px;
            font-size: 12px;
            font-family: {FONTS['family']};
            min-width: 80px;
            min-height: 24px;
        }}
        QTabBar#ectoTabBar::tab:selected {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {theme.weight_panel_hover},
                stop:0.1 {theme.border_medium},
                stop:0.32 {theme.weight_panel_bg},
                stop:0.68 {theme.border_standard},
                stop:1 {theme.button_default_bg});
            color: {theme.text_white};
            font-weight: bold;
            border-top: 1px solid {theme.border_medium};
            border-left: 1px solid {theme.border_light};
            border-right: 1px solid {theme.border_standard};
            border-bottom: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            padding-top: 6px;
            padding-right: 14px;
            padding-bottom: 6px;
            padding-left: 30px;
            min-height: 24px;
        }}
        QTabBar#ectoTabBar::tab:hover:!selected {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {theme.border_light},
                stop:0.22 {theme.row_bg_hover},
                stop:1 {theme.card_background});
            color: {theme.text_white};
            border-top: 1px solid {theme.border_medium};
            border-left: 1px solid {theme.border_light};
            border-right: 1px solid {theme.border_standard};
            border-bottom: none;
            padding-top: 5px;
            padding-right: 14px;
            padding-bottom: 6px;
            padding-left: 28px;
        }}
        QTabBar#ectoTabBar::tab:last {{
            min-width: 32px;
            padding-top: 5px;
            padding-right: 12px;
            padding-bottom: 6px;
            padding-left: 12px;
            font-weight: bold;
            font-size: 16px;
            color: {theme.text_white};
            min-height: 24px;
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
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #5DADE2,
                stop:0.4 #3B8ED0,
                stop:0.6 #2E78B8,
                stop:1 #1A5F9E);
            color: {theme.text_white};
            border: 1px solid #1A5F9E;
            border-radius: 22px;
            padding: 12px 20px;
            font-size: 15px;
            font-weight: bold;
            margin-top: 2px;
            margin-bottom: 14px;
        }}
        QPushButton#{object_name}:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #6BB8E8,
                stop:0.4 #4A9AD8,
                stop:0.6 #3888C8,
                stop:1 #2068A8);
        }}
        QPushButton#{object_name}:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2E78B8,
                stop:0.4 #1A5F9E,
                stop:0.6 #155288,
                stop:1 #104572);
        }}
    """
