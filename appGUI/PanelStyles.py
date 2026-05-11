from PyQt6 import QtCore, QtWidgets


def _theme_name(app=None):
    options = getattr(app, "options", None)
    if options is not None:
        try:
            return options.get("global_theme", "default")
        except AttributeError:
            pass

    settings = QtCore.QSettings("Open Source", "FlatCAM_Plus")
    if settings.contains("theme"):
        return settings.value("theme", type=str)
    return "default"


def modern_panel_colors(app=None):
    theme = _theme_name(app)
    if theme in ["default", "light"]:
        return {
            "app_bg": "#eef0f3",
            "surface": "#ffffff",
            "subtle": "#f8fafc",
            "text": "#263244",
            "selected_text": "#111827",
            "border": "#dfe4ec",
            "separator": "#e3e8f0",
            "hover": "#eef4ff",
            "hover_border": "#d9e6fb",
            "active": "#dfeafe",
            "active_border": "#b9d1ff",
            "disabled": "#a8b2c1",
            "hint": "#6f7b8e",
            "console_bg": "#1e1e1e",
            "console_text": "#d4d4d4",
        }

    return {
        "app_bg": "#171717",
        "surface": "#262626",
        "subtle": "#171717",
        "text": "#f0f0f0",
        "selected_text": "#ffffff",
        "border": "#444444",
        "separator": "#323232",
        "hover": "#323232",
        "hover_border": "#444444",
        "active": "#2b2b2b",
        "active_border": "#ff6900",
        "disabled": "#777777",
        "hint": "#999999",
        "console_bg": "#171717",
        "console_text": "#f0f0f0",
    }


def _normalize_preference_label_colors(widget):
    if widget is None:
        return

    try:
        from appGUI.GUIElements import FCLabel
    except ImportError:
        return

    for label in widget.findChildren(FCLabel):
        if getattr(label, "_color", None) is None:
            continue

        label._color = None
        title = getattr(label, "_title", None)
        if title is not None:
            label.setText(str(title))


def modern_panel_frame_stylesheet(app=None):
    c = modern_panel_colors(app)
    return f"""
        FCFrame {{
            background: {c["surface"]};
            border: 1px solid {c["border"]};
            border-radius: 8px;
        }}
    """


def _resource_icon_url(app=None, filename=""):
    resource_location = getattr(app, "resource_location", "")
    if not resource_location or not filename:
        return ""
    return (resource_location + "/" + filename).replace("\\", "/")


def _modern_tab_close_button_stylesheet(app=None):
    c = modern_panel_colors(app)
    close_icon = _resource_icon_url(app, "cancel_edit32.png")
    icon_rule = f"image: url({close_icon});" if close_icon else ""
    return f"""
        QTabBar::close-button {{
            {icon_rule}
            subcontrol-position: right center;
            width: 24px;
            height: 24px;
            margin-left: 6px;
            margin-right: 7px;
            border: 1px solid transparent;
            border-radius: 7px;
        }}
        QTabBar::close-button:hover {{
            background: {c["hover"]};
            border: 1px solid {c["hover_border"]};
        }}
        QTabBar::close-button:pressed {{
            background: {c["active"]};
            border: 1px solid {c["active_border"]};
        }}
    """


