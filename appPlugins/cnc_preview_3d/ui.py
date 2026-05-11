# FlatCAM Plus CNC 3D Preview Module
# License: FlatCAM Plus CNC 3D Preview Module Non-Commercial License.
# See appPlugins/cnc_preview_3d/LICENSE.

import builtins
import gettext
import os

from PyQt6 import QtCore, QtGui, QtWidgets

from appGUI.GUIElements import FCComboBox, FCLabel
from appPlugins.cnc_control.widgets import FluidStyleButton

from .renderer import CNCPreview3DCanvas
from .sections import DEFAULT_PREVIEW_SECTIONS

import appTranslation as fcTranslate

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class OrbitGizmoButton(QtWidgets.QToolButton):
    viewRequested = QtCore.pyqtSignal(str)

    def __init__(self, tooltip="", parent=None):
        super().__init__(parent)
        self.canvas = None
        self.face_paths = {}
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)
        self.setToolTip(tooltip)
        self.setFixedSize(128, 128)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.setInterval(80)
        self.refresh_timer.timeout.connect(self.update)
        self.refresh_timer.start()

    def set_canvas(self, canvas):
        self.canvas = canvas
        self.update()

    def rotated_axes(self):
        axes = [
            ("X", (1.0, 0.0, 0.0), QtGui.QColor("#e45757")),
            ("Y", (0.0, 1.0, 0.0), QtGui.QColor("#48a868")),
            ("Z", (0.0, 0.0, 1.0), QtGui.QColor("#3f8cff")),
        ]
        if self.canvas is None:
            return axes

        try:
            state = self.canvas.view.camera.get_state()
            quaternion = state.get("_quaternion")
            if quaternion is None:
                return axes
            return [
                (label, quaternion.inverse().rotate_point(vector), color)
                for label, vector, color in axes
            ]
        except Exception:
            return axes

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(5, 5, -5, -5)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(0, 0, 0, 32))
        painter.drawRoundedRect(rect.adjusted(3, 4, 3, 4), 8, 8)
        painter.setBrush(QtGui.QColor(255, 255, 255, 220 if self.underMouse() else 202))
        painter.drawRoundedRect(rect, 8, 8)

        cx = rect.center().x()
        top = rect.top() + 13
        left = cx - 36
        right = cx + 36
        mid_y = top + 24
        lower_y = top + 84
        cube_center = QtCore.QPointF(cx, top + 48)

        def path_from(points):
            path = QtGui.QPainterPath()
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)
            path.closeSubpath()
            return path

        top_path = path_from([
            QtCore.QPointF(cx, top),
            QtCore.QPointF(right, mid_y),
            QtCore.QPointF(cx, top + 48),
            QtCore.QPointF(left, mid_y),
        ])
        front_path = path_from([
            QtCore.QPointF(left, mid_y),
            QtCore.QPointF(cx, top + 48),
            QtCore.QPointF(cx, lower_y),
            QtCore.QPointF(left, lower_y - 24),
        ])
        right_path = path_from([
            QtCore.QPointF(right, mid_y),
            QtCore.QPointF(cx, top + 48),
            QtCore.QPointF(cx, lower_y),
            QtCore.QPointF(right, lower_y - 24),
        ])
        self.face_paths = {"top": top_path, "front": front_path, "right": right_path}

        painter.setPen(QtGui.QPen(QtGui.QColor(74, 82, 82, 150), 1))
        faces = [
            (front_path, QtGui.QColor("#dfe7e3"), _("Front")),
            (right_path, QtGui.QColor("#cfdad6"), _("Right")),
            (top_path, QtGui.QColor("#f3f6f4"), _("Top")),
        ]
        painter.setFont(QtGui.QFont(painter.font().family(), 7, QtGui.QFont.Weight.Bold))
        for path, color, label in faces:
            painter.setBrush(color)
            painter.drawPath(path)
            painter.setPen(QtGui.QColor("#303838"))
            painter.drawText(path.boundingRect(), QtCore.Qt.AlignmentFlag.AlignCenter, label)
            painter.setPen(QtGui.QPen(QtGui.QColor(74, 82, 82, 150), 1))

        painter.setBrush(QtGui.QColor(255, 255, 255, 235))
        painter.drawEllipse(cube_center, 10, 10)
        painter.setPen(QtGui.QColor("#303838"))
        painter.drawText(
            QtCore.QRectF(cube_center.x() - 8, cube_center.y() - 8, 16, 16),
            QtCore.Qt.AlignmentFlag.AlignCenter,
            "3D"
        )

        self.draw_axis_tripod(painter, rect)
        self.draw_view_badges(painter, rect)

    def draw_axis_tripod(self, painter, rect):
        center = QtCore.QPointF(rect.left() + 24, rect.bottom() - 23)
        radius = 15
        axes = []
        for label, vector, color in self.rotated_axes():
            x, y, z = vector
            point = QtCore.QPointF(center.x() + x * radius, center.y() - y * radius)
            axes.append((label, point, z, color))

        painter.setFont(QtGui.QFont(painter.font().family(), 6, QtGui.QFont.Weight.Bold))
        for label, point, _z, color in sorted(axes, key=lambda item: item[2]):
            painter.setPen(QtGui.QPen(color, 2))
            painter.drawLine(center, point)
            painter.setBrush(color)
            painter.drawEllipse(point, 5, 5)
            painter.setPen(QtGui.QColor("white"))
            painter.drawText(QtCore.QRectF(point.x() - 4, point.y() - 4, 8, 8), QtCore.Qt.AlignmentFlag.AlignCenter, label)

    def draw_view_badges(self, painter, rect):
        badges = [
            ("left", "L", rect.right() - 59, rect.bottom() - 25),
            ("back", "B", rect.right() - 38, rect.bottom() - 25),
            ("bottom", "D", rect.right() - 17, rect.bottom() - 25),
        ]
        painter.setFont(QtGui.QFont(painter.font().family(), 7, QtGui.QFont.Weight.Bold))
        for view_name, label, x_pos, y_pos in badges:
            badge_rect = QtCore.QRectF(x_pos - 8, y_pos - 8, 16, 16)
            path = QtGui.QPainterPath()
            path.addEllipse(badge_rect)
            self.face_paths[view_name] = path
            painter.setPen(QtGui.QPen(QtGui.QColor(74, 82, 82, 145), 1))
            painter.setBrush(QtGui.QColor(245, 248, 248, 232))
            painter.drawEllipse(badge_rect)
            painter.setPen(QtGui.QColor("#303838"))
            painter.drawText(badge_rect, QtCore.Qt.AlignmentFlag.AlignCenter, label)

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return

        pos = QtCore.QPointF(event.position())
        for view_name, path in self.face_paths.items():
            if path.contains(pos):
                self.viewRequested.emit(view_name)
                return
        self.viewRequested.emit("iso")


