from __future__ import annotations


TOKENS = {
    "bg": "#F5F7FA",
    "surface": "#FFFFFF",
    "surface_alt": "#FAFBFC",
    "surface_soft": "#F2F5F8",
    "border": "#D9E1EA",
    "border_strong": "#C5D0DC",
    "text": "#0F172A",
    "text_muted": "#66758A",
    "text_soft": "#94A3B8",
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_pressed": "#1E40AF",
    "danger": "#C62828",
    "danger_soft": "#FDEDED",
    "success": "#0F766E",
    "warning": "#B45309",
    "shadow": "rgba(15, 23, 42, 0.06)",
}


METRICS = {
    "radius_sm": 8,
    "radius_md": 12,
    "radius_lg": 16,
    "space_xs": 4,
    "space_sm": 8,
    "space_md": 12,
    "space_lg": 16,
    "space_xl": 20,
    "control_h": 34,
    "button_h": 36,
    "toolbar_h": 52,
    "sidebar_w": 308,
    "props_w": 340,
    "results_h": 220,
}


def build_qss() -> str:
    c = TOKENS
    m = METRICS
    return f"""
    QWidget {{
        color: {c["text"]};
        font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
        font-size: 13px;
    }}

    QMainWindow {{
        background: {c["bg"]};
    }}

    QMainWindow::separator {{
        background: transparent;
        width: 3px;
        height: 3px;
    }}

    QMainWindow::separator:hover {{
        background: #CFE0FF;
    }}

    QDockWidget {{
        color: {c["text"]};
        font-weight: 600;
    }}

    QDockWidget::title {{
        text-align: left;
        padding: 8px 40px 8px 12px;
        background: {c["surface"]};
        border: 1px solid {c["border"]};
        border-bottom: none;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
    }}

    QLabel {{
        background: transparent;
    }}

    QDockWidget::close-button,
    QDockWidget::float-button {{
        border: none;
        background: transparent;
        width: 22px;
        height: 22px;
        padding: 3px;
        margin: 0 2px 0 0;
        icon-size: 14px;
        border-radius: 7px;
    }}

    QDockWidget::close-button:hover,
    QDockWidget::float-button:hover {{
        background: {c["surface_soft"]};
        border-radius: 6px;
    }}

    QFrame#Toolbar,
    QFrame#Sidebar,
    QFrame#CanvasPanel,
    QFrame#PropertyPanel,
    QFrame#ResultsPanel,
    QFrame#Card,
    QFrame#DetailPanel {{
        background: {c["surface"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
    }}

    QFrame#Sidebar,
    QFrame#PropertyPanel,
    QFrame#ResultsPanel {{
        border-top-left-radius: 0px;
        border-top-right-radius: 0px;
    }}

    QLabel#Title {{
        font-size: 20px;
        font-weight: 600;
        color: {c["text"]};
    }}

    QLabel#Subtitle,
    QLabel#Hint,
    QLabel#SectionHint,
    QLabel#StatusMuted {{
        color: {c["text_muted"]};
        font-size: 11px;
    }}

    QLabel#PanelTitle {{
        font-size: 13px;
        font-weight: 600;
        color: {c["text"]};
    }}

    QLabel#MetricLabel {{
        color: {c["text_muted"]};
        font-size: 12px;
    }}

    QLabel#MetricValue {{
        color: {c["text"]};
        font-size: 18px;
        font-weight: 600;
    }}

    QLabel#Badge {{
        background: {c["surface_soft"]};
        color: {c["text_muted"]};
        border: 1px solid {c["border"]};
        border-radius: {m["radius_sm"]}px;
        padding: 4px 8px;
    }}

    QPushButton {{
        min-height: {m["button_h"]}px;
        padding: 0 14px;
        border-radius: {m["radius_sm"]}px;
        border: 1px solid {c["border"]};
        background: {c["surface"]};
        color: {c["text"]};
    }}

    QPushButton:hover {{
        background: {c["surface_soft"]};
        border-color: {c["border_strong"]};
    }}

    QPushButton:pressed {{
        background: #EEF2F6;
    }}

    QPushButton:disabled {{
        color: {c["text_soft"]};
        background: {c["surface_alt"]};
        border-color: {c["border"]};
    }}

    QPushButton[role="primary"] {{
        background: {c["primary"]};
        color: white;
        border-color: {c["primary"]};
        font-weight: 600;
    }}

    QPushButton[role="primary"]:hover {{
        background: {c["primary_hover"]};
        border-color: {c["primary_hover"]};
    }}

    QPushButton[role="primary"]:pressed {{
        background: {c["primary_pressed"]};
        border-color: {c["primary_pressed"]};
    }}

    QToolButton {{
        min-height: 40px;
        text-align: left;
        padding: 0 14px;
        border-radius: {m["radius_sm"]}px;
        border: 1px solid {c["border"]};
        background: {c["surface_alt"]};
        color: {c["text"]};
        font-weight: 500;
    }}

    QToolButton:hover {{
        background: {c["surface_soft"]};
        border-color: {c["border_strong"]};
        color: {c["text"]};
    }}

    QToolButton:checked {{
        background: #EFF6FF;
        border-color: #BFDBFE;
        color: {c["primary"]};
        font-weight: 600;
    }}

    QTabWidget#SidebarTabs::pane {{
        border: none;
        background: transparent;
    }}

    QTabWidget#SidebarTabs QTabBar::tab {{
        min-width: 96px;
        padding: 10px 14px;
        margin-right: 6px;
        background: transparent;
        color: {c["text_muted"]};
        border-bottom: 2px solid transparent;
    }}

    QTabWidget#SidebarTabs QTabBar::tab:selected {{
        color: {c["text"]};
        border-bottom-color: {c["primary"]};
        font-weight: 600;
    }}

    QScrollArea {{
        border: none;
        background: transparent;
    }}

    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}

    QLineEdit,
    QComboBox,
    QPlainTextEdit,
    QTextEdit,
    QTableWidget {{
        background: {c["surface"]};
        border: 1px solid {c["border"]};
        border-radius: {m["radius_sm"]}px;
        color: {c["text"]};
        selection-background-color: #DBEAFE;
        selection-color: {c["text"]};
    }}

    QLineEdit,
    QComboBox {{
        min-height: {m["control_h"]}px;
        padding: 0 10px;
    }}

    QLineEdit[error="true"],
    QComboBox[error="true"] {{
        border-color: #DC2626;
        background: {c["danger_soft"]};
    }}

    QLineEdit:focus,
    QComboBox:focus,
    QTextEdit:focus,
    QPlainTextEdit:focus {{
        border-color: {c["primary"]};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 24px;
        background: transparent;
    }}

    QGroupBox {{
        border: none;
        background: transparent;
        margin-top: 10px;
        padding: 10px 0 0 0;
        font-weight: 600;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 0px;
        padding: 0;
        color: {c["text"]};
    }}

    QTabWidget::pane {{
        border: 1px solid {c["border"]};
        border-radius: {m["radius_md"]}px;
        background: {c["surface"]};
        top: -1px;
    }}

    QTabBar::tab {{
        background: transparent;
        color: {c["text_muted"]};
        padding: 8px 12px;
        margin-right: 4px;
        border-bottom: 2px solid transparent;
    }}

    QTabBar::tab:selected {{
        color: {c["text"]};
        border-bottom-color: {c["primary"]};
        font-weight: 600;
    }}

    QHeaderView::section {{
        background: {c["surface_alt"]};
        color: {c["text_muted"]};
        padding: 8px;
        border: none;
        border-bottom: 1px solid {c["border"]};
        border-right: 1px solid {c["border"]};
        font-weight: 600;
    }}

    QTableWidget {{
        gridline-color: {c["border"]};
    }}

    QTableWidget::item {{
        padding: 6px;
        border: none;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 4px 0;
    }}

    QScrollBar::handle:vertical {{
        background: #CBD5E1;
        min-height: 24px;
        border-radius: 5px;
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {{
        background: none;
        border: none;
    }}
    """