def modern_panel_stylesheet(app=None):
    c = modern_panel_colors(app)
    theme = _theme_name(app)
    if theme in ["default", "light"]:
        alert_bg = "#fff1f2"
        alert_hover = "#ffe4e6"
        alert_border = "#f43f5e"
        alert_text = "#b4233a"
    else:
        alert_bg = "#3a1c28"
        alert_hover = "#4a2432"
        alert_border = "#f87171"
        alert_text = "#fecdd3"

    arrow_icon = ""
    resource_location = getattr(app, "resource_location", "")
    if resource_location:
        arrow_icon = (resource_location + "/down-arrow32.png").replace("\\", "/")

    arrow_rule = ""
    if arrow_icon:
        arrow_rule = f"""
            QComboBox::down-arrow {{
                image: url({arrow_icon});
                width: 10px;
                height: 10px;
            }}
        """

    return f"""
        QWidget[modernPanelRoot="true"] {{
            background: {c["surface"]};
            color: {c["text"]};
            border: 0px;
            border-radius: 8px;
        }}
        QToolTip {{
            background: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 5px;
            padding: 5px 7px;
        }}
        QScrollArea {{
            background: transparent;
            border: 0px;
        }}
        QLabel {{
            color: {c["text"]};
        }}
        QTabWidget::pane {{
            background: {c["surface"]};
            border: 1px solid {c["border"]};
            border-radius: 8px;
            top: -1px;
        }}
        QTabBar {{
            qproperty-drawBase: 0;
        }}
        QTabBar::tab {{
            background: {c["subtle"]};
            color: {c["hint"]};
            border: 1px solid {c["border"]};
            border-bottom: 0px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            padding: 7px 34px 7px 12px;
            margin-right: 4px;
            min-width: 82px;
            font-weight: 600;
        }}
        QTabBar::tab:hover {{
            background: {c["hover"]};
            color: {c["selected_text"]};
            border-color: {c["hover_border"]};
        }}
        QTabBar::tab:selected {{
            background: {c["surface"]};
            color: {c["text"]};
            border-color: {c["border"]};
            border-bottom: 1px solid {c["surface"]};
        }}
        QTabBar::tab:disabled {{
            color: {c["disabled"]};
        }}
        {_modern_tab_close_button_stylesheet(app)}
        FCFrame,
        QGroupBox {{
            background: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 8px;
        }}
        QGroupBox {{
            margin-top: 13px;
            padding: 9px 8px 8px 8px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 8px;
            padding: 0 5px;
            color: {c["text"]};
        }}
        QPushButton,
        QToolButton {{
            background: {c["subtle"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 5px;
            padding: 5px 7px;
            font-weight: 600;
            min-height: 24px;
        }}
        QPushButton:hover,
        QToolButton:hover {{
            background: {c["hover"]};
            border-color: {c["hover_border"]};
        }}
        QPushButton:pressed,
        QPushButton:checked,
        QToolButton:pressed,
        QToolButton:checked {{
            background: {c["active"]};
            border-color: {c["active_border"]};
        }}
        QPushButton:disabled,
        QToolButton:disabled {{
            background: {c["surface"]};
            color: {c["disabled"]};
            border-color: {c["separator"]};
        }}
        QPushButton[prefAlert="true"],
        QToolButton[prefAlert="true"] {{
            background: {alert_bg};
            color: {alert_text};
            border-color: {alert_border};
        }}
        QPushButton[prefAlert="true"]:hover,
        QToolButton[prefAlert="true"]:hover {{
            background: {alert_hover};
            border-color: {alert_border};
        }}
        QToolButton::menu-button {{
            border: 0px;
            width: 14px;
        }}
        QLineEdit,
        QComboBox,
        QSpinBox,
        QDoubleSpinBox,
        QTextEdit,
        QPlainTextEdit {{
            background: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 5px;
            padding: 4px 7px;
            min-height: 28px;
            selection-background-color: {c["active"]};
            selection-color: {c["selected_text"]};
        }}
        QComboBox {{
            padding-right: 28px;
        }}
        QLineEdit:focus,
        QComboBox:focus,
        QSpinBox:focus,
        QDoubleSpinBox:focus,
        QTextEdit:focus,
        QPlainTextEdit:focus {{
            border-color: {c["active_border"]};
        }}
        QLineEdit:disabled,
        QComboBox:disabled,
        QSpinBox:disabled,
        QDoubleSpinBox:disabled,
        QTextEdit:disabled,
        QPlainTextEdit:disabled {{
            color: {c["disabled"]};
            border-color: {c["separator"]};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            border-left: 0px;
            width: 26px;
        }}
        {arrow_rule}
        QComboBox QAbstractItemView {{
            background: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 8px;
            padding: 6px;
            outline: 0px;
            selection-background-color: {c["hover"]};
            selection-color: {c["selected_text"]};
        }}
        QSpinBox::up-button,
        QSpinBox::down-button,
        QDoubleSpinBox::up-button,
        QDoubleSpinBox::down-button {{
            background: transparent;
            border: 0px;
            width: 18px;
        }}
        QCheckBox,
        QRadioButton {{
            color: {c["text"]};
            spacing: 6px;
            border-top: 2px solid transparent;
            border-bottom: 2px solid transparent;
            text-decoration: none;
        }}
        QCheckBox:hover,
        QRadioButton:hover {{
            border-bottom: 2px solid transparent;
            text-decoration: none;
        }}
        QCheckBox::indicator,
        QRadioButton::indicator {{
            background: {c["surface"]};
            border: 1px solid {c["border"]};
            width: 15px;
            height: 15px;
        }}
        QCheckBox::indicator {{
            border-radius: 4px;
        }}
        QRadioButton::indicator {{
            border-radius: 8px;
        }}
        QCheckBox::indicator:hover,
        QRadioButton::indicator:hover {{
            background: {c["hover"]};
            border-color: {c["hover_border"]};
        }}
        QCheckBox::indicator:checked,
        QRadioButton::indicator:checked {{
            background: {c["active"]};
            border-color: {c["active_border"]};
        }}
        QListWidget,
        QTableWidget,
        QTreeWidget {{
            background: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 8px;
            gridline-color: {c["separator"]};
            alternate-background-color: {c["subtle"]};
            selection-background-color: {c["hover"]};
            selection-color: {c["selected_text"]};
            outline: 0px;
        }}
        QListWidget::item,
        QTableWidget::item,
        QTreeWidget::item {{
            border: 0px;
            padding: 4px 5px;
        }}
        QTableWidget QCheckBox {{
            background: transparent;
            margin: 0px;
            padding: 0px;
        }}
        QListWidget::item:selected,
        QTableWidget::item:selected,
        QTreeWidget::item:selected {{
            background: {c["hover"]};
            color: {c["selected_text"]};
        }}
        QListWidget::item:hover,
        QTableWidget::item:hover,
        QTreeWidget::item:hover {{
            background: {c["hover"]};
            color: {c["selected_text"]};
        }}
        QHeaderView::section {{
            background: {c["subtle"]};
            color: {c["text"]};
            border: 0px;
            border-bottom: 1px solid {c["separator"]};
            padding: 6px;
            font-weight: 600;
        }}
        QProgressBar {{
            border: 1px solid {c["border"]};
            border-radius: 5px;
            background: {c["surface"]};
            color: {c["text"]};
            text-align: center;
            min-height: 18px;
        }}
        QProgressBar::chunk {{
            background: {c["active_border"]};
            border-radius: 3px;
        }}
        QMenu {{
            background: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: 8px;
            padding: 6px;
        }}
        QMenu::item {{
            background: transparent;
            color: {c["text"]};
            padding: 6px 22px 6px 28px;
            border-radius: 5px;
        }}
        QMenu::item:selected {{
            background: {c["hover"]};
            color: {c["selected_text"]};
        }}
        QMenu::item:disabled {{
            color: {c["disabled"]};
        }}
        QMenu::separator {{
            height: 1px;
            background: {c["separator"]};
            margin: 5px 8px;
        }}
        QMenu::icon {{
            padding-left: 4px;
        }}
    """


