from __future__ import annotations

import math
import sys
from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPointF, Property, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDockWidget,
    QFormLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .models import DistributedLoadSpec, ElementSpec, NodeLoadSpec, NodeSpec, SolveResult, StructureModel, SupportSpec
from .qt_styles import METRICS, TOKENS, build_qss
from .solver import SolveError, solve_structure


VIEW_LABELS = {
    "structure": "结构",
    "displacement": "位移",
    "axial": "轴力",
    "shear": "剪力",
    "moment": "弯矩",
    "reaction": "反力",
}

TOOL_LABELS = {
    "select": "选择 / 拖拽",
    "add_node": "放置节点",
    "add_element": "连接杆件",
    "add_support": "添加支座",
    "add_node_load": "添加节点荷载",
    "add_moment_load": "添加集中力偶",
    "add_dist_load": "添加分布荷载",
    "delete": "删除",
}


VIEW_LABELS = {
    "structure": "Structure",
    "displacement": "Displacement",
    "axial": "Axial",
    "shear": "Shear",
    "moment": "Moment",
    "reaction": "Reaction",
}

TOOL_LABELS = {
    "select": "Select / Drag",
    "add_node": "Place Node",
    "add_element": "Create Member",
    "add_support": "Add Support",
    "add_node_load": "Add Node Load",
    "add_moment_load": "Add Moment",
    "add_dist_load": "Add Distributed Load",
    "delete": "Delete",
}


def _c(name: str) -> QColor:
    return QColor(TOKENS[name])


def _pen(color: QColor, width: float = 1.0, *, dash: bool = False, round_cap: bool = False) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    if dash:
        pen.setStyle(Qt.DashLine)
    if round_cap:
        pen.setCapStyle(Qt.RoundCap)
    return pen


@dataclass(slots=True)
class MetricCard:
    title: QLabel
    value: QLabel