class CNCPreview3DUI:
    pluginName = _("CNC 3D Preview")

    def __init__(self, layout, app):
        self.app = app
        self.layout = layout
        self.section_plugins = {
            key: section_cls() for key, section_cls in DEFAULT_PREVIEW_SECTIONS.items()
        }

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.container = QtWidgets.QWidget()
        self.container.setObjectName("cnc_preview_3d_root")
        self.container.setStyleSheet(self.stylesheet())
        self.layout.addWidget(self.container)

        self.main_lay = QtWidgets.QVBoxLayout(self.container)
        self.main_lay.setContentsMargins(0, 0, 0, 0)
        self.main_lay.setSpacing(0)

        self.build_controls()
        self.build_layout()

    def stylesheet(self):
        palette = QtWidgets.QApplication.palette()
        window = palette.color(QtGui.QPalette.ColorRole.Window).name()
        base = palette.color(QtGui.QPalette.ColorRole.Base).name()
        text = palette.color(QtGui.QPalette.ColorRole.WindowText).name()
        mid = palette.color(QtGui.QPalette.ColorRole.Mid).name()
        hover = palette.color(QtGui.QPalette.ColorRole.AlternateBase).name()
        arrow_icon = os.path.join(self.app.resource_location, "down-arrow32.png").replace("\\", "/")

        return f"""
            QWidget#cnc_preview_3d_root {{
                background: transparent;
            }}
            QGroupBox#preview_panel {{
                background: {window};
                border: 1px solid {mid};
                border-radius: 6px;
                margin-top: 13px;
                padding: 9px 8px 8px 8px;
                font-weight: 600;
            }}
            QGroupBox#preview_panel::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 8px;
                padding: 0 5px;
                color: {text};
            }}
            QFrame#preview_canvas_frame {{
                background: #f3f5f1;
                border: 0px;
                border-radius: 0px;
            }}
            QFrame#preview_view_overlay {{
                background: transparent;
                border: 0;
            }}
            QComboBox {{
                min-height: 30px;
                padding: 4px 30px 4px 8px;
                border: 1px solid {mid};
                border-radius: 5px;
                background: {base};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border: 0;
            }}
            QComboBox::down-arrow {{
                image: url("{arrow_icon}");
                width: 10px;
                height: 10px;
            }}
            QLabel#preview_status {{
                color: {text};
                background: {hover};
                border: 1px solid {mid};
                border-radius: 5px;
                padding: 6px;
            }}
        """

    def build_controls(self):
        self.job_combo = FCComboBox()
        self.job_combo.setMinimumHeight(32)
        self.job_combo.setMinimumWidth(176)
        self.refresh_btn = FluidStyleButton(_("Refresh"), "#337ab7", "#286090")
        self.refresh_btn.setMinimumHeight(32)
        self.top_btn = FluidStyleButton(_("Top"), "#5bc0de", "#31b0d5")
        self.orbit_btn = OrbitGizmoButton(_("Orbit view"))
        self.fit_btn = FluidStyleButton(_("Fit"), "#5cb85c", "#449d44")
        self.top_btn.setToolTip(_("Top view"))
        self.top_btn.setFixedSize(42, 28)
        self.fit_btn.setToolTip(_("Fit view"))
        self.fit_btn.setFixedSize(42, 28)

        self.lines_value = FCLabel("-")
        self.cut_value = FCLabel("-")
        self.drill_value = FCLabel("-")
        self.bounds_value = FCLabel("-")
        self.status_label = FCLabel(_("No CNCJob rendered."))
        self.status_label.setObjectName("preview_status")

    def create_panel(self, title):
        panel = QtWidgets.QGroupBox(title)
        panel.setObjectName("preview_panel")
        lay = QtWidgets.QVBoxLayout(panel)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        return panel, lay

    def build_layout(self):
        splitter = QtWidgets.QSplitter()
        splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("""
            QSplitter {
                background: transparent;
                border: 0px;
            }
            QSplitter::handle {
                background: transparent;
                border: 0px;
            }
        """)
        self.main_lay.addWidget(splitter, 1)

        side = QtWidgets.QWidget()
        side_lay = QtWidgets.QVBoxLayout(side)
        side_lay.setContentsMargins(8, 8, 8, 8)
        side_lay.setSpacing(8)
        side_lay.addWidget(self.section_plugins["job_selector"].build_panel(self))
        side_lay.addWidget(self.section_plugins["render_info"].build_panel(self))
        side_lay.addStretch()
        splitter.addWidget(side)

        self.canvas_frame = QtWidgets.QFrame()
        self.canvas_frame.setObjectName("preview_canvas_frame")
        self.canvas_frame.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.canvas_frame.setLineWidth(0)
        canvas_lay = QtWidgets.QGridLayout(self.canvas_frame)
        canvas_lay.setContentsMargins(0, 0, 0, 0)
        canvas_lay.setSpacing(0)
        self.canvas = CNCPreview3DCanvas(self.app)
        self.canvas.native.setStyleSheet("background: #f3f5f1; border: 0px;")
        self.orbit_btn.set_canvas(self.canvas)
        canvas_lay.addWidget(self.canvas.native, 0, 0)
        self.view_overlay = self.build_view_overlay()
        canvas_lay.addWidget(
            self.view_overlay,
            0,
            0,
            alignment=QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignRight
        )
        splitter.addWidget(self.canvas_frame)
        splitter.setSizes([280, 980])
        splitter.setStretchFactor(1, 1)

    def build_view_overlay(self):
        overlay = QtWidgets.QFrame()
        overlay.setObjectName("preview_view_overlay")
        overlay.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Maximum)
        lay = QtWidgets.QVBoxLayout(overlay)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(4)
        lay.addWidget(self.orbit_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        view_row = QtWidgets.QHBoxLayout()
        view_row.setContentsMargins(0, 0, 0, 0)
        view_row.setSpacing(4)
        view_row.addWidget(self.top_btn)
        view_row.addWidget(self.fit_btn)
        lay.addLayout(view_row)
        return overlay

    def update_stats(self, result):
        self.lines_value.setText(str(result.get("line_count", 0)))
        self.cut_value.setText(str(result.get("cut_count", 0)))
        self.drill_value.setText(str(result.get("drill_count", 0)))
        self.bounds_value.setText(result.get("bounds", "-"))
        self.status_label.setText(_("Rendered: %s") % result.get("name", "-"))

    def set_status(self, message):
        self.status_label.setText(message)