def modern_preferences_tab_area_stylesheet(app=None):
    c = modern_panel_colors(app)
    return f"""
        QTabWidget#preferences_tab_area::pane {{
            background: transparent;
            border: 1px solid {c["border"]};
            border-radius: 8px;
            top: -1px;
        }}
        QTabWidget#preferences_tab_area > QWidget {{
            background: transparent;
        }}
    """


def modern_preferences_tabbar_stylesheet(app=None):
    c = modern_panel_colors(app)
    return f"""
        QTabBar {{
            qproperty-drawBase: 0;
        }}
        QTabBar::tab {{
            background: {c["subtle"]};
            color: {c["hint"]};
            border: 1px solid {c["border"]};
            border-bottom: 0px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            padding: 7px 34px 7px 12px;
            margin-right: 4px;
            min-width: 90px;
            font-weight: 600;
        }}
        QTabBar::tab:hover {{
            background: {c["hover"]};
            color: {c["selected_text"]};
            border-color: {c["hover_border"]};
        }}
        QTabBar::tab:selected {{
            background: {c["surface"]};
            color: {c["text"]};
            border-color: {c["border"]};
            border-bottom: 1px solid {c["surface"]};
        }}
        QTabBar::tab:selected:disabled {{
            background: {c["subtle"]};
            color: {c["disabled"]};
            border-color: {c["separator"]};
        }}
        {_modern_tab_close_button_stylesheet(app)}
    """