class FadeFrame(QFrame):
    def __init__(self, object_name: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if object_name:
            self.setObjectName(object_name)
        self._effect: QGraphicsOpacityEffect | None = None
        self._anim: QPropertyAnimation | None = None

    def fade_in(self) -> None:
        if self._effect is None:
            self._effect = QGraphicsOpacityEffect(self)
            self._effect.setOpacity(1.0)
            self.setGraphicsEffect(self._effect)
            self._anim = QPropertyAnimation(self._effect, b"opacity", self)
            self._anim.setDuration(150)
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
        if self._anim is None or self._effect is None:
            return
        self._anim.stop()
        self._effect.setOpacity(0.0)
        self._anim.start()


class ResultPanel(FadeFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("ResultsPanel", parent)
        self._panel_height = METRICS["results_h"]

    def getPanelHeight(self) -> int:
        return self._panel_height

    def setPanelHeight(self, value: int) -> None:
        self._panel_height = value
        self.setMaximumHeight(value)
        self.updateGeometry()

    panelHeight = Property(int, getPanelHeight, setPanelHeight)


class StructureCanvas(QWidget):
    clicked = Signal(QPointF)
    dragged = Signal(QPointF)
    released = Signal()
    moved = Signal(QPointF)
    left_canvas = Signal()

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window
        self.setMouseTracking(True)
        self.setMinimumSize(360, 320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.clicked.emit(event.position())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        pos = event.position()
        if event.buttons() & Qt.LeftButton:
            self.dragged.emit(pos)
        else:
            self.moved.emit(pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self.released.emit()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self.left_canvas.emit()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self.window.paint_canvas(painter, self.rect())


class DetailWindow(QMainWindow):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self.setWindowTitle("详细信息")
        self.resize(480, 640)
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("模型信息")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self.info_edit = QPlainTextEdit()
        self.info_edit.setReadOnly(True)
        layout.addWidget(self.info_edit, 1)

    def refresh(self, text: str) -> None:
        self.info_edit.setPlainText(text)


class DockTitleBar(QFrame):
    def __init__(self, dock: QDockWidget, title: str) -> None:
        super().__init__(dock)
        self.setObjectName("DockTitleBar")
        self.dock = dock

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(6)

        self.label = QLabel(title)
        self.label.setObjectName("DockTitleLabel")
        layout.addWidget(self.label)
        layout.addStretch(1)

        self.float_button = QToolButton()
        self.float_button.setObjectName("DockTitleButton")
        self.float_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarNormalButton))
        self.float_button.clicked.connect(self._toggle_float)
        layout.addWidget(self.float_button)

        self.close_button = QToolButton()
        self.close_button.setObjectName("DockTitleButton")
        self.close_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        self.close_button.clicked.connect(self.dock.hide)
        layout.addWidget(self.close_button)

        self.dock.topLevelChanged.connect(self._update_float_button)
        self.dock.windowTitleChanged.connect(self.label.setText)
        self._update_float_button()

    def _toggle_float(self) -> None:
        self.dock.setFloating(not self.dock.isFloating())
        self._update_float_button()

    def _update_float_button(self) -> None:
        icon = (
            QStyle.StandardPixmap.SP_TitleBarMaxButton
            if self.dock.isFloating()
            else QStyle.StandardPixmap.SP_TitleBarNormalButton
        )
        self.float_button.setIcon(self.style().standardIcon(icon))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("anaStruct 结构搭建器")
        self.resize(1580, 980)
        self.setMinimumSize(1320, 840)

        self.model = StructureModel()
        self.result: SolveResult | None = None
        self.grid_pixels = 56.0
        self.grid_margin = 52.0

        self.editor_tool = "select"
        self.view_mode = "structure"
        self.selected_node: str | None = None
        self.selected_element: str | None = None
        self.selected_node_load: str | None = None
        self.selected_dist_load: tuple[str | None, str | None, str | None] | None = None
        self.pending_element_start: str | None = None
        self.pending_dist_load_start: str | None = None
        self.dragging_node: str | None = None
        self.hover_world_point: tuple[float, float] | None = None
        self.detail_window = DetailWindow(self)

        self._build_ui()
        self._connect_signals()
        self._load_demo_model()

    def _build_ui(self) -> None:
        self.setStyleSheet(build_qss())
        self.setStatusBar(QStatusBar(self))
        self.setDockOptions(
            QMainWindow.AnimatedDocks
            | QMainWindow.AllowNestedDocks
            | QMainWindow.AllowTabbedDocks
            | QMainWindow.GroupedDragging
        )
        self.statusBar().showMessage("第 1 步：在画布上放置节点。")

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header = QVBoxLayout()
        title = QLabel("anaStruct 结构搭建器")
        title.setObjectName("Title")
        subtitle = QLabel("基于 anaStruct 的轻量结构建模与内力查看界面。")
        subtitle.setObjectName("Subtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        toolbar = QFrame()
        toolbar.setObjectName("Toolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 8, 12, 8)
        toolbar_layout.setSpacing(8)

        self.demo_button = QPushButton("示例模型")
        self.solve_button = QPushButton("计算")
        self.solve_button.setProperty("role", "primary")
        self.clear_button = QPushButton("清空")
        self.detail_button = QPushButton("详细信息")
        self.results_toggle = QPushButton("收起结果")
        self.panels_button = QToolButton()
        self.panels_button.setText("Panels")
        self.panels_button.setPopupMode(QToolButton.InstantPopup)
        self.view_combo = QComboBox()
        self.view_combo.addItems(list(VIEW_LABELS.values()))

        for widget in (self.demo_button, self.solve_button, self.clear_button, self.detail_button, self.results_toggle, self.panels_button):
            toolbar_layout.addWidget(widget)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(QLabel("视图"))
        toolbar_layout.addWidget(self.view_combo)
        root.addWidget(toolbar)

        self.canvas_panel = FadeFrame("CanvasPanel")
        root.addWidget(self.canvas_panel, 1)
        canvas_layout = QVBoxLayout(self.canvas_panel)
        canvas_layout.setContentsMargins(12, 12, 12, 12)
        canvas_layout.setSpacing(8)
        canvas_title_row = QHBoxLayout()
        canvas_title = QLabel("绘图区")
        canvas_title.setObjectName("PanelTitle")
        self.canvas_hint = QLabel("整数网格吸附，支持直接拖拽建模。")
        self.canvas_hint.setObjectName("SectionHint")
        canvas_title_row.addWidget(canvas_title)
        canvas_title_row.addStretch(1)
        canvas_title_row.addWidget(self.canvas_hint)
        canvas_layout.addLayout(canvas_title_row)
        self.canvas = StructureCanvas(self)
        self.canvas.setStyleSheet(f"background:{TOKENS['surface']}; border:1px solid {TOKENS['border']}; border-radius:12px;")
        canvas_layout.addWidget(self.canvas, 1)

        self.sidebar = FadeFrame("Sidebar")
        self.sidebar.setMinimumWidth(180)
        self._build_sidebar()
        self.sidebar_dock = self._create_dock("工具与默认值", "sidebar_dock", self.sidebar)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.sidebar_dock)

        self.properties = FadeFrame("PropertyPanel")
        self.properties.setMinimumWidth(220)
        self._build_properties()
        self.properties_dock = self._create_dock("属性与摘要", "properties_dock", self.properties)
        self.addDockWidget(Qt.RightDockWidgetArea, self.properties_dock)

        self.results_panel = ResultPanel()
        self.results_panel.setMinimumHeight(120)
        self._build_results_panel()
        self.results_dock = self._create_dock("结果数据", "results_dock", self.results_panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.results_dock)

        self._results_anim = QPropertyAnimation(self.results_panel, b"panelHeight", self)
        self._results_anim.setDuration(160)
        self._results_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._build_window_menu()
        self.sidebar_dock.visibilityChanged.connect(self._sync_dock_buttons)
        self.properties_dock.visibilityChanged.connect(self._sync_dock_buttons)
        self.results_dock.visibilityChanged.connect(self._sync_dock_buttons)
        self.resizeDocks([self.sidebar_dock, self.properties_dock], [METRICS["sidebar_w"], METRICS["props_w"]], Qt.Horizontal)
        self.resizeDocks([self.results_dock], [METRICS["results_h"]], Qt.Vertical)
        self._sync_dock_buttons()

    def _create_dock(self, title: str, name: str, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )
        return dock

    def _build_window_menu(self) -> None:
        sidebar_action = self.sidebar_dock.toggleViewAction()
        properties_action = self.properties_dock.toggleViewAction()
        results_action = self.results_dock.toggleViewAction()
        menu = self.menuBar().addMenu("窗口")
        menu.addAction(sidebar_action)
        menu.addAction(properties_action)
        menu.addAction(results_action)
        detail_action = menu.addAction("详细信息")
        detail_action.triggered.connect(self._show_detail_window)

        panels_menu = QMenu(self)
        panels_menu.addAction(sidebar_action)
        panels_menu.addAction(properties_action)
        panels_menu.addAction(results_action)
        self.panels_button.setMenu(panels_menu)

    def _sync_dock_buttons(self) -> None:
        if hasattr(self, "results_toggle"):
            self.results_toggle.setText("Hide Results" if self.results_dock.isVisible() else "Show Results")
            return
            self.results_toggle.setText("隐藏结果区" if self.results_dock.isVisible() else "显示结果区")

    def _build_sidebar(self) -> None:
        self._build_sidebar_compact()
        return
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        tools_group = QGroupBox("工具")
        tools_layout = QVBoxLayout(tools_group)
        tools_layout.setSpacing(6)
        self.tool_buttons: dict[str, QToolButton] = {}
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        for key, label in TOOL_LABELS.items():
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            if key == self.editor_tool:
                button.setChecked(True)
            self.tool_group.addButton(button)
            self.tool_buttons[key] = button
            tools_layout.addWidget(button)
        layout.addWidget(tools_group)

        self.tool_hint = QLabel("先选择工具，再在画布上操作。")
        self.tool_hint.setObjectName("Hint")
        self.tool_hint.setWordWrap(True)
        layout.addWidget(self.tool_hint)

        defaults_group = QGroupBox("默认构件参数")
        defaults_form = QFormLayout(defaults_group)
        defaults_form.setContentsMargins(10, 12, 10, 10)
        defaults_form.setSpacing(10)
        self.default_e = QLineEdit("2.06e11")
        self.default_a = QLineEdit("0.02")
        self.default_i = QLineEdit("8.5e-5")
        defaults_form.addRow("E", self.default_e)
        defaults_form.addRow("A", self.default_a)
        defaults_form.addRow("I", self.default_i)
        layout.addWidget(defaults_group)

        node_tool_group = QGroupBox("节点 / 集中力默认值")
        node_form = QFormLayout(node_tool_group)
        node_form.setContentsMargins(10, 12, 10, 10)
        node_form.setSpacing(10)
        self.new_node_role = QComboBox()
        self.new_node_role.addItems(["structural", "reference", "hinge"])
        self.new_node_kind = QComboBox()
        self.new_node_kind.addItems(["free", "fixed", "hinged", "roller_y"])
        self.support_kind = QComboBox()
        self.support_kind.addItems(["fixed", "hinged", "roller_x", "roller_y"])
        self.node_force = QLineEdit("10")
        self.node_angle = QLineEdit("-90")
        self.node_moment = QLineEdit("10")
        node_form.addRow("新节点角色", self.new_node_role)
        node_form.addRow("新节点支座", self.new_node_kind)
        node_form.addRow("支座预设", self.support_kind)
        node_form.addRow("F", self.node_force)
        node_form.addRow("角度", self.node_angle)
        node_form.addRow("M", self.node_moment)
        layout.addWidget(node_tool_group)

        dist_group = QGroupBox("分布荷载默认值")
        dist_form = QFormLayout(dist_group)
        dist_form.setContentsMargins(10, 12, 10, 10)
        dist_form.setSpacing(10)
        self.dist_q = QLineEdit("-10")
        self.dist_dir = QComboBox()
        self.dist_dir.addItems(["element", "parallel", "x", "y"])
        dist_form.addRow("q", self.dist_q)
        dist_form.addRow("方向", self.dist_dir)
        layout.addWidget(dist_group)
        layout.addStretch(1)

    def _build_sidebar_compact(self) -> None:
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setObjectName("SidebarTabs")
        layout.addWidget(self.sidebar_tabs, 1)

        tools_tab = QWidget()
        tools_tab_layout = QVBoxLayout(tools_tab)
        tools_tab_layout.setContentsMargins(0, 8, 0, 0)
        tools_tab_layout.setSpacing(12)

        tools_group = QGroupBox("\u5de5\u5177")
        tools_layout = QVBoxLayout(tools_group)
        tools_layout.setContentsMargins(10, 14, 10, 10)
        tools_layout.setSpacing(8)
        self.tool_buttons = {}
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        for key, label in TOOL_LABELS.items():
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setMinimumHeight(40)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            if key == self.editor_tool:
                button.setChecked(True)
            self.tool_group.addButton(button)
            self.tool_buttons[key] = button
            tools_layout.addWidget(button)
        tools_tab_layout.addWidget(tools_group)

        self.tool_hint = QLabel("\u5148\u9009\u62e9\u5de5\u5177\uff0c\u518d\u5728\u753b\u5e03\u4e0a\u64cd\u4f5c\u3002")
        self.tool_hint.setObjectName("Hint")
        self.tool_hint.setWordWrap(True)
        tools_tab_layout.addWidget(self.tool_hint)
        tools_tab_layout.addStretch(1)
        self.sidebar_tabs.addTab(tools_tab, "\u5de5\u5177")

        defaults_scroll = QScrollArea()
        defaults_scroll.setWidgetResizable(True)
        defaults_scroll.setFrameShape(QFrame.NoFrame)
        defaults_container = QWidget()
        defaults_layout = QVBoxLayout(defaults_container)
        defaults_layout.setContentsMargins(0, 8, 0, 0)
        defaults_layout.setSpacing(12)

        defaults_group = QGroupBox("\u9ed8\u8ba4\u6784\u4ef6\u53c2\u6570")
        defaults_form = QFormLayout(defaults_group)
        defaults_form.setContentsMargins(10, 12, 10, 10)
        defaults_form.setSpacing(10)
        self.default_e = QLineEdit("2.06e11")
        self.default_a = QLineEdit("0.02")
        self.default_i = QLineEdit("8.5e-5")
        defaults_form.addRow("E", self.default_e)
        defaults_form.addRow("A", self.default_a)
        defaults_form.addRow("I", self.default_i)
        defaults_layout.addWidget(defaults_group)

        node_tool_group = QGroupBox("\u8282\u70b9 / \u96c6\u4e2d\u529b\u9ed8\u8ba4\u503c")
        node_form = QFormLayout(node_tool_group)
        node_form.setContentsMargins(10, 12, 10, 10)
        node_form.setSpacing(10)
        self.new_node_role = QComboBox()
        self.new_node_role.addItems(["structural", "reference", "hinge"])
        self.new_node_kind = QComboBox()
        self.new_node_kind.addItems(["free", "fixed", "hinged", "roller_y"])
        self.support_kind = QComboBox()
        self.support_kind.addItems(["fixed", "hinged", "roller_x", "roller_y"])
        self.node_force = QLineEdit("10")
        self.node_angle = QLineEdit("-90")
        self.node_moment = QLineEdit("10")
        node_form.addRow("\u65b0\u8282\u70b9\u89d2\u8272", self.new_node_role)
        node_form.addRow("\u65b0\u8282\u70b9\u652f\u5ea7", self.new_node_kind)
        node_form.addRow("\u652f\u5ea7\u9884\u8bbe", self.support_kind)
        node_form.addRow("F", self.node_force)
        node_form.addRow("\u89d2\u5ea6", self.node_angle)
        node_form.addRow("M", self.node_moment)
        defaults_layout.addWidget(node_tool_group)

        dist_group = QGroupBox("\u5206\u5e03\u8377\u8f7d\u9ed8\u8ba4\u503c")
        dist_form = QFormLayout(dist_group)
        dist_form.setContentsMargins(10, 12, 10, 10)
        dist_form.setSpacing(10)
        self.dist_q = QLineEdit("-10")
        self.dist_dir = QComboBox()
        self.dist_dir.addItems(["element", "parallel", "x", "y"])
        dist_form.addRow("q", self.dist_q)
        dist_form.addRow("\u65b9\u5411", self.dist_dir)
        defaults_layout.addWidget(dist_group)
        defaults_layout.addStretch(1)

        defaults_scroll.setWidget(defaults_container)
        self.sidebar_tabs.addTab(defaults_scroll, "\u9ed8\u8ba4\u503c")

    def _build_properties(self) -> None:
        layout = QVBoxLayout(self.properties)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        summary_title = QLabel("结果摘要")
        summary_title.setObjectName("PanelTitle")
        layout.addWidget(summary_title)

        summary_grid = QGridLayout()
        summary_grid.setSpacing(10)
        self.metric_cards: dict[str, MetricCard] = {}
        items = [
            ("max_displacement", "最大位移"),
            ("max_axial", "最大轴力"),
            ("max_shear", "最大剪力"),
            ("max_moment", "最大弯矩"),
        ]
        for idx, (key, label) in enumerate(items):
            card = FadeFrame("Card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(4)
            title = QLabel(label)
            title.setObjectName("MetricLabel")
            value = QLabel("--")
            value.setObjectName("MetricValue")
            card_layout.addWidget(title)
            card_layout.addWidget(value)
            summary_grid.addWidget(card, idx // 2, idx % 2)
            self.metric_cards[key] = MetricCard(title=title, value=value)
        layout.addLayout(summary_grid)

        current_title = QLabel("当前对象")
        current_title.setObjectName("PanelTitle")
        layout.addWidget(current_title)
        self.selection_title = QLabel("未选中对象")
        self.selection_title.setObjectName("StatusMuted")
        layout.addWidget(self.selection_title)

        self.property_stack = QStackedWidget()
        layout.addWidget(self.property_stack, 1)
        self.property_stack.setGraphicsEffect(QGraphicsOpacityEffect(self.property_stack))
        self._property_anim = QPropertyAnimation(self.property_stack.graphicsEffect(), b"opacity", self)
        self._property_anim.setDuration(140)
        self._property_anim.setStartValue(0.0)
        self._property_anim.setEndValue(1.0)

        self.empty_page = self._build_empty_property_page()
        self.node_page = self._build_node_property_page()
        self.element_page = self._build_element_property_page()
        self.node_load_page = self._build_node_load_property_page()
        self.dist_load_page = self._build_dist_load_property_page()

        for page in (self.empty_page, self.node_page, self.element_page, self.node_load_page, self.dist_load_page):
            self.property_stack.addWidget(page)

    def _build_results_panel(self) -> None:
        layout = QVBoxLayout(self.results_panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("结果数据")
        title.setObjectName("PanelTitle")
        hint = QLabel("计算完成后会显示节点和单元结果。")
        hint.setObjectName("SectionHint")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(hint)
        layout.addLayout(header)

        self.result_switch = QComboBox()
        self.result_switch.addItems(["节点结果", "单元结果"])
        layout.addWidget(self.result_switch, 0, Qt.AlignLeft)

        self.result_pages = QStackedWidget()
        self.node_table = self._make_table(["节点", "ux", "uy", "phi", "Rx", "Ry", "Rm"])
        self.element_table = self._make_table(["单元", "长度", "Nmin", "Nmax", "Qmin", "Qmax", "Mmin", "Mmax"])
        self.result_pages.addWidget(self.node_table)
        self.result_pages.addWidget(self.element_table)
        layout.addWidget(self.result_pages, 1)

    def _make_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.horizontalHeader().setHighlightSections(False)
        return table

    def _build_empty_property_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("DetailPanel")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        label = QLabel("在画布上选择节点、杆件或荷载后，这里会显示对应参数。")
        label.setObjectName("Hint")
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return page

    def _build_node_property_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("DetailPanel")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        form = QFormLayout()
        form.setSpacing(10)
        self.node_x_edit = QLineEdit()
        self.node_y_edit = QLineEdit()
        self.node_role_combo = QComboBox()
        self.node_role_combo.addItems(["structural", "reference", "hinge"])
        self.node_support_combo = QComboBox()
        self.node_support_combo.addItems(["free", "fixed", "hinged", "roller_y"])
        self.node_force_edit = QLineEdit()
        self.node_angle_edit = QLineEdit()
        self.node_moment_edit = QLineEdit()
        form.addRow("X", self.node_x_edit)
        form.addRow("Y", self.node_y_edit)
        form.addRow("角色", self.node_role_combo)
        form.addRow("支座", self.node_support_combo)
        form.addRow("F", self.node_force_edit)
        form.addRow("角度", self.node_angle_edit)
        form.addRow("M", self.node_moment_edit)
        layout.addLayout(form)
        self.apply_node_button = QPushButton("应用节点详情")
        layout.addWidget(self.apply_node_button)
        layout.addStretch(1)
        return page

    def _build_element_property_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("DetailPanel")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        form = QFormLayout()
        form.setSpacing(10)
        self.element_e_edit = QLineEdit()
        self.element_a_edit = QLineEdit()
        self.element_i_edit = QLineEdit()
        self.element_q_edit = QLineEdit()
        self.element_dir_combo = QComboBox()
        self.element_dir_combo.addItems(["element", "parallel", "x", "y"])
        form.addRow("E", self.element_e_edit)
        form.addRow("A", self.element_a_edit)
        form.addRow("I", self.element_i_edit)
        form.addRow("q", self.element_q_edit)
        form.addRow("方向", self.element_dir_combo)
        layout.addLayout(form)
        self.apply_element_button = QPushButton("应用杆件详情")
        layout.addWidget(self.apply_element_button)
        layout.addStretch(1)
        return page

    def _build_node_load_property_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("DetailPanel")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        form = QFormLayout()
        form.setSpacing(10)
        self.selected_force_edit = QLineEdit()
        self.selected_angle_edit = QLineEdit()
        self.selected_moment_edit = QLineEdit()
        form.addRow("F", self.selected_force_edit)
        form.addRow("角度", self.selected_angle_edit)
        form.addRow("M", self.selected_moment_edit)
        layout.addLayout(form)
        self.apply_node_load_button = QPushButton("应用荷载详情")
        layout.addWidget(self.apply_node_load_button)
        layout.addStretch(1)
        return page

    def _build_dist_load_property_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("DetailPanel")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        form = QFormLayout()
        form.setSpacing(10)
        self.selected_dist_q_edit = QLineEdit()
        self.selected_dist_dir_combo = QComboBox()
        self.selected_dist_dir_combo.addItems(["element", "parallel", "x", "y"])
        form.addRow("q", self.selected_dist_q_edit)
        form.addRow("方向", self.selected_dist_dir_combo)
        layout.addLayout(form)
        self.apply_dist_load_button = QPushButton("应用荷载详情")
        layout.addWidget(self.apply_dist_load_button)
        layout.addStretch(1)
        return page

    def _connect_signals(self) -> None:
        self.demo_button.clicked.connect(self._load_demo_model)
        self.solve_button.clicked.connect(self._solve)
        self.clear_button.clicked.connect(self._clear_all)
        self.detail_button.clicked.connect(self._show_detail_window)
        self.results_toggle.clicked.connect(self._toggle_results_panel)
        self.view_combo.currentTextChanged.connect(self._on_view_changed)
        self.result_switch.currentIndexChanged.connect(self.result_pages.setCurrentIndex)

        for key, button in self.tool_buttons.items():
            button.clicked.connect(lambda checked=False, tool=key: self._on_tool_changed(tool))

        self.apply_node_button.clicked.connect(self._apply_node_properties)
        self.apply_element_button.clicked.connect(self._apply_element_properties)
        self.apply_node_load_button.clicked.connect(self._apply_node_load_properties)
        self.apply_dist_load_button.clicked.connect(self._apply_dist_load_properties)

        self.canvas.clicked.connect(self._on_canvas_click)
        self.canvas.moved.connect(self._on_canvas_move)
        self.canvas.dragged.connect(self._on_canvas_drag)
        self.canvas.released.connect(self._on_canvas_release)
        self.canvas.left_canvas.connect(self._on_canvas_leave)

    def _load_demo_model(self) -> None:
        self.model = StructureModel(
            nodes=[
                NodeSpec("N1", 0.0, 0.0),
                NodeSpec("N2", 6.0, 0.0),
                NodeSpec("N3", 0.0, 4.0),
                NodeSpec("N4", 6.0, 4.0),
            ],
            elements=[
                ElementSpec("E1", "N1", "N3", 2.06e11, 0.02, 8.5e-5),
                ElementSpec("E2", "N3", "N4", 2.06e11, 0.02, 8.5e-5),
                ElementSpec("E3", "N4", "N2", 2.06e11, 0.02, 8.5e-5),
            ],
            supports=[SupportSpec("N1", "fixed"), SupportSpec("N2", "fixed")],
            node_loads=[NodeLoadSpec("N4", 0.0, -40.0, 0.0)],
            distributed_loads=[DistributedLoadSpec(q=-18.0, element="E2", direction="element")],
        )
        self.result = None
        self.selected_node = None
        self.selected_element = None
        self.selected_node_load = None
        self.selected_dist_load = None
        self.pending_element_start = None
        self.pending_dist_load_start = None
        self.dragging_node = None
        self._update_summary()
        self._update_selection_panel()
        self._update_results_tables()
        self._update_info_panel()
        self.canvas.update()
        self._set_status("已加载示例模型。")

    def _clear_all(self) -> None:
        self.model = StructureModel()
        self.result = None
        self.selected_node = None
        self.selected_element = None
        self.selected_node_load = None
        self.selected_dist_load = None
        self.pending_element_start = None
        self.pending_dist_load_start = None
        self.dragging_node = None
        self._update_summary()
        self._update_selection_panel()
        self._update_results_tables()
        self._update_info_panel()
        self.canvas.update()
        self._set_status("已清空模型，请先放置节点。")

    def _solve(self) -> None:
        if len(self.model.nodes) < 2 or not self.model.elements:
            QMessageBox.warning(self, "无法计算", "请至少创建两个节点和一个杆件。")
            return
        try:
            self.result = solve_structure(self.model)
        except SolveError as exc:
            QMessageBox.critical(self, "计算失败", str(exc))
            return
        self._update_summary()
        self._update_results_tables()
        self._update_info_panel()
        self.canvas.update()
        self.results_panel.fade_in()
        self._set_status("计算完成，可以切换视图查看结果。")

    def _show_detail_window(self) -> None:
        self._update_info_panel()
        self.detail_window.show()
        self.detail_window.raise_()
        self.detail_window.activateWindow()

    def _toggle_results_panel(self) -> None:
        if hasattr(self, "results_dock"):
            self.results_dock.setVisible(not self.results_dock.isVisible())
            self._sync_dock_buttons()
            return
        expanded = self.results_panel.maximumHeight() > 0
        start = self.results_panel.maximumHeight()
        end = 0 if expanded else METRICS["results_h"]
        self._results_anim.stop()
        self._results_anim.setStartValue(start)
        self._results_anim.setEndValue(end)
        self._results_anim.start()
        self.results_toggle.setText("展开结果" if expanded else "收起结果")

    def _on_view_changed(self, text: str) -> None:
        for key, label in VIEW_LABELS.items():
            if label == text:
                self.view_mode = key
                break
        self.canvas.update()

    def _on_tool_changed(self, tool: str) -> None:
        self.editor_tool = tool
        for key, button in self.tool_buttons.items():
            if key != tool:
                button.setChecked(False)
        hints = {
            "select": "拖拽节点即可修改结构，点击对象后可在右侧编辑。",
            "add_node": "点击空白区域放置节点，节点会自动吸附到整数坐标。",
            "add_element": "先点起点，再点终点，即可创建杆件。",
            "add_support": "点击同一节点可在自由、固定、铰接、滚支之间循环切换。",
            "add_node_load": "点击节点即可添加节点荷载。",
            "add_moment_load": "点击节点即可添加集中力偶。",
            "add_dist_load": "先点起点节点，再点终点节点，按整跨施加分布荷载。",
            "delete": "点击节点或杆件即可删除。",
        }
        self.pending_element_start = None
        self.pending_dist_load_start = None
        self.selected_node_load = None
        self.selected_dist_load = None
        self.tool_hint.setText(hints.get(tool, "请在画布上操作。"))
        self._set_status(hints.get(tool, "请在画布上操作。"))
        self._update_selection_panel()
        self._update_info_panel()
        self.canvas.update()

    def _on_canvas_click(self, point: QPointF) -> None:
        x = point.x()
        y = point.y()
        node = self._find_nearest_node(x, y)
        element = self._find_nearest_element(x, y)
        node_load = self._find_nearest_node_load(x, y)
        dist_load = self._find_nearest_dist_load(x, y)

        try:
            if self.editor_tool == "select":
                self.selected_node_load = None
                self.selected_dist_load = None
                if node_load is not None:
                    self.selected_node = None
                    self.selected_element = None
                    self.selected_node_load = node_load
                    self.dragging_node = None
                elif dist_load is not None:
                    self.selected_node = None
                    self.selected_element = None
                    self.selected_dist_load = dist_load
                    self.dragging_node = None
                else:
                    self.selected_node = node
                    self.selected_element = None if node else element
                    self.dragging_node = node
                self._update_selection_panel()
                self._update_info_panel()
                self.canvas.update()
                return

            if self.editor_tool == "add_node":
                if node is None:
                    self._add_node_at_canvas(x, y)
                return

            if self.editor_tool == "add_element":
                if node is None:
                    self._set_status("请先点击节点作为杆件端点。")
                    return
                if self.pending_element_start is None:
                    self.pending_element_start = node
                    self.selected_node = node
                    self.selected_element = None
                    self._set_status("已选择起点，请再点击一个节点完成杆件。")
                else:
                    if node == self.pending_element_start:
                        self._set_status("终点不能与起点相同。")
                    else:
                        self._add_element(self.pending_element_start, node)
                        self.pending_element_start = None
                self._update_selection_panel()
                self._update_info_panel()
                self.canvas.update()
                return

            if self.editor_tool == "add_support":
                if node is None:
                    self._set_status("请点击一个节点施加支座。")
                    return
                self._cycle_support(node)
                return

            if self.editor_tool == "add_node_load":
                if node is None:
                    self._set_status("请点击一个节点施加节点荷载。")
                    return
                self._set_node_load(node)
                return

            if self.editor_tool == "add_moment_load":
                if node is None:
                    self._set_status("请点击一个节点施加集中力偶。")
                    return
                self._set_node_moment(node)
                return

            if self.editor_tool == "add_dist_load":
                if node is None:
                    self._set_status("分布荷载请通过两个节点选取：先点起点，再点终点。")
                    return
                if self.pending_dist_load_start is None:
                    self.pending_dist_load_start = node
                    self.selected_node = node
                    self.selected_element = None
                    self._update_selection_panel()
                    self._update_info_panel()
                    self._set_status("已选择分布荷载起点，请再点击终点节点。")
                else:
                    if node == self.pending_dist_load_start:
                        self._set_status("终点不能与起点相同。")
                    else:
                        self._set_distributed_load_between_nodes(self.pending_dist_load_start, node)
                        self.pending_dist_load_start = None
                self.canvas.update()
                return

            if self.editor_tool == "delete":
                if node:
                    self._delete_node(node)
                elif element:
                    self._delete_element(element)
        except SolveError as exc:
            QMessageBox.critical(self, "输入错误", str(exc))

    def _on_canvas_move(self, point: QPointF) -> None:
        x, y = self._canvas_to_world(point.x(), point.y())
        sx = self._snap_value(x)
        sy = self._snap_value(y)
        self.hover_world_point = (sx, sy)
        if self.editor_tool == "add_node":
            self._set_status(f"即将吸附到整数点 ({int(sx)}, {int(sy)})")
        self.canvas.update()

    def _on_canvas_drag(self, point: QPointF) -> None:
        if self.editor_tool != "select" or self.dragging_node is None:
            self._on_canvas_move(point)
            return
        node = self._get_node(self.dragging_node)
        if node is None:
            return
        x, y = self._canvas_to_world(point.x(), point.y())
        node.x = self._snap_value(x)
        node.y = self._snap_value(y)
        self.result = None
        self._update_selection_panel()
        self._update_summary()
        self._update_results_tables()
        self._update_info_panel()
        self.canvas.update()

    def _on_canvas_release(self) -> None:
        self.dragging_node = None

    def _on_canvas_leave(self) -> None:
        self.hover_world_point = None
        self.canvas.update()

    def _add_node_at_canvas(self, canvas_x: float, canvas_y: float) -> None:
        x, y = self._canvas_to_world(canvas_x, canvas_y)
        x = self._snap_value(x)
        y = self._snap_value(y)
        existing = next((item for item in self.model.nodes if abs(item.x - x) < 1e-9 and abs(item.y - y) < 1e-9), None)
        if existing is not None:
            self.selected_node = existing.name
            self.selected_element = None
            self.selected_node_load = None
            self.selected_dist_load = None
            self._update_selection_panel()
            self._update_info_panel()
            self.canvas.update()
            self._set_status(f"该位置已存在节点 {existing.name}")
            return
        name = f"N{len(self.model.nodes) + 1}"
        self.model.nodes.append(NodeSpec(name, x, y, role=self.new_node_role.currentText()))
        self._apply_new_node_support(name)
        self.result = None
        self.selected_node = name
        self.selected_element = None
        self.selected_node_load = None
        self.selected_dist_load = None
        self._update_selection_panel()
        self._update_summary()
        self._update_results_tables()
        self._update_info_panel()
        self.canvas.update()
        self._set_status(f"已放置节点 {name}")

    def _add_element(self, start: str, end: str) -> None:
        if self._find_element_between(start, end) is not None:
            self._set_status("这两个节点之间已经存在杆件。")
            return
        name = f"E{len(self.model.elements) + 1}"
        self.model.elements.append(
            ElementSpec(
                name=name,
                start=start,
                end=end,
                e=self._parse_float(self.default_e, "E"),
                a=self._parse_float(self.default_a, "A"),
                i=self._parse_float(self.default_i, "I"),
            )
        )
        self.result = None
        self.selected_node = None
        self.selected_element = name
        self.selected_node_load = None
        self.selected_dist_load = None
        self._update_selection_panel()
        self._update_summary()
        self._update_results_tables()
        self._update_info_panel()
        self.canvas.update()
        self._set_status(f"已创建杆件 {name}")

    def _cycle_support(self, node_name: str) -> None:
        cycle = [None, "fixed", "hinged", "roller_y"]
        current = self._get_support_kind(node_name)
        try:
            index = cycle.index(current)
        except ValueError:
            index = 0
        next_kind = cycle[(index + 1) % len(cycle)]
        self.model.supports = [item for item in self.model.supports if item.node != node_name]
        if next_kind is not None:
            self.model.supports.append(SupportSpec(node_name, next_kind))
        self.result = None
        self.selected_node = node_name
        self.selected_element = None
        self.selected_node_load = None
        self.selected_dist_load = None
        self._update_selection_panel()
        self._update_info_panel()
        self.canvas.update()
        self._set_status(f"节点 {node_name} 已切换为 {self._support_label(next_kind)}")

    def _set_node_load(self, node_name: str) -> None:
        fx, fy = self._force_components_from_widgets(self.node_force, self.node_angle)
        moment = self._parse_float(self.node_moment, "M")
        self.model.node_loads = [item for item in self.model.node_loads if item.node != node_name]
        self.model.node_loads.append(NodeLoadSpec(node_name, fx, fy, moment))
        self.result = None
        self.selected_node = node_name
        self.selected_element = None
        self.selected_node_load = node_name
        self.selected_dist_load = None
        self._update_selection_panel()
        self._update_info_panel()
        self.canvas.update()
        self._set_status("已施加节点荷载。")

    def _set_node_moment(self, node_name: str) -> None:
        moment = self._parse_float(self.node_moment, "M")
        existing = next((item for item in self.model.node_loads if item.node == node_name), None)
        fx = existing.fx if existing else 0.0
        fy = existing.fy if existing else 0.0
        if abs(moment) <= 1e-12 and abs(fx) <= 1e-12 and abs(fy) <= 1e-12:
            self._set_status("当前 M 为 0，请先输入非零集中力偶。")
            return
        self.model.node_loads = [item for item in self.model.node_loads if item.node != node_name]
        if any(abs(v) > 1e-12 for v in (fx, fy, moment)):
            self.model.node_loads.append(NodeLoadSpec(node_name, fx, fy, moment))
        self.result = None
        self.selected_node = node_name
        self.selected_element = None
        self.selected_node_load = node_name
        self.selected_dist_load = None
        self._update_selection_panel()
        self._update_info_panel()
        self.canvas.update()
        self._set_status("已施加集中力偶。")

    def _set_distributed_load_between_nodes(self, start_node: str, end_node: str) -> None:
        q = self._parse_float(self.dist_q, "q")
        direction = self.dist_dir.currentText()
        self.model.distributed_loads = [
            item
            for item in self.model.distributed_loads
            if not (item.start_node == start_node and item.end_node == end_node)
            and not (item.start_node == end_node and item.end_node == start_node)
        ]
        self.model.distributed_loads.append(DistributedLoadSpec(q=q, direction=direction, start_node=start_node, end_node=end_node))
        self.result = None
        self.selected_node = None
        self.selected_element = None
        self.selected_node_load = None
        self.selected_dist_load = self._dist_load_key(self.model.distributed_loads[-1])
        self._update_selection_panel()
        self._update_info_panel()
        self.canvas.update()
        self._set_status("已按起止节点施加整跨分布荷载。")

    def _delete_node(self, node_name: str) -> None:
        self.model.nodes = [item for item in self.model.nodes if item.name != node_name]
        removed = {item.name for item in self.model.elements if item.start == node_name or item.end == node_name}
        self.model.elements = [item for item in self.model.elements if item.name not in removed]
        self.model.supports = [item for item in self.model.supports if item.node != node_name]
        self.model.node_loads = [item for item in self.model.node_loads if item.node != node_name]
        self.model.distributed_loads = [
            item
            for item in self.model.distributed_loads
            if item.element not in removed and item.start_node != node_name and item.end_node != node_name
        ]
        self.result = None
        self.selected_node = None
        self.selected_element = None
        self.selected_node_load = None
        self.selected_dist_load = None
        self.pending_element_start = None
        self._update_selection_panel()
        self._update_summary()
        self._update_results_tables()
        self._update_info_panel()
        self.canvas.update()
        self._set_status(f"已删除节点 {node_name}")

    def _delete_element(self, element_name: str) -> None:
        self.model.elements = [item for item in self.model.elements if item.name != element_name]
        self.model.distributed_loads = [item for item in self.model.distributed_loads if item.element != element_name]
        self.result = None
        self.selected_node = None
        self.selected_element = None
        self.selected_node_load = None
        self.selected_dist_load = None
        self._update_selection_panel()
        self._update_summary()
        self._update_results_tables()
        self._update_info_panel()
        self.canvas.update()
        self._set_status(f"已删除杆件 {element_name}")

    def _apply_node_properties(self) -> None:
        try:
            if self.selected_node is None:
                return
            node = self._get_node(self.selected_node)
            if node is None:
                return
            node.x = self._snap_value(self._parse_float(self.node_x_edit, "X"))
            node.y = self._snap_value(self._parse_float(self.node_y_edit, "Y"))
            node.role = self.node_role_combo.currentText()
            self.model.supports = [item for item in self.model.supports if item.node != node.name]
            if self.node_support_combo.currentText() != "free":
                self.model.supports.append(SupportSpec(node.name, self.node_support_combo.currentText()))
            self.model.node_loads = [item for item in self.model.node_loads if item.node != node.name]
            fx, fy = self._force_components_from_widgets(self.node_force_edit, self.node_angle_edit)
            moment = self._parse_float(self.node_moment_edit, "M")
            if any(abs(v) > 1e-12 for v in (fx, fy, moment)):
                self.model.node_loads.append(NodeLoadSpec(node.name, fx, fy, moment))
            self.result = None
            self._update_selection_panel()
            self._update_summary()
            self._update_results_tables()
            self._update_info_panel()
            self.canvas.update()
        except SolveError as exc:
            QMessageBox.critical(self, "输入错误", str(exc))

    def _apply_element_properties(self) -> None:
        try:
            if self.selected_element is None:
                return
            element = self._get_element(self.selected_element)
            if element is None:
                return
            element.e = self._parse_float(self.element_e_edit, "E")
            element.a = self._parse_float(self.element_a_edit, "A")
            element.i = self._parse_float(self.element_i_edit, "I")
            self.model.distributed_loads = [item for item in self.model.distributed_loads if item.element != element.name]
            q = self._parse_float(self.element_q_edit, "q")
            if abs(q) > 1e-12:
                self.model.distributed_loads.append(DistributedLoadSpec(q=q, element=element.name, direction=self.element_dir_combo.currentText()))
            self.result = None
            self._update_summary()
            self._update_results_tables()
            self._update_info_panel()
            self.canvas.update()
        except SolveError as exc:
            QMessageBox.critical(self, "输入错误", str(exc))

    def _apply_node_load_properties(self) -> None:
        try:
            if self.selected_node_load is None:
                return
            fx, fy = self._force_components_from_widgets(self.selected_force_edit, self.selected_angle_edit)
            moment = self._parse_float(self.selected_moment_edit, "M")
            self.model.node_loads = [item for item in self.model.node_loads if item.node != self.selected_node_load]
            if any(abs(v) > 1e-12 for v in (fx, fy, moment)):
                self.model.node_loads.append(NodeLoadSpec(self.selected_node_load, fx, fy, moment))
            self.result = None
            self._update_selection_panel()
            self._update_info_panel()
            self.canvas.update()
        except SolveError as exc:
            QMessageBox.critical(self, "输入错误", str(exc))

    def _apply_dist_load_properties(self) -> None:
        try:
            if self.selected_dist_load is None:
                return
            target = self._get_dist_load_by_key(self.selected_dist_load)
            if target is None:
                return
            target.q = self._parse_float(self.selected_dist_q_edit, "q")
            target.direction = self.selected_dist_dir_combo.currentText()
            self.result = None
            self._update_selection_panel()
            self._update_info_panel()
            self.canvas.update()
        except SolveError as exc:
            QMessageBox.critical(self, "输入错误", str(exc))

    def _update_selection_panel(self) -> None:
        self._clear_error_states()
        if self.selected_node_load:
            load = next((item for item in self.model.node_loads if item.node == self.selected_node_load), None)
            if load is not None:
                magnitude, angle = self._force_polar(load.fx, load.fy)
                self.selection_title.setText(f"节点荷载 {load.node}")
                self.selected_force_edit.setText(self._fmt(magnitude))
                self.selected_angle_edit.setText(self._fmt(angle))
                self.selected_moment_edit.setText(self._fmt(load.moment))
                self.property_stack.setCurrentWidget(self.node_load_page)
                self._fade_properties()
                return

        if self.selected_dist_load:
            load = self._get_dist_load_by_key(self.selected_dist_load)
            if load is not None:
                self.selection_title.setText(f"分布荷载 {self._dist_load_label(load)}")
                self.selected_dist_q_edit.setText(self._fmt(load.q))
                self.selected_dist_dir_combo.setCurrentText(load.direction)
                self.property_stack.setCurrentWidget(self.dist_load_page)
                self._fade_properties()
                return

        if self.selected_node:
            node = self._get_node(self.selected_node)
            if node is not None:
                self.selection_title.setText(f"节点 {node.name}")
                self.node_x_edit.setText(self._fmt(node.x))
                self.node_y_edit.setText(self._fmt(node.y))
                self.node_role_combo.setCurrentText(node.role)
                self.node_support_combo.setCurrentText(self._get_support_kind(node.name) or "free")
                load = next((item for item in self.model.node_loads if item.node == node.name), None)
                magnitude, angle = self._force_polar(load.fx, load.fy) if load else (0.0, 0.0)
                self.node_force_edit.setText(self._fmt(magnitude))
                self.node_angle_edit.setText(self._fmt(angle))
                self.node_moment_edit.setText(self._fmt(load.moment) if load else "0")
                self.property_stack.setCurrentWidget(self.node_page)
                self._fade_properties()
                return

        if self.selected_element:
            element = self._get_element(self.selected_element)
            if element is not None:
                self.selection_title.setText(f"杆件 {element.name}: {element.start} -> {element.end}")
                self.element_e_edit.setText(self._fmt(element.e))
                self.element_a_edit.setText(self._fmt(element.a))
                self.element_i_edit.setText(self._fmt(element.i))
                dist = next((item for item in self.model.distributed_loads if item.element == element.name), None)
                self.element_q_edit.setText(self._fmt(dist.q) if dist else "0")
                self.element_dir_combo.setCurrentText(dist.direction if dist else "element")
                self.property_stack.setCurrentWidget(self.element_page)
                self._fade_properties()
                return

        self.selection_title.setText("未选中对象")
        self.property_stack.setCurrentWidget(self.empty_page)
        self._fade_properties()

    def _update_summary(self) -> None:
        if self.result is None:
            for card in self.metric_cards.values():
                card.value.setText("--")
            return
        self.metric_cards["max_displacement"].value.setText(self._fmt(self.result.summary.max_displacement))
        self.metric_cards["max_axial"].value.setText(self._fmt(self.result.summary.max_axial))
        self.metric_cards["max_shear"].value.setText(self._fmt(self.result.summary.max_shear))
        self.metric_cards["max_moment"].value.setText(self._fmt(self.result.summary.max_moment))

    def _update_results_tables(self) -> None:
        self.node_table.setRowCount(0)
        self.element_table.setRowCount(0)
        if self.result is None:
            return
        for row in self.result.node_results:
            index = self.node_table.rowCount()
            self.node_table.insertRow(index)
            values = [row.name, row.ux, row.uy, row.phi, row.rx, row.ry, row.rm]
            for column, value in enumerate(values):
                self.node_table.setItem(index, column, QTableWidgetItem(value if isinstance(value, str) else self._fmt(value)))
        for row in self.result.element_results:
            index = self.element_table.rowCount()
            self.element_table.insertRow(index)
            values = [row.name, row.length, row.n_min, row.n_max, row.q_min, row.q_max, row.m_min, row.m_max]
            for column, value in enumerate(values):
                self.element_table.setItem(index, column, QTableWidgetItem(value if isinstance(value, str) else self._fmt(value)))
        self.results_panel.fade_in()

    def _update_info_panel(self) -> None:
        lines = [
            f"节点数: {len(self.model.nodes)}",
            f"杆件数: {len(self.model.elements)}",
            f"支座数: {len(self.model.supports)}",
            f"节点荷载数: {len(self.model.node_loads)}",
            f"分布荷载数: {len(self.model.distributed_loads)}",
            "",
            f"当前工具: {self.editor_tool}",
            f"新节点角色: {self.new_node_role.currentText()}",
            f"新节点支座: {self._support_label(self.new_node_kind.currentText())}",
            f"预设支座: {self._support_label(self.support_kind.currentText())}",
            f"预设节点荷载: F={self.node_force.text()}, angle={self.node_angle.text()}, M={self.node_moment.text()}",
            f"预设分布荷载: q={self.dist_q.text()}, dir={self.dist_dir.currentText()}",
        ]
        self.detail_window.refresh("\n".join(lines))

    def _fade_properties(self) -> None:
        effect = self.property_stack.graphicsEffect()
        if effect is None:
            return
        effect.setOpacity(0.0)
        self._property_anim.stop()
        self._property_anim.start()

    def _clear_error_states(self) -> None:
        widgets = [
            self.default_e,
            self.default_a,
            self.default_i,
            self.node_force,
            self.node_angle,
            self.node_moment,
            self.dist_q,
            self.node_x_edit,
            self.node_y_edit,
            self.node_force_edit,
            self.node_angle_edit,
            self.node_moment_edit,
            self.element_e_edit,
            self.element_a_edit,
            self.element_i_edit,
            self.element_q_edit,
            self.selected_force_edit,
            self.selected_angle_edit,
            self.selected_moment_edit,
            self.selected_dist_q_edit,
        ]
        for widget in widgets:
            self._set_error_state(widget, False)

    def _set_error_state(self, widget: QWidget, has_error: bool) -> None:
        widget.setProperty("error", has_error)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _parse_float(self, widget: QLineEdit, label: str) -> float:
        self._set_error_state(widget, False)
        try:
            return float(widget.text().strip())
        except ValueError as exc:
            self._set_error_state(widget, True)
            raise SolveError(f"{label} 不是有效数字。") from exc

    def _force_components_from_widgets(self, magnitude_widget: QLineEdit, angle_widget: QLineEdit) -> tuple[float, float]:
        magnitude = self._parse_float(magnitude_widget, "F")
        angle_deg = self._parse_float(angle_widget, "角度")
        angle_rad = math.radians(angle_deg)
        return magnitude * math.cos(angle_rad), magnitude * math.sin(angle_rad)

    def paint_canvas(self, painter: QPainter, rect) -> None:
        painter.fillRect(rect, _c("surface"))
        self._draw_grid(painter, rect)
        if self.result is not None and self.view_mode not in {"structure", "reaction"}:
            self._draw_result_diagram(painter, self.view_mode)
        for element in self.model.elements:
            self._draw_element(painter, element)
        self._draw_supports(painter)
        self._draw_loads(painter)
        if self.result is not None and self.view_mode == "reaction":
            self._draw_reactions(painter)
        for node in self.model.nodes:
            self._draw_node(painter, node)
        self._draw_pending_marker(painter)
        self._draw_hover_snap(painter)
        self._draw_canvas_badge(painter)

    def _draw_grid(self, painter: QPainter, rect) -> None:
        width = rect.width()
        height = rect.height()
        step = int(self.grid_pixels)
        origin_x = self.grid_margin
        origin_y = height - self.grid_margin
        start_ix = -int(origin_x // step) - 1
        end_ix = int((width - origin_x) // step) + 1
        start_iy = -int((height - origin_y) // step) - 1
        end_iy = int(origin_y // step) + 1
        small_pen = QPen(_c("border"), 1)
        axis_pen = QPen(_c("border_strong"), 1.5)
        painter.setFont(QFont("Consolas", 9))
        for ix in range(start_ix, end_ix + 1):
            x = origin_x + ix * step
            painter.setPen(axis_pen if ix == 0 else small_pen)
            painter.drawLine(QPointF(x, 0), QPointF(x, height))
            if 0 <= x <= width:
                painter.setPen(_c("text_soft"))
                painter.drawText(QPointF(x + 4, origin_y + 16), str(ix))
        for iy in range(start_iy, end_iy + 1):
            y = origin_y - iy * step
            painter.setPen(axis_pen if iy == 0 else small_pen)
            painter.drawLine(QPointF(0, y), QPointF(width, y))
            if 0 <= y <= height:
                painter.setPen(_c("text_soft"))
                painter.drawText(QPointF(origin_x - 28, y + 4), str(iy))

    def _draw_element(self, painter: QPainter, element: ElementSpec) -> None:
        start = self._get_node(element.start)
        end = self._get_node(element.end)
        if start is None or end is None:
            return
        p1 = QPointF(*self._world_to_canvas(start.x, start.y))
        p2 = QPointF(*self._world_to_canvas(end.x, end.y))
        color = _c("primary") if element.name == self.selected_element else _c("text")
        painter.setPen(_pen(QColor("#D7E0EA"), 5 if element.name == self.selected_element else 3, round_cap=True))
        painter.drawLine(p1, p2)
        painter.setPen(_pen(color, 3 if element.name == self.selected_element else 2, round_cap=True))
        painter.drawLine(p1, p2)
        painter.setPen(color)
        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        painter.drawText(QPointF((p1.x() + p2.x()) / 2 - 12, (p1.y() + p2.y()) / 2 - 12), element.name)

    def _draw_node(self, painter: QPainter, node: NodeSpec) -> None:
        x, y = self._world_to_canvas(node.x, node.y)
        center = QPointF(x, y)
        if node.role == "reference":
            outline = _c("text_muted")
            radius = 6
        else:
            outline = _c("text")
            radius = 7
        if node.name == self.selected_node:
            painter.setPen(QPen(_c("primary"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, 12, 12)
        painter.setPen(QPen(outline, 2.2))
        painter.setBrush(QColor("white"))
        painter.drawEllipse(center, radius, radius)
        if node.role == "hinge":
            painter.setBrush(outline)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(center, 2.5, 2.5)
        painter.setPen(outline if node.name != self.selected_node else _c("primary"))
        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        painter.drawText(QPointF(x + 12, y - 10), node.name)

    def _draw_supports(self, painter: QPainter) -> None:
        for support in self.model.supports:
            node = self._get_node(support.node)
            if node is None:
                continue
            x, y = self._world_to_canvas(node.x, node.y)
            if support.kind == "fixed":
                painter.setPen(QPen(_c("text_muted"), 2.5))
                painter.drawLine(QPointF(x - 16, y - 12), QPointF(x - 16, y + 20))
                painter.setPen(QPen(_c("text_muted"), 1.2))
                for oy in range(-10, 21, 6):
                    painter.drawLine(QPointF(x - 16, y + oy), QPointF(x - 4, y + oy + 5))
            elif support.kind == "hinged":
                self._draw_support_triangle(painter, x, y, rollers=False)
            elif support.kind == "roller_y":
                self._draw_support_triangle(painter, x, y, rollers=True)
            elif support.kind == "roller_x":
                self._draw_support_triangle_vertical(painter, x, y)

    def _draw_support_triangle(self, painter: QPainter, x: float, y: float, rollers: bool) -> None:
        path = QPainterPath()
        path.moveTo(x - 14, y + 18)
        path.lineTo(x + 14, y + 18)
        path.lineTo(x, y + 4)
        path.closeSubpath()
        painter.setBrush(QColor("white"))
        painter.setPen(QPen(_c("text_muted"), 1.8))
        painter.drawPath(path)
        if rollers:
            painter.drawEllipse(QPointF(x - 8, y + 23), 4, 4)
            painter.drawEllipse(QPointF(x + 8, y + 23), 4, 4)
            base_y = y + 31
        else:
            base_y = y + 23
        painter.drawLine(QPointF(x - 20, base_y), QPointF(x + 20, base_y))
        for dx in range(-18, 19, 8):
            painter.drawLine(QPointF(x + dx, base_y), QPointF(x + dx - 5, base_y + 5))

    def _draw_support_triangle_vertical(self, painter: QPainter, x: float, y: float) -> None:
        path = QPainterPath()
        path.moveTo(x - 14, y + 18)
        path.lineTo(x + 14, y + 18)
        path.lineTo(x, y + 4)
        path.closeSubpath()
        painter.setBrush(QColor("white"))
        painter.setPen(QPen(_c("text_muted"), 1.8))
        painter.drawPath(path)
        painter.drawEllipse(QPointF(x, y + 12), 4, 4)
        painter.drawEllipse(QPointF(x, y + 22), 4, 4)

    def _draw_loads(self, painter: QPainter) -> None:
        for load in self.model.node_loads:
            node = self._get_node(load.node)
            if node is None:
                continue
            x, y = self._world_to_canvas(node.x, node.y)
            color = _c("primary") if load.node == self.selected_node_load else _c("danger")
            magnitude, angle = self._force_polar(load.fx, load.fy)
            if magnitude > 1e-12:
                ax, ay = self._node_load_canvas_vector(load.fx, load.fy)
                self._draw_arrow(painter, QPointF(x + ax, y + ay), QPointF(x, y), color, 2.3)
                self._draw_badge(painter, QPointF(x + ax * 0.55 + 12, y + ay * 0.55 - 10), f"F={self._fmt(magnitude)} @ {self._fmt(angle)}°", color)
            if abs(load.moment) > 1e-12:
                self._draw_moment_symbol(painter, QPointF(x, y), load.moment, color)

        for load in self.model.distributed_loads:
            endpoints = self._dist_load_canvas_points(load)
            if endpoints is None:
                continue
            x1, y1, x2, y2 = endpoints
            color = _c("primary") if self.selected_dist_load == self._dist_load_key(load) else _c("danger")
            ox, oy = self._dist_load_offset(load, x1, y1, x2, y2)
            p1 = QPointF(x1 + ox, y1 + oy)
            p2 = QPointF(x2 + ox, y2 + oy)
            painter.setPen(QPen(_c("danger_soft"), 4))
            painter.drawLine(p1, p2)
            painter.setPen(QPen(color, 1.2))
            painter.drawLine(p1, p2)
            for factor in (0.16, 0.32, 0.48, 0.64, 0.80):
                px = x1 + (x2 - x1) * factor
                py = y1 + (y2 - y1) * factor
                sx = px + ox
                sy = py + oy
                self._draw_arrow(painter, QPointF(sx, sy), QPointF(px, py), color, 1.2)
            self._draw_badge(painter, QPointF((x1 + x2) / 2 + ox * 0.85, (y1 + y2) / 2 + oy * 0.85 - 12), f"q={self._fmt(load.q)}", color)

    def _draw_reactions(self, painter: QPainter) -> None:
        if self.result is None:
            return
        color = QColor("#B91C1C")
        for row in self.result.node_results:
            node = self._get_node(row.name)
            if node is None:
                continue
            x, y = self._world_to_canvas(node.x, node.y)
            if abs(row.rx) > 1e-9:
                dx = 30 if row.rx > 0 else -30
                self._draw_arrow(painter, QPointF(x, y + 28), QPointF(x + dx, y + 28), color, 1.6)
            if abs(row.ry) > 1e-9:
                dy = -30 if row.ry > 0 else 30
                self._draw_arrow(painter, QPointF(x - 28, y), QPointF(x - 28, y + dy), color, 1.6)

    def _draw_result_diagram(self, painter: QPainter, mode: str) -> None:
        if self.result is None:
            return
        getter_name = {
            "displacement": "displacements",
            "axial": "axial_force",
            "shear": "shear_force",
            "moment": "bending_moment",
        }.get(mode)
        if getter_name is None:
            return
        plotter = getattr(self.result.system, "plotter", None)
        if plotter is None:
            return
        plot_source = getattr(plotter, "plot_values", plotter)
        method = getattr(plot_source, getter_name, None)
        if method is None:
            return
        try:
            values = method(factor=None, linear=False) if mode == "displacement" else method(factor=None)
        except Exception:
            return
        if not values or len(values) < 2:
            return
        points = [QPointF(*self._world_to_canvas(float(x_val), float(y_val))) for x_val, y_val in zip(values[0], values[1])]
        if len(points) < 2:
            return
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        color = {
            "displacement": _c("success"),
            "axial": _c("warning"),
            "shear": _c("primary"),
            "moment": QColor("#7C3AED"),
        }[mode]
        painter.setPen(QPen(color, 2.4))
        painter.drawPath(path)

    def _draw_pending_marker(self, painter: QPainter) -> None:
        if not self.pending_element_start:
            return
        node = self._get_node(self.pending_element_start)
        if node is None:
            return
        x, y = self._world_to_canvas(node.x, node.y)
        painter.setPen(QPen(_c("primary"), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(x, y), 10, 10)

    def _draw_hover_snap(self, painter: QPainter) -> None:
        if self.hover_world_point is None or self.editor_tool not in {"add_node", "select"}:
            return
        x, y = self._world_to_canvas(*self.hover_world_point)
        painter.setPen(_pen(_c("success"), 1.4, dash=True))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(x, y), 6, 6)
        painter.drawLine(QPointF(x - 10, y), QPointF(x + 10, y))
        painter.drawLine(QPointF(x, y - 10), QPointF(x, y + 10))
        painter.setPen(_c("success"))
        painter.setFont(QFont("Consolas", 9, QFont.Bold))
        painter.drawText(QPointF(x + 10, y - 10), f"({int(self.hover_world_point[0])}, {int(self.hover_world_point[1])})")

    def _draw_canvas_badge(self, painter: QPainter) -> None:
        painter.setPen(QPen(_c("border"), 1))
        painter.setBrush(QColor("white"))
        rect = QRectF(16, 16, 250, 52)
        painter.drawRoundedRect(rect, 10, 10)
        painter.setPen(_c("text"))
        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        painter.drawText(QPointF(28, 38), f"工具: {TOOL_LABELS.get(self.editor_tool, self.editor_tool)}")
        painter.setPen(_c("text_muted"))
        painter.setFont(QFont("Microsoft YaHei UI", 10))
        painter.drawText(QPointF(28, 58), f"视图: {VIEW_LABELS.get(self.view_mode, self.view_mode)}")

    def _draw_arrow(self, painter: QPainter, start: QPointF, end: QPointF, color: QColor, width: float) -> None:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            return
        ux = dx / length
        uy = dy / length
        head_len = max(8.0, min(14.0, 6.0 + width * 2.0))
        head_w = max(6.0, min(10.0, 4.0 + width * 1.8))
        shaft_end = QPointF(end.x() - ux * head_len, end.y() - uy * head_len)
        nx = -uy
        ny = ux
        painter.setPen(_pen(color, width, round_cap=True))
        painter.drawLine(start, shaft_end)
        path = QPainterPath()
        path.moveTo(end)
        path.lineTo(shaft_end.x() + nx * head_w * 0.5, shaft_end.y() + ny * head_w * 0.5)
        path.lineTo(shaft_end.x() - nx * head_w * 0.5, shaft_end.y() - ny * head_w * 0.5)
        path.closeSubpath()
        painter.fillPath(path, color)

    def _draw_badge(self, painter: QPainter, origin: QPointF, text: str, color: QColor) -> None:
        metrics = painter.fontMetrics()
        width = max(56, metrics.horizontalAdvance(text) + 18)
        rect = QRectF(origin.x() - 8, origin.y() - 12, width, 22)
        painter.setPen(QPen(_c("border"), 1))
        painter.setBrush(QColor("white"))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(color)
        painter.setFont(QFont("Consolas", 9, QFont.Bold))
        painter.drawText(rect.adjusted(8, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, text)

    def _draw_moment_symbol(self, painter: QPainter, center: QPointF, moment: float, color: QColor) -> None:
        radius = max(16.0, min(32.0, 13.0 + abs(moment) * 0.8))
        start_angle = 40 if moment >= 0 else 220
        span_angle = -260 if moment >= 0 else 260
        rect = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
        painter.setPen(QPen(color, 1.8))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(rect, start_angle * 16, span_angle * 16)
        tip_angle = math.radians(start_angle + (-260 if moment >= 0 else 260))
        tx = center.x() + radius * math.cos(tip_angle)
        ty = center.y() - radius * math.sin(tip_angle)
        tangent_angle = tip_angle + (-math.pi / 2 if moment >= 0 else math.pi / 2)
        hx = tx - 10 * math.cos(tangent_angle)
        hy = ty + 10 * math.sin(tangent_angle)
        self._draw_arrow(painter, QPointF(hx, hy), QPointF(tx, ty), color, 1.6)
        self._draw_badge(painter, QPointF(center.x() + radius + 12, center.y() - radius - 6), f"M={self._fmt(moment)}", color)

    def _find_nearest_node(self, x: float, y: float, radius: float = 14) -> str | None:
        best_name = None
        best_dist = radius
        for node in self.model.nodes:
            cx, cy = self._world_to_canvas(node.x, node.y)
            dist = math.hypot(cx - x, cy - y)
            if dist <= best_dist:
                best_name = node.name
                best_dist = dist
        return best_name

    def _find_nearest_element(self, x: float, y: float, tolerance: float = 10) -> str | None:
        best_name = None
        best_dist = tolerance
        for element in self.model.elements:
            start = self._get_node(element.start)
            end = self._get_node(element.end)
            if start is None or end is None:
                continue
            x1, y1 = self._world_to_canvas(start.x, start.y)
            x2, y2 = self._world_to_canvas(end.x, end.y)
            dist = self._distance_to_segment(x, y, x1, y1, x2, y2)
            if dist <= best_dist:
                best_name = element.name
                best_dist = dist
        return best_name

    def _find_nearest_node_load(self, x: float, y: float, tolerance: float = 16) -> str | None:
        best_name = None
        best_dist = tolerance
        for load in self.model.node_loads:
            node = self._get_node(load.node)
            if node is None:
                continue
            cx, cy = self._world_to_canvas(node.x, node.y)
            candidates: list[float] = []
            if abs(load.fx) > 0 or abs(load.fy) > 0:
                ax, ay = self._node_load_canvas_vector(load.fx, load.fy)
                candidates.append(self._distance_to_segment(x, y, cx, cy, cx + ax, cy + ay))
            if abs(load.moment) > 0:
                candidates.append(math.hypot((cx + 22) - x, (cy + 22) - y))
            for dist in candidates:
                if dist <= best_dist:
                    best_dist = dist
                    best_name = load.node
        return best_name

    def _find_nearest_dist_load(self, x: float, y: float, tolerance: float = 18) -> tuple[str | None, str | None, str | None] | None:
        best_key = None
        best_dist = tolerance
        for load in self.model.distributed_loads:
            endpoints = self._dist_load_canvas_points(load)
            if endpoints is None:
                continue
            x1, y1, x2, y2 = endpoints
            ox, oy = self._dist_load_offset(load, x1, y1, x2, y2)
            dist = self._distance_to_segment(x, y, x1 + ox, y1 + oy, x2 + ox, y2 + oy)
            if dist <= best_dist:
                best_dist = dist
                best_key = self._dist_load_key(load)
        return best_key

    def _distance_to_segment(self, px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return math.hypot(px - x1, py - y1)
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    def _world_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        height = max(self.canvas.height(), 200)
        return float(self.grid_margin + x * self.grid_pixels), float(height - self.grid_margin - y * self.grid_pixels)

    def _canvas_to_world(self, canvas_x: float, canvas_y: float) -> tuple[float, float]:
        height = max(self.canvas.height(), 200)
        return float((canvas_x - self.grid_margin) / self.grid_pixels), float((height - self.grid_margin - canvas_y) / self.grid_pixels)

    def _get_node(self, name: str | None) -> NodeSpec | None:
        if name is None:
            return None
        return next((item for item in self.model.nodes if item.name == name), None)

    def _get_element(self, name: str | None) -> ElementSpec | None:
        if name is None:
            return None
        return next((item for item in self.model.elements if item.name == name), None)

    def _get_support_kind(self, node_name: str) -> str | None:
        support = next((item for item in self.model.supports if item.node == node_name), None)
        return None if support is None else support.kind

    def _dist_load_key(self, load: DistributedLoadSpec) -> tuple[str | None, str | None, str | None]:
        return (load.element, load.start_node, load.end_node)

    def _get_dist_load_by_key(self, key: tuple[str | None, str | None, str | None]) -> DistributedLoadSpec | None:
        return next((item for item in self.model.distributed_loads if self._dist_load_key(item) == key), None)

    def _dist_load_label(self, load: DistributedLoadSpec) -> str:
        return load.element if load.element is not None else f"{load.start_node} -> {load.end_node}"

    def _dist_load_canvas_points(self, load: DistributedLoadSpec) -> tuple[float, float, float, float] | None:
        if load.element is not None:
            element = self._get_element(load.element)
            if element is None:
                return None
            start = self._get_node(element.start)
            end = self._get_node(element.end)
        else:
            start = self._get_node(load.start_node)
            end = self._get_node(load.end_node)
        if start is None or end is None:
            return None
        x1, y1 = self._world_to_canvas(start.x, start.y)
        x2, y2 = self._world_to_canvas(end.x, end.y)
        return x1, y1, x2, y2

    def _node_load_canvas_vector(self, fx: float, fy: float) -> tuple[float, float]:
        magnitude, _angle = self._force_polar(fx, fy)
        if magnitude <= 1e-12:
            return 0.0, 0.0
        length = max(28.0, min(168.0, 18.0 + magnitude * 5.2))
        return (fx / magnitude) * length, -(fy / magnitude) * length

    def _dist_load_offset(self, load: DistributedLoadSpec, x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            return 0.0, -20.0
        tx = dx / length
        ty = dy / length
        nx = -ty
        ny = tx
        sign = 1.0 if load.q >= 0 else -1.0
        magnitude = max(18.0, min(50.0, 12.0 + abs(load.q) * 1.1))
        if load.direction == "x":
            vx, vy = sign, 0.0
        elif load.direction == "y":
            vx, vy = 0.0, -sign
        elif load.direction == "parallel":
            vx, vy = sign * tx, sign * ty
        else:
            vx, vy = sign * nx, sign * ny
        return vx * magnitude, vy * magnitude

    def _apply_new_node_support(self, node_name: str) -> None:
        kind = self.new_node_kind.currentText()
        self.model.supports = [item for item in self.model.supports if item.node != node_name]
        if kind != "free":
            self.model.supports.append(SupportSpec(node_name, kind))

    def _support_label(self, kind: str | None) -> str:
        mapping = {
            None: "自由",
            "free": "自由",
            "fixed": "固定",
            "hinged": "铰接",
            "roller_y": "滚支",
            "roller_x": "roller_x",
        }
        return mapping.get(kind, str(kind))

    def _find_element_between(self, start: str, end: str) -> ElementSpec | None:
        for element in self.model.elements:
            if {element.start, element.end} == {start, end}:
                return element
        return None

    def _force_polar(self, fx: float, fy: float) -> tuple[float, float]:
        magnitude = math.hypot(fx, fy)
        if magnitude <= 1e-12:
            return 0.0, 0.0
        return magnitude, math.degrees(math.atan2(fy, fx))

    def _snap_value(self, value: float) -> float:
        return round(value)

    def _fmt(self, value: float) -> str:
        if abs(value) >= 1e4 or (abs(value) > 0 and abs(value) < 1e-3):
            return f"{value:.3e}"
        return f"{value:.3f}"

    def _set_status(self, text: str) -> None:
        self.statusBar().showMessage(text)


class DetailWindow(QMainWindow):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self.setWindowTitle("Details")
        self.resize(480, 640)
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Model Details")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self.info_edit = QPlainTextEdit()
        self.info_edit.setReadOnly(True)
        layout.addWidget(self.info_edit, 1)

    def refresh(self, text: str) -> None:
        self.info_edit.setPlainText(text)


class MainWindow(MainWindow):
    TOOL_HINTS = {
        "select": "Drag nodes to update geometry, or click a node, member, or load to edit its properties.",
        "add_node": "Click any empty grid point to place a node. New nodes snap to integer coordinates.",
        "add_element": "Click a start node, then click an end node to create a member.",
        "add_support": "Click the same node repeatedly to cycle support types.",
        "add_node_load": "Click a node to apply a concentrated force.",
        "add_moment_load": "Click a node to apply a concentrated moment.",
        "add_dist_load": "Click a start node, then an end node to apply a distributed load over the selected span.",
        "delete": "Click a node or member to delete it.",
    }

    def _build_ui(self) -> None:
        self.setWindowTitle("anaStruct Structure Builder")
        self.setStyleSheet(build_qss())
        self.setStatusBar(QStatusBar(self))
        self.setDockOptions(
            QMainWindow.AnimatedDocks
            | QMainWindow.AllowNestedDocks
            | QMainWindow.AllowTabbedDocks
            | QMainWindow.GroupedDragging
        )
        self.statusBar().showMessage("Step 1: place nodes on the canvas.")

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header = QVBoxLayout()
        title = QLabel("anaStruct Structure Builder")
        title.setObjectName("Title")
        subtitle = QLabel("Lightweight structural modeling and internal-force inspection based on anaStruct.")
        subtitle.setObjectName("Subtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        toolbar = QFrame()
        toolbar.setObjectName("Toolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 8, 12, 8)
        toolbar_layout.setSpacing(8)

        self.demo_button = QPushButton("Load Demo")
        self.solve_button = QPushButton("Solve")
        self.solve_button.setProperty("role", "primary")
        self.clear_button = QPushButton("Clear")
        self.detail_button = QPushButton("Details")
        self.results_toggle = QPushButton("Hide Results")
        self.panels_button = QToolButton()
        self.panels_button.setText("Panels")
        self.panels_button.setPopupMode(QToolButton.InstantPopup)
        self.view_combo = QComboBox()
        self.view_combo.addItems(list(VIEW_LABELS.values()))

        for widget in (
            self.demo_button,
            self.solve_button,
            self.clear_button,
            self.detail_button,
            self.results_toggle,
            self.panels_button,
        ):
            toolbar_layout.addWidget(widget)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(QLabel("View"))
        toolbar_layout.addWidget(self.view_combo)
        root.addWidget(toolbar)

        self.canvas_panel = FadeFrame("CanvasPanel")
        root.addWidget(self.canvas_panel, 1)
        canvas_layout = QVBoxLayout(self.canvas_panel)
        canvas_layout.setContentsMargins(12, 12, 12, 12)
        canvas_layout.setSpacing(8)
        canvas_title_row = QHBoxLayout()
        canvas_title = QLabel("Canvas")
        canvas_title.setObjectName("PanelTitle")
        self.canvas_hint = QLabel("Snap-to-integer grid with direct drag editing.")
        self.canvas_hint.setObjectName("SectionHint")
        canvas_title_row.addWidget(canvas_title)
        canvas_title_row.addStretch(1)
        canvas_title_row.addWidget(self.canvas_hint)
        canvas_layout.addLayout(canvas_title_row)
        self.canvas = StructureCanvas(self)
        self.canvas.setStyleSheet(
            f"background:{TOKENS['surface']}; border:1px solid {TOKENS['border']}; border-radius:12px;"
        )
        canvas_layout.addWidget(self.canvas, 1)

        self.sidebar = FadeFrame("Sidebar")
        self.sidebar.setMinimumWidth(180)
        self._build_sidebar()
        self.sidebar_dock = self._create_dock("Tools & Defaults", "sidebar_dock", self.sidebar)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.sidebar_dock)

        self.properties = FadeFrame("PropertyPanel")
        self.properties.setMinimumWidth(220)
        self._build_properties()
        self.properties_dock = self._create_dock("Properties & Summary", "properties_dock", self.properties)
        self.addDockWidget(Qt.RightDockWidgetArea, self.properties_dock)

        self.results_panel = ResultPanel()
        self.results_panel.setMinimumHeight(120)
        self._build_results_panel()
        self.results_dock = self._create_dock("Results", "results_dock", self.results_panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.results_dock)

        self._results_anim = QPropertyAnimation(self.results_panel, b"panelHeight", self)
        self._results_anim.setDuration(160)
        self._results_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._build_window_menu()
        self.sidebar_dock.visibilityChanged.connect(self._sync_dock_buttons)
        self.properties_dock.visibilityChanged.connect(self._sync_dock_buttons)
        self.results_dock.visibilityChanged.connect(self._sync_dock_buttons)
        self.resizeDocks(
            [self.sidebar_dock, self.properties_dock],
            [METRICS["sidebar_w"], METRICS["props_w"]],
            Qt.Horizontal,
        )
        self.resizeDocks([self.results_dock], [METRICS["results_h"]], Qt.Vertical)
        self._sync_dock_buttons()

    def _build_window_menu(self) -> None:
        sidebar_action = self.sidebar_dock.toggleViewAction()
        properties_action = self.properties_dock.toggleViewAction()
        results_action = self.results_dock.toggleViewAction()

        self.menuBar().clear()
        menu = self.menuBar().addMenu("Window")
        menu.addAction(sidebar_action)
        menu.addAction(properties_action)
        menu.addAction(results_action)
        detail_action = menu.addAction("Details")
        detail_action.triggered.connect(self._show_detail_window)

        panels_menu = QMenu(self)
        panels_menu.addAction(sidebar_action)
        panels_menu.addAction(properties_action)
        panels_menu.addAction(results_action)
        self.panels_button.setMenu(panels_menu)

    def _sync_dock_buttons(self) -> None:
        if hasattr(self, "results_toggle"):
            self.results_toggle.setText("Hide Results" if self.results_dock.isVisible() else "Show Results")

    def _build_sidebar_compact(self) -> None:
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setObjectName("SidebarTabs")
        layout.addWidget(self.sidebar_tabs, 1)

        tools_tab = QWidget()
        tools_tab_layout = QVBoxLayout(tools_tab)
        tools_tab_layout.setContentsMargins(0, 8, 0, 0)
        tools_tab_layout.setSpacing(12)

        tools_group = QGroupBox("Tools")
        tools_layout = QVBoxLayout(tools_group)
        tools_layout.setContentsMargins(10, 14, 10, 10)
        tools_layout.setSpacing(8)
        self.tool_buttons = {}
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        for key, label in TOOL_LABELS.items():
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setMinimumHeight(40)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            if key == self.editor_tool:
                button.setChecked(True)
            self.tool_group.addButton(button)
            self.tool_buttons[key] = button
            tools_layout.addWidget(button)
        tools_tab_layout.addWidget(tools_group)

        self.tool_hint = QLabel("Select a tool, then work directly on the canvas.")
        self.tool_hint.setObjectName("Hint")
        self.tool_hint.setWordWrap(True)
        tools_tab_layout.addWidget(self.tool_hint)
        tools_tab_layout.addStretch(1)
        self.sidebar_tabs.addTab(tools_tab, "Tools")

        defaults_scroll = QScrollArea()
        defaults_scroll.setWidgetResizable(True)
        defaults_scroll.setFrameShape(QFrame.NoFrame)
        defaults_container = QWidget()
        defaults_layout = QVBoxLayout(defaults_container)
        defaults_layout.setContentsMargins(0, 8, 0, 0)
        defaults_layout.setSpacing(12)

        defaults_group = QGroupBox("Default Member Properties")
        defaults_form = QFormLayout(defaults_group)
        defaults_form.setContentsMargins(10, 12, 10, 10)
        defaults_form.setSpacing(10)
        self.default_e = QLineEdit("2.06e11")
        self.default_a = QLineEdit("0.02")
        self.default_i = QLineEdit("8.5e-5")
        defaults_form.addRow("E", self.default_e)
        defaults_form.addRow("A", self.default_a)
        defaults_form.addRow("I", self.default_i)
        defaults_layout.addWidget(defaults_group)

        node_tool_group = QGroupBox("Default Node / Point Load")
        node_form = QFormLayout(node_tool_group)
        node_form.setContentsMargins(10, 12, 10, 10)
        node_form.setSpacing(10)
        self.new_node_role = QComboBox()
        self.new_node_role.addItems(["structural", "reference", "hinge"])
        self.new_node_kind = QComboBox()
        self.new_node_kind.addItems(["free", "fixed", "hinged", "roller_y"])
        self.support_kind = QComboBox()
        self.support_kind.addItems(["fixed", "hinged", "roller_x", "roller_y"])
        self.node_force = QLineEdit("10")
        self.node_angle = QLineEdit("-90")
        self.node_moment = QLineEdit("10")
        node_form.addRow("New node role", self.new_node_role)
        node_form.addRow("New node support", self.new_node_kind)
        node_form.addRow("Support preset", self.support_kind)
        node_form.addRow("F", self.node_force)
        node_form.addRow("Angle", self.node_angle)
        node_form.addRow("M", self.node_moment)
        defaults_layout.addWidget(node_tool_group)

        dist_group = QGroupBox("Default Distributed Load")
        dist_form = QFormLayout(dist_group)
        dist_form.setContentsMargins(10, 12, 10, 10)
        dist_form.setSpacing(10)
        self.dist_q = QLineEdit("-10")
        self.dist_dir = QComboBox()
        self.dist_dir.addItems(["element", "parallel", "x", "y"])
        dist_form.addRow("q", self.dist_q)
        dist_form.addRow("Direction", self.dist_dir)
        defaults_layout.addWidget(dist_group)
        defaults_layout.addStretch(1)

        defaults_scroll.setWidget(defaults_container)
        self.sidebar_tabs.addTab(defaults_scroll, "Defaults")

    def _build_properties(self) -> None:
        layout = QVBoxLayout(self.properties)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        summary_title = QLabel("Result Summary")
        summary_title.setObjectName("PanelTitle")
        layout.addWidget(summary_title)

        summary_grid = QGridLayout()
        summary_grid.setSpacing(10)
        self.metric_cards = {}
        items = [
            ("max_displacement", "Max displacement"),
            ("max_axial", "Max axial"),
            ("max_shear", "Max shear"),
            ("max_moment", "Max moment"),
        ]
        for idx, (key, label) in enumerate(items):
            card = FadeFrame("Card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(4)
            title = QLabel(label)
            title.setObjectName("MetricLabel")
            value = QLabel("--")
            value.setObjectName("MetricValue")
            card_layout.addWidget(title)
            card_layout.addWidget(value)
            summary_grid.addWidget(card, idx // 2, idx % 2)
            self.metric_cards[key] = MetricCard(title=title, value=value)
        layout.addLayout(summary_grid)

        current_title = QLabel("Current Object")
        current_title.setObjectName("PanelTitle")
        layout.addWidget(current_title)
        self.selection_title = QLabel("No selection")
        self.selection_title.setObjectName("StatusMuted")
        layout.addWidget(self.selection_title)

        self.property_stack = QStackedWidget()
        layout.addWidget(self.property_stack, 1)
        self.property_stack.setGraphicsEffect(QGraphicsOpacityEffect(self.property_stack))
        self._property_anim = QPropertyAnimation(self.property_stack.graphicsEffect(), b"opacity", self)
        self._property_anim.setDuration(140)
        self._property_anim.setStartValue(0.0)
        self._property_anim.setEndValue(1.0)

        self.empty_page = self._build_empty_property_page()
        self.node_page = self._build_node_property_page()
        self.element_page = self._build_element_property_page()
        self.node_load_page = self._build_node_load_property_page()
        self.dist_load_page = self._build_dist_load_property_page()

        for page in (self.empty_page, self.node_page, self.element_page, self.node_load_page, self.dist_load_page):
            self.property_stack.addWidget(page)

    def _build_results_panel(self) -> None:
        layout = QVBoxLayout(self.results_panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Results")
        title.setObjectName("PanelTitle")
        hint = QLabel("Node and member results appear here after solving.")
        hint.setObjectName("SectionHint")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(hint)
        layout.addLayout(header)

        self.result_switch = QComboBox()
        self.result_switch.addItems(["Node Results", "Element Results"])
        layout.addWidget(self.result_switch, 0, Qt.AlignLeft)

        self.result_pages = QStackedWidget()
        self.node_table = self._make_table(["Node", "ux", "uy", "phi", "Rx", "Ry", "Rm"])
        self.element_table = self._make_table(["Element", "Length", "Nmin", "Nmax", "Qmin", "Qmax", "Mmin", "Mmax"])
        self.result_pages.addWidget(self.node_table)
        self.result_pages.addWidget(self.element_table)
        layout.addWidget(self.result_pages, 1)

    def _build_empty_property_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("DetailPanel")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        label = QLabel("Select a node, member, or load on the canvas to inspect and edit its properties.")
        label.setObjectName("Hint")
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return page

    def _build_node_property_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("DetailPanel")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        form = QFormLayout()
        form.setSpacing(10)
        self.node_x_edit = QLineEdit()
        self.node_y_edit = QLineEdit()
        self.node_role_combo = QComboBox()
        self.node_role_combo.addItems(["structural", "reference", "hinge"])
        self.node_support_combo = QComboBox()
        self.node_support_combo.addItems(["free", "fixed", "hinged", "roller_y"])
        self.node_force_edit = QLineEdit()
        self.node_angle_edit = QLineEdit()
        self.node_moment_edit = QLineEdit()
        form.addRow("X", self.node_x_edit)
        form.addRow("Y", self.node_y_edit)
        form.addRow("Role", self.node_role_combo)
        form.addRow("Support", self.node_support_combo)
        form.addRow("F", self.node_force_edit)
        form.addRow("Angle", self.node_angle_edit)
        form.addRow("M", self.node_moment_edit)
        layout.addLayout(form)
        self.apply_node_button = QPushButton("Apply Node Changes")
        layout.addWidget(self.apply_node_button)
        layout.addStretch(1)
        return page

    def _build_element_property_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("DetailPanel")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        form = QFormLayout()
        form.setSpacing(10)
        self.element_e_edit = QLineEdit()
        self.element_a_edit = QLineEdit()
        self.element_i_edit = QLineEdit()
        self.element_q_edit = QLineEdit()
        self.element_dir_combo = QComboBox()
        self.element_dir_combo.addItems(["element", "parallel", "x", "y"])
        form.addRow("E", self.element_e_edit)
        form.addRow("A", self.element_a_edit)
        form.addRow("I", self.element_i_edit)
        form.addRow("q", self.element_q_edit)
        form.addRow("Direction", self.element_dir_combo)
        layout.addLayout(form)
        self.apply_element_button = QPushButton("Apply Member Changes")
        layout.addWidget(self.apply_element_button)
        layout.addStretch(1)
        return page

    def _build_node_load_property_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("DetailPanel")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        form = QFormLayout()
        form.setSpacing(10)
        self.selected_force_edit = QLineEdit()
        self.selected_angle_edit = QLineEdit()
        self.selected_moment_edit = QLineEdit()
        form.addRow("F", self.selected_force_edit)
        form.addRow("Angle", self.selected_angle_edit)
        form.addRow("M", self.selected_moment_edit)
        layout.addLayout(form)
        self.apply_node_load_button = QPushButton("Apply Load Changes")
        layout.addWidget(self.apply_node_load_button)
        layout.addStretch(1)
        return page

    def _build_dist_load_property_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("DetailPanel")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        form = QFormLayout()
        form.setSpacing(10)
        self.selected_dist_q_edit = QLineEdit()
        self.selected_dist_dir_combo = QComboBox()
        self.selected_dist_dir_combo.addItems(["element", "parallel", "x", "y"])
        form.addRow("q", self.selected_dist_q_edit)
        form.addRow("Direction", self.selected_dist_dir_combo)
        layout.addLayout(form)
        self.apply_dist_load_button = QPushButton("Apply Load Changes")
        layout.addWidget(self.apply_dist_load_button)
        layout.addStretch(1)
        return page

    def _load_demo_model(self) -> None:
        super()._load_demo_model()
        self._set_status("Demo model loaded.")

    def _clear_all(self) -> None:
        super()._clear_all()
        self._set_status("Model cleared. Place nodes to start a new structure.")

    def _solve(self) -> None:
        if len(self.model.nodes) < 2 or not self.model.elements:
            QMessageBox.warning(self, "Nothing to Solve", "Create at least two nodes and one member before solving.")
            return
        try:
            self.result = solve_structure(self.model)
        except SolveError as exc:
            QMessageBox.critical(self, "Solve Failed", str(exc))
            return
        self._update_summary()
        self._update_results_tables()
        self._update_info_panel()
        self.canvas.update()
        self.results_panel.fade_in()
        self._set_status("Solve complete. Switch views to inspect the results.")

    def _toggle_results_panel(self) -> None:
        if hasattr(self, "results_dock"):
            self.results_dock.setVisible(not self.results_dock.isVisible())
            self._sync_dock_buttons()
            return
        expanded = self.results_panel.maximumHeight() > 0
        start = self.results_panel.maximumHeight()
        end = 0 if expanded else METRICS["results_h"]
        self._results_anim.stop()
        self._results_anim.setStartValue(start)
        self._results_anim.setEndValue(end)
        self._results_anim.start()
        self.results_toggle.setText("Show Results" if expanded else "Hide Results")

    def _on_tool_changed(self, tool: str) -> None:
        self.editor_tool = tool
        for key, button in self.tool_buttons.items():
            if key != tool:
                button.setChecked(False)
        self.pending_element_start = None
        self.pending_dist_load_start = None
        self.selected_node_load = None
        self.selected_dist_load = None
        hint = self.TOOL_HINTS.get(tool, "Work directly on the canvas.")
        self.tool_hint.setText(hint)
        self._set_status(hint)
        self._update_selection_panel()
        self._update_info_panel()
        self.canvas.update()

    def _on_canvas_click(self, point: QPointF) -> None:
        x = point.x()
        y = point.y()
        node = self._find_nearest_node(x, y)
        element = self._find_nearest_element(x, y)
        node_load = self._find_nearest_node_load(x, y)
        dist_load = self._find_nearest_dist_load(x, y)

        try:
            if self.editor_tool == "select":
                self.selected_node_load = None
                self.selected_dist_load = None
                if node_load is not None:
                    self.selected_node = None
                    self.selected_element = None
                    self.selected_node_load = node_load
                    self.dragging_node = None
                elif dist_load is not None:
                    self.selected_node = None
                    self.selected_element = None
                    self.selected_dist_load = dist_load
                    self.dragging_node = None
                else:
                    self.selected_node = node
                    self.selected_element = None if node else element
                    self.dragging_node = node
                self._update_selection_panel()
                self._update_info_panel()
                self.canvas.update()
                return

            if self.editor_tool == "add_node":
                if node is None:
                    self._add_node_at_canvas(x, y)
                return

            if self.editor_tool == "add_element":
                if node is None:
                    self._set_status("Click a node to choose the member start point.")
                    return
                if self.pending_element_start is None:
                    self.pending_element_start = node
                    self.selected_node = node
                    self.selected_element = None
                    self._set_status("Start node selected. Click another node to finish the member.")
                else:
                    if node == self.pending_element_start:
                        self._set_status("The end node cannot be the same as the start node.")
                    else:
                        self._add_element(self.pending_element_start, node)
                        self.pending_element_start = None
                self._update_selection_panel()
                self._update_info_panel()
                self.canvas.update()
                return

            if self.editor_tool == "add_support":
                if node is None:
                    self._set_status("Click a node to assign a support.")
                    return
                self._cycle_support(node)
                return

            if self.editor_tool == "add_node_load":
                if node is None:
                    self._set_status("Click a node to apply a point load.")
                    return
                self._set_node_load(node)
                return

            if self.editor_tool == "add_moment_load":
                if node is None:
                    self._set_status("Click a node to apply a concentrated moment.")
                    return
                self._set_node_moment(node)
                return

            if self.editor_tool == "add_dist_load":
                if node is None:
                    self._set_status("Distributed loads are selected by two nodes: click the start node, then the end node.")
                    return
                if self.pending_dist_load_start is None:
                    self.pending_dist_load_start = node
                    self.selected_node = node
                    self.selected_element = None
                    self._update_selection_panel()
                    self._update_info_panel()
                    self._set_status("Start node selected for distributed load. Click the end node.")
                else:
                    if node == self.pending_dist_load_start:
                        self._set_status("The end node cannot be the same as the start node.")
                    else:
                        self._set_distributed_load_between_nodes(self.pending_dist_load_start, node)
                        self.pending_dist_load_start = None
                self.canvas.update()
                return

            if self.editor_tool == "delete":
                if node:
                    self._delete_node(node)
                elif element:
                    self._delete_element(element)
        except SolveError as exc:
            QMessageBox.critical(self, "Input Error", str(exc))

    def _on_canvas_move(self, point: QPointF) -> None:
        x, y = self._canvas_to_world(point.x(), point.y())
        sx = self._snap_value(x)
        sy = self._snap_value(y)
        self.hover_world_point = (sx, sy)
        if self.editor_tool == "add_node":
            self._set_status(f"Snap target: ({int(sx)}, {int(sy)})")
        self.canvas.update()

    def _add_node_at_canvas(self, canvas_x: float, canvas_y: float) -> None:
        x, y = self._canvas_to_world(canvas_x, canvas_y)
        x = self._snap_value(x)
        y = self._snap_value(y)
        existing = next((item for item in self.model.nodes if abs(item.x - x) < 1e-9 and abs(item.y - y) < 1e-9), None)
        if existing is not None:
            self.selected_node = existing.name
            self.selected_element = None
            self.selected_node_load = None
            self.selected_dist_load = None
            self._update_selection_panel()
            self._update_info_panel()
            self.canvas.update()
            self._set_status(f"A node already exists at this location: {existing.name}.")
            return
        name = f"N{len(self.model.nodes) + 1}"
        self.model.nodes.append(NodeSpec(name, x, y, role=self.new_node_role.currentText()))
        self._apply_new_node_support(name)
        self.result = None
        self.selected_node = name
        self.selected_element = None
        self.selected_node_load = None
        self.selected_dist_load = None
        self._update_selection_panel()
        self._update_summary()
        self._update_results_tables()
        self._update_info_panel()
        self.canvas.update()
        self._set_status(f"Placed node {name}.")

    def _add_element(self, start: str, end: str) -> None:
        if self._find_element_between(start, end) is not None:
            self._set_status("A member already exists between these two nodes.")
            return
        name = f"E{len(self.model.elements) + 1}"
        self.model.elements.append(
            ElementSpec(
                name=name,
                start=start,
                end=end,
                e=self._parse_float(self.default_e, "E"),
                a=self._parse_float(self.default_a, "A"),
                i=self._parse_float(self.default_i, "I"),
            )
        )
        self.result = None
        self.selected_node = None
        self.selected_element = name
        self.selected_node_load = None
        self.selected_dist_load = None
        self._update_selection_panel()
        self._update_summary()
        self._update_results_tables()
        self._update_info_panel()
        self.canvas.update()
        self._set_status(f"Created member {name}.")

    def _cycle_support(self, node_name: str) -> None:
        cycle = [None, "fixed", "hinged", "roller_y"]
        current = self._get_support_kind(node_name)
        try:
            index = cycle.index(current)
        except ValueError:
            index = 0
        next_kind = cycle[(index + 1) % len(cycle)]
        self.model.supports = [item for item in self.model.supports if item.node != node_name]
        if next_kind is not None:
            self.model.supports.append(SupportSpec(node_name, next_kind))
        self.result = None
        self.selected_node = node_name
        self.selected_element = None
        self.selected_node_load = None
        self.selected_dist_load = None
        self._update_selection_panel()
        self._update_info_panel()
        self.canvas.update()
        self._set_status(f"Node {node_name} support changed to {self._support_label(next_kind)}.")

    def _set_node_load(self, node_name: str) -> None:
        fx, fy = self._force_components_from_widgets(self.node_force, self.node_angle)
        moment = self._parse_float(self.node_moment, "M")
        self.model.node_loads = [item for item in self.model.node_loads if item.node != node_name]
        self.model.node_loads.append(NodeLoadSpec(node_name, fx, fy, moment))
        self.result = None
        self.selected_node = node_name
        self.selected_element = None
        self.selected_node_load = node_name
        self.selected_dist_load = None
        self._update_selection_panel()
        self._update_info_panel()
        self.canvas.update()
        self._set_status("Point load applied.")

    def _set_node_moment(self, node_name: str) -> None:
        moment = self._parse_float(self.node_moment, "M")
        existing = next((item for item in self.model.node_loads if item.node == node_name), None)
        fx = existing.fx if existing else 0.0
        fy = existing.fy if existing else 0.0
        if abs(moment) <= 1e-12 and abs(fx) <= 1e-12 and abs(fy) <= 1e-12:
            self._set_status("M is currently zero. Enter a non-zero moment first.")
            return
        self.model.node_loads = [item for item in self.model.node_loads if item.node != node_name]
        if any(abs(v) > 1e-12 for v in (fx, fy, moment)):
            self.model.node_loads.append(NodeLoadSpec(node_name, fx, fy, moment))
        self.result = None
        self.selected_node = node_name
        self.selected_element = None
        self.selected_node_load = node_name
        self.selected_dist_load = None
        self._update_selection_panel()
        self._update_info_panel()
        self.canvas.update()
        self._set_status("Concentrated moment applied.")

    def _set_distributed_load_between_nodes(self, start_node: str, end_node: str) -> None:
        q = self._parse_float(self.dist_q, "q")
        direction = self.dist_dir.currentText()
        self.model.distributed_loads = [
            item
            for item in self.model.distributed_loads
            if not (item.start_node == start_node and item.end_node == end_node)
            and not (item.start_node == end_node and item.end_node == start_node)
        ]
        self.model.distributed_loads.append(
            DistributedLoadSpec(q=q, direction=direction, start_node=start_node, end_node=end_node)
        )
        self.result = None
        self.selected_node = None
        self.selected_element = None
        self.selected_node_load = None
        self.selected_dist_load = self._dist_load_key(self.model.distributed_loads[-1])
        self._update_selection_panel()
        self._update_info_panel()
        self.canvas.update()
        self._set_status("Distributed load applied over the selected span.")

    def _delete_node(self, node_name: str) -> None:
        super()._delete_node(node_name)
        self._set_status(f"Deleted node {node_name}.")

    def _delete_element(self, element_name: str) -> None:
        super()._delete_element(element_name)
        self._set_status(f"Deleted member {element_name}.")

    def _apply_node_properties(self) -> None:
        try:
            if self.selected_node is None:
                return
            node = self._get_node(self.selected_node)
            if node is None:
                return
            node.x = self._snap_value(self._parse_float(self.node_x_edit, "X"))
            node.y = self._snap_value(self._parse_float(self.node_y_edit, "Y"))
            node.role = self.node_role_combo.currentText()
            self.model.supports = [item for item in self.model.supports if item.node != node.name]
            if self.node_support_combo.currentText() != "free":
                self.model.supports.append(SupportSpec(node.name, self.node_support_combo.currentText()))
            self.model.node_loads = [item for item in self.model.node_loads if item.node != node.name]
            fx, fy = self._force_components_from_widgets(self.node_force_edit, self.node_angle_edit)
            moment = self._parse_float(self.node_moment_edit, "M")
            if any(abs(v) > 1e-12 for v in (fx, fy, moment)):
                self.model.node_loads.append(NodeLoadSpec(node.name, fx, fy, moment))
            self.result = None
            self._update_selection_panel()
            self._update_summary()
            self._update_results_tables()
            self._update_info_panel()
            self.canvas.update()
        except SolveError as exc:
            QMessageBox.critical(self, "Input Error", str(exc))

    def _apply_element_properties(self) -> None:
        try:
            if self.selected_element is None:
                return
            element = self._get_element(self.selected_element)
            if element is None:
                return
            element.e = self._parse_float(self.element_e_edit, "E")
            element.a = self._parse_float(self.element_a_edit, "A")
            element.i = self._parse_float(self.element_i_edit, "I")
            self.model.distributed_loads = [item for item in self.model.distributed_loads if item.element != element.name]
            q = self._parse_float(self.element_q_edit, "q")
            if abs(q) > 1e-12:
                self.model.distributed_loads.append(
                    DistributedLoadSpec(q=q, element=element.name, direction=self.element_dir_combo.currentText())
                )
            self.result = None
            self._update_summary()
            self._update_results_tables()
            self._update_info_panel()
            self.canvas.update()
        except SolveError as exc:
            QMessageBox.critical(self, "Input Error", str(exc))

    def _apply_node_load_properties(self) -> None:
        try:
            if self.selected_node_load is None:
                return
            fx, fy = self._force_components_from_widgets(self.selected_force_edit, self.selected_angle_edit)
            moment = self._parse_float(self.selected_moment_edit, "M")
            self.model.node_loads = [item for item in self.model.node_loads if item.node != self.selected_node_load]
            if any(abs(v) > 1e-12 for v in (fx, fy, moment)):
                self.model.node_loads.append(NodeLoadSpec(self.selected_node_load, fx, fy, moment))
            self.result = None
            self._update_selection_panel()
            self._update_info_panel()
            self.canvas.update()
        except SolveError as exc:
            QMessageBox.critical(self, "Input Error", str(exc))

    def _apply_dist_load_properties(self) -> None:
        try:
            if self.selected_dist_load is None:
                return
            target = self._get_dist_load_by_key(self.selected_dist_load)
            if target is None:
                return
            target.q = self._parse_float(self.selected_dist_q_edit, "q")
            target.direction = self.selected_dist_dir_combo.currentText()
            self.result = None
            self._update_selection_panel()
            self._update_info_panel()
            self.canvas.update()
        except SolveError as exc:
            QMessageBox.critical(self, "Input Error", str(exc))

    def _update_selection_panel(self) -> None:
        self._clear_error_states()
        if self.selected_node_load:
            load = next((item for item in self.model.node_loads if item.node == self.selected_node_load), None)
            if load is not None:
                magnitude, angle = self._force_polar(load.fx, load.fy)
                self.selection_title.setText(f"Node load {load.node}")
                self.selected_force_edit.setText(self._fmt(magnitude))
                self.selected_angle_edit.setText(self._fmt(angle))
                self.selected_moment_edit.setText(self._fmt(load.moment))
                self.property_stack.setCurrentWidget(self.node_load_page)
                self._fade_properties()
                return

        if self.selected_dist_load:
            load = self._get_dist_load_by_key(self.selected_dist_load)
            if load is not None:
                self.selection_title.setText(f"Distributed load {self._dist_load_label(load)}")
                self.selected_dist_q_edit.setText(self._fmt(load.q))
                self.selected_dist_dir_combo.setCurrentText(load.direction)
                self.property_stack.setCurrentWidget(self.dist_load_page)
                self._fade_properties()
                return

        if self.selected_node:
            node = self._get_node(self.selected_node)
            if node is not None:
                self.selection_title.setText(f"Node {node.name}")
                self.node_x_edit.setText(self._fmt(node.x))
                self.node_y_edit.setText(self._fmt(node.y))
                self.node_role_combo.setCurrentText(node.role)
                self.node_support_combo.setCurrentText(self._get_support_kind(node.name) or "free")
                load = next((item for item in self.model.node_loads if item.node == node.name), None)
                magnitude, angle = self._force_polar(load.fx, load.fy) if load else (0.0, 0.0)
                self.node_force_edit.setText(self._fmt(magnitude))
                self.node_angle_edit.setText(self._fmt(angle))
                self.node_moment_edit.setText(self._fmt(load.moment) if load else "0")
                self.property_stack.setCurrentWidget(self.node_page)
                self._fade_properties()
                return

        if self.selected_element:
            element = self._get_element(self.selected_element)
            if element is not None:
                self.selection_title.setText(f"Member {element.name}: {element.start} -> {element.end}")
                self.element_e_edit.setText(self._fmt(element.e))
                self.element_a_edit.setText(self._fmt(element.a))
                self.element_i_edit.setText(self._fmt(element.i))
                dist = next((item for item in self.model.distributed_loads if item.element == element.name), None)
                self.element_q_edit.setText(self._fmt(dist.q) if dist else "0")
                self.element_dir_combo.setCurrentText(dist.direction if dist else "element")
                self.property_stack.setCurrentWidget(self.element_page)
                self._fade_properties()
                return

        self.selection_title.setText("No selection")
        self.property_stack.setCurrentWidget(self.empty_page)
        self._fade_properties()

    def _update_info_panel(self) -> None:
        lines = [
            f"Nodes: {len(self.model.nodes)}",
            f"Members: {len(self.model.elements)}",
            f"Supports: {len(self.model.supports)}",
            f"Node loads: {len(self.model.node_loads)}",
            f"Distributed loads: {len(self.model.distributed_loads)}",
            "",
            f"Current tool: {TOOL_LABELS.get(self.editor_tool, self.editor_tool)}",
            f"New node role: {self.new_node_role.currentText()}",
            f"New node support: {self._support_label(self.new_node_kind.currentText())}",
            f"Support preset: {self._support_label(self.support_kind.currentText())}",
            f"Default node load: F={self.node_force.text()}, angle={self.node_angle.text()}, M={self.node_moment.text()}",
            f"Default distributed load: q={self.dist_q.text()}, dir={self.dist_dir.currentText()}",
        ]
        self.detail_window.refresh("\n".join(lines))

    def _parse_float(self, widget: QLineEdit, label: str) -> float:
        self._set_error_state(widget, False)
        try:
            return float(widget.text().strip())
        except ValueError as exc:
            self._set_error_state(widget, True)
            raise SolveError(f"{label} is not a valid number.") from exc

    def _force_components_from_widgets(self, magnitude_widget: QLineEdit, angle_widget: QLineEdit) -> tuple[float, float]:
        magnitude = self._parse_float(magnitude_widget, "F")
        angle_deg = self._parse_float(angle_widget, "Angle")
        angle_rad = math.radians(angle_deg)
        return magnitude * math.cos(angle_rad), magnitude * math.sin(angle_rad)

    def _draw_loads(self, painter: QPainter) -> None:
        for load in self.model.node_loads:
            node = self._get_node(load.node)
            if node is None:
                continue
            x, y = self._world_to_canvas(node.x, node.y)
            color = _c("primary") if load.node == self.selected_node_load else _c("danger")
            magnitude, angle = self._force_polar(load.fx, load.fy)
            if magnitude > 1e-12:
                ax, ay = self._node_load_canvas_vector(load.fx, load.fy)
                self._draw_arrow(painter, QPointF(x + ax, y + ay), QPointF(x, y), color, 2.3)
                self._draw_badge(
                    painter,
                    QPointF(x + ax * 0.55 + 12, y + ay * 0.55 - 10),
                    f"F={self._fmt(magnitude)} @ {self._fmt(angle)} deg",
                    color,
                )
            if abs(load.moment) > 1e-12:
                self._draw_moment_symbol(painter, QPointF(x, y), load.moment, color)

        for load in self.model.distributed_loads:
            endpoints = self._dist_load_canvas_points(load)
            if endpoints is None:
                continue
            x1, y1, x2, y2 = endpoints
            color = _c("primary") if self.selected_dist_load == self._dist_load_key(load) else _c("danger")
            ox, oy = self._dist_load_offset(load, x1, y1, x2, y2)
            p1 = QPointF(x1 + ox, y1 + oy)
            p2 = QPointF(x2 + ox, y2 + oy)
            painter.setPen(QPen(_c("danger_soft"), 4))
            painter.drawLine(p1, p2)
            painter.setPen(QPen(color, 1.2))
            painter.drawLine(p1, p2)
            for factor in (0.16, 0.32, 0.48, 0.64, 0.80):
                px = x1 + (x2 - x1) * factor
                py = y1 + (y2 - y1) * factor
                sx = px + ox
                sy = py + oy
                self._draw_arrow(painter, QPointF(sx, sy), QPointF(px, py), color, 1.2)
            self._draw_badge(
                painter,
                QPointF((x1 + x2) / 2 + ox * 0.85, (y1 + y2) / 2 + oy * 0.85 - 12),
                f"q={self._fmt(load.q)}",
                color,
            )

    def _support_label(self, kind: str | None) -> str:
        mapping = {
            None: "free",
            "free": "free",
            "fixed": "fixed",
            "hinged": "hinged",
            "roller_y": "roller Y",
            "roller_x": "roller X",
        }
        return mapping.get(kind, str(kind))

    def _draw_canvas_badge(self, painter: QPainter) -> None:
        painter.setPen(QPen(_c("border"), 1))
        painter.setBrush(QColor("white"))
        rect = QRectF(16, 16, 280, 52)
        painter.drawRoundedRect(rect, 10, 10)
        painter.setPen(_c("text"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.drawText(QPointF(28, 38), f"Tool: {TOOL_LABELS.get(self.editor_tool, self.editor_tool)}")
        painter.setPen(_c("text_muted"))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(QPointF(28, 58), f"View: {VIEW_LABELS.get(self.view_mode, self.view_mode)}")


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