def modern_workspace_tab_area_stylesheet(app=None, object_name="workspace_tab_area"):
    c = modern_panel_colors(app)
    if object_name == "left_sidebar":
        return f"""
            QTabWidget#{object_name} {{
                background: {c["surface"]};
                border: 1px solid {c["border"]};
                border-radius: 12px;
            }}
            QTabWidget#{object_name}::pane {{
                background: {c["surface"]};
                border: 0px;
                border-radius: 12px;
                margin: 0px;
                top: 0px;
            }}
            QTabWidget#{object_name}::tab-bar {{
                left: 0px;
                top: 0px;
            }}
            QTabWidget#{object_name} > QWidget {{
                background: {c["surface"]};
                border-radius: 12px;
            }}
        """

    if object_name == "plot_tab_area":
        return f"""
            QTabWidget#{object_name} {{
                background: {c["surface"]};
                border: 1px solid {c["border"]};
                border-radius: 12px;
            }}
            QTabWidget#{object_name}::pane {{
                background: {c["surface"]};
                border: 0px;
                border-radius: 12px;
                margin: 0px;
                top: 0px;
            }}
            QTabWidget#{object_name}::tab-bar {{
                left: 10px;
                top: 0px;
            }}
            QTabWidget#{object_name} > QWidget {{
                background: {c["surface"]};
                border-radius: 12px;
            }}
        """

    return f"""
        QTabWidget#{object_name} {{
            background: {c["surface"]};
            border-radius: 10px;
        }}
        QTabWidget#{object_name}::pane {{
            background: {c["surface"]};
            border: 1px solid {c["border"]};
            border-radius: 10px;
            top: -1px;
        }}
        QTabWidget#{object_name}::tab-bar {{
            left: 0px;
        }}
        QTabWidget#{object_name} > QWidget {{
            background: {c["surface"]};
            border-radius: 10px;
        }}
    """


def modern_workspace_tabbar_stylesheet(app=None, min_width=90, expanding=True):
    c = modern_panel_colors(app)
    expanding_value = "true" if expanding else "false"
    bar_background = c["subtle"] if expanding else "transparent"
    bar_border = f"1px solid {c['border']}" if expanding else "0px"
    tab_border_right = f"1px solid {c['border']}"
    tab_margin = "0px" if expanding else "5px 5px 0px 0px"
    tab_radius_styles = "border-radius: 0px;" if expanding else """
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            border-bottom-left-radius: 0px;
            border-bottom-right-radius: 0px;
    """

    return f"""
        QTabBar {{
            qproperty-drawBase: 0;
            qproperty-expanding: {expanding_value};
            background: {bar_background};
            border: {bar_border};
            border-bottom: 0px;
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        }}
        QTabBar::tab {{
            background: {c["subtle"]};
            color: {c["hint"]};
            border: 1px solid {c["border"]};
            border-right: {tab_border_right};
            border-bottom: 0px;
            {tab_radius_styles}
            padding: 8px 34px 8px 12px;
            margin: {tab_margin};
            min-width: {min_width}px;
            font-weight: 600;
        }}
        QTabBar::tab:hover {{
            background: {c["hover"]};
            color: {c["selected_text"]};
            border-color: {c["hover_border"]};
        }}
        QTabBar::tab:selected {{
            background: {c["surface"]};
            color: {c["text"]};
            border-right: 1px solid {c["border"]};
            border-bottom: 0px;
        }}
        QTabBar::tab:disabled {{
            color: {c["disabled"]};
        }}
        {_modern_tab_close_button_stylesheet(app)}
    """


def modern_project_view_stylesheet(app=None):
    c = modern_panel_colors(app)
    return f"""
        QTreeView {{
            background: {c["surface"]};
            color: {c["text"]};
            border: 0px;
            border-radius: 8px;
            padding: 2px;
            outline: 0px;
            selection-background-color: {c["hover"]};
            selection-color: {c["selected_text"]};
        }}
        QTreeView::item {{
            background: transparent;
            border: 0px;
            border-radius: 5px;
            padding: 5px;
            min-height: 24px;
        }}
        QTreeView::item:hover {{
            background: {c["hover"]};
            color: {c["selected_text"]};
        }}
        QTreeView::item:selected {{
            background: {c["active"]};
            color: {c["selected_text"]};
        }}
        QTreeView::branch {{
            background: transparent;
        }}
        QHeaderView::section {{
            background: {c["subtle"]};
            color: {c["text"]};
            border: 0px;
            border-bottom: 1px solid {c["separator"]};
            padding: 6px;
            font-weight: 600;
        }}
    """


def modern_sidebar_stylesheet(app=None):
    c = modern_panel_colors(app)
    return f"""
        QScrollArea {{
            background: {c["surface"]};
            border: 1px solid {c["border"]};
            border-radius: 8px;
        }}
        QScrollArea > QWidget {{
            background: {c["surface"]};
            border-radius: 8px;
        }}
        QScrollArea > QWidget > QWidget {{
            background: {c["surface"]};
            border-radius: 8px;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {c["separator"]};
            border-radius: 5px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {c["hover_border"]};
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background: transparent;
            border: 0px;
        }}
    """


def _resolve_tab_bar(tab_widget):
    if tab_widget is None:
        return None

    tab_bar = getattr(tab_widget, "tabBar", None)
    if callable(tab_bar):
        return tab_bar()
    return tab_bar


def apply_modern_panel_style(widget, app=None):
    if widget is None:
        return

    widget.setProperty("modernPanelRoot", True)
    widget.setStyleSheet(modern_panel_stylesheet(app))
    widget.style().unpolish(widget)
    widget.style().polish(widget)

    try:
        from appGUI.GUIElements import FCFrame
    except ImportError:
        FCFrame = None

    if FCFrame is not None:
        for frame in widget.findChildren(FCFrame):
            if getattr(frame, "_color", None) is None and getattr(frame, "_b_color", None) is None:
                frame.setStyleSheet(modern_panel_frame_stylesheet(app))

    for combo in widget.findChildren(QtWidgets.QComboBox):
        view_attr = getattr(combo, "view", None)
        view = view_attr() if callable(view_attr) else view_attr
        if view is not None:
            view.setStyleSheet(modern_panel_stylesheet(app))


def apply_modern_main_workspace_style(ui, app=None):
    c = modern_panel_colors(app)

    ui.setObjectName("main_window")
    ui.setContentsMargins(14, 14, 14, 12)
    ui.setStyleSheet(f"""
        QMainWindow#main_window {{
            background: {c['app_bg']};
        }}
    """)

    for name in ["splitter", "splitter_left", "right_widget", "properties_sidebar", "plot_tab", "project_tab",
                 "project_frame", "properties_tab", "plugin_tab"]:
        widget = getattr(ui, name, None)
        if widget is None:
            continue
        object_name = widget.objectName() or name
        widget.setObjectName(object_name)
        if isinstance(widget, QtWidgets.QSplitter):
            if object_name == "splitter":
                widget.setHandleWidth(12)
                widget.setContentsMargins(0, 8, 0, 0)
                widget.setCollapsible(0, False)
            widget.setStyleSheet(f"""
                QSplitter#{object_name} {{
                    background: {c['app_bg']};
                    border: 0px;
                }}
                QSplitter#{object_name}::handle {{
                    background: {c['app_bg']};
                    margin: 0px;
                }}
            """)
        elif object_name == "project_frame":
            widget.setStyleSheet(f"""
                QFrame#project_frame {{
                    background: {c['surface']};
                    border: 0px;
                    border-radius: 10px;
                }}
            """)
        elif object_name == "right_properties_sidebar":
            widget.setStyleSheet(f"""
                QFrame#right_properties_sidebar {{
                    background: {c['surface']};
                    border: 1px solid {c['border']};
                    border-radius: 12px;
                }}
                QFrame#right_properties_header {{
                    background: {c['subtle']};
                    border: 0px;
                    border-radius: 8px;
                }}
                QLabel#right_properties_title {{
                    color: {c['text']};
                    font-weight: 600;
                }}
                QToolButton#right_properties_close_btn {{
                    background: transparent;
                    color: {c['hint']};
                    border: 1px solid transparent;
                    border-radius: 6px;
                    min-width: 24px;
                    min-height: 24px;
                }}
                QToolButton#right_properties_close_btn:hover {{
                    background: {c['hover']};
                    color: {c['selected_text']};
                    border-color: {c['hover_border']};
                }}
            """)
        else:
            background = c['app_bg'] if object_name == "right_widget" else c['surface']
            widget.setStyleSheet(
                f"QWidget#{object_name} {{ background: {background}; color: {c['text']}; border-radius: 10px; }}"
            )

    right_widget = getattr(ui, "right_widget", None)
    if right_widget is not None:
        right_widget.setObjectName("right_widget")

    for name in ["right_lay", "right_layout", "project_frame_lay", "project_tab_layout",
                 "properties_tab_layout", "plugin_tab_layout"]:
        layout = getattr(ui, name, None)
        if layout is None:
            continue
        if name in ["right_lay", "right_layout"]:
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10 if name == "right_lay" else 0)
        elif name == "project_frame_lay":
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(0)
        elif name == "project_tab_layout":
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        else:
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(10)

    notebook = getattr(ui, "notebook", None)
    if notebook is not None:
        notebook.setObjectName("left_sidebar")
        notebook.setMinimumWidth(320)
        notebook.setStyleSheet(modern_workspace_tab_area_stylesheet(app, "left_sidebar"))
        tab_bar = _resolve_tab_bar(notebook)
        if tab_bar is not None:
            tab_bar.setObjectName("left_sidebar_tab_bar")
            tab_bar.setProperty("expand_to_widget_width", True)
            tab_bar.setExpanding(True)
            tab_bar.setStyleSheet(modern_workspace_tabbar_stylesheet(app, min_width=82, expanding=True))
            tab_bar.updateGeometry()

    plot_tab_area = getattr(ui, "plot_tab_area", None)
    if plot_tab_area is not None:
        plot_tab_area.setObjectName("plot_tab_area")
        plot_tab_area.setContentsMargins(0, 0, 0, 0)
        plot_tab_area.setStyleSheet(modern_workspace_tab_area_stylesheet(app, "plot_tab_area"))
        tab_bar = _resolve_tab_bar(plot_tab_area)
        if tab_bar is not None:
            tab_bar.setObjectName("plot_tab_bar")
            tab_bar.setProperty("expand_to_widget_width", False)
            tab_bar.setExpanding(False)
            tab_bar.setStyleSheet(modern_workspace_tabbar_stylesheet(app, min_width=98, expanding=False))
            tab_bar.updateGeometry()

    for name in ["properties_scroll_area", "plugin_scroll_area"]:
        apply_modern_sidebar_style(getattr(ui, name, None), app)

    project_view = getattr(getattr(app, "collection", None), "view", None)
    if project_view is not None:
        project_view.setObjectName("project_tree")
        project_view.setAlternatingRowColors(False)
        project_view.setStyleSheet(modern_project_view_stylesheet(app))


def apply_modern_preferences_style(ui, app=None):
    root = getattr(ui, "preferences_tab", None)
    if root is not None:
        apply_modern_panel_style(root, app)
        root.setStyleSheet(modern_panel_stylesheet(app))
        _normalize_preference_label_colors(root)

    tab_area = getattr(ui, "pref_tab_area", None)
    if tab_area is not None:
        tab_area.setObjectName("preferences_tab_area")
        tab_area.setStyleSheet(modern_preferences_tab_area_stylesheet(app))

        tab_bar = tab_area.tabBar()
        if tab_bar is not None:
            tab_bar.setObjectName("preferences_tab_bar")
            tab_bar.setStyleSheet(modern_preferences_tabbar_stylesheet(app))

    for name in [
        "pref_tab_layout", "general_tab_lay", "gerber_tab_lay",
        "excellon_tab_lay", "geometry_tab_lay", "cncjob_tab_lay",
        "plugins_eng_tab_lay", "tools_tab_lay", "tools2_tab_lay", "fa_tab_lay",
    ]:
        layout = getattr(ui, name, None)
        if layout is None:
            continue
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

    for name in [
        "pref_tab_bottom_layout", "pref_tab_bottom_layout_1", "pref_tab_bottom_layout_2",
    ]:
        layout = getattr(ui, name, None)
        if layout is not None:
            layout.setSpacing(8)

    scroll_names = [
        "general_scroll_area", "gerber_scroll_area", "excellon_scroll_area",
        "geometry_scroll_area", "cncjob_scroll_area", "plugins_engraving_scroll_area",
        "tools_scroll_area", "tools2_scroll_area", "fa_scroll_area",
    ]
    for name in scroll_names:
        scroll_area = getattr(ui, name, None)
        if scroll_area is None:
            continue
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: 0px; }")
        viewport = scroll_area.viewport()
        if viewport is not None:
            viewport.setStyleSheet("background: transparent;")

    form_names = [
        "general_pref_form", "gerber_pref_form", "excellon_pref_form",
        "geo_pref_form", "cncjob_pref_form", "plugin_eng_pref_form",
        "plugin_pref_form", "plugin2_pref_form", "util_pref_form",
    ]
    for name in form_names:
        form = getattr(ui, name, None)
        apply_modern_panel_style(form, app)
        _normalize_preference_label_colors(form)

    for name in [
        "pref_defaults_button", "pref_open_button", "clear_btn",
        "pref_apply_button", "pref_save_button", "pref_close_button",
    ]:
        button = getattr(ui, name, None)
        if button is None:
            continue
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(32)
        button.style().unpolish(button)
        button.style().polish(button)

    apply_button = getattr(ui, "pref_apply_button", None)
    if apply_button is not None:
        if apply_button.property("prefAlert") is None:
            apply_button.setProperty("prefAlert", False)
        apply_button.style().unpolish(apply_button)
        apply_button.style().polish(apply_button)


def apply_modern_sidebar_style(scroll_area, app=None):
    if scroll_area is None:
        return

    scroll_area.setStyleSheet(modern_sidebar_stylesheet(app))
    viewport = scroll_area.viewport()
    if viewport is not None:
        c = modern_panel_colors(app)
        viewport.setStyleSheet(f"background: {c['surface']}; border-radius: 8px;")
