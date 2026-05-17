# FlatCAM Plus CNC Control Module
# License: FlatCAM Plus CNC Control Module Non-Commercial License.
# See appPlugins/cnc_control/LICENSE.

import math

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import Qt


class FluidStyleButton(QtWidgets.QToolButton):
    def __init__(self, text="", color="#31b0d5", hover="#269abc", text_color="white", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIconSize(QtCore.QSize(18, 18))
        self.setMinimumHeight(28)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)


class GCodeJobCanvas(QtWidgets.QWidget):
    full_screen_requested = QtCore.pyqtSignal()
    placement_changed = QtCore.pyqtSignal(float, float, float) # dx, dy, rotation

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preview = {}
        self.setMinimumSize(360, 280)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        
        # Pan and Zoom state
        self.offset = QtCore.QPointF(0, 0)
        self.zoom = 1.0
        self.last_mouse_pos = None
        self.is_panning = False
        self.enable_fs_button = True

        # Live Placement state
        self.edit_mode = False
        self.live_offset = QtCore.QPointF(0, 0)
        self.live_rotation = 0.0
        self.is_dragging_object = False
        self.is_rotating_object = False
        self.drag_start_pos = None
        self.rotation_handle_rect = QtCore.QRectF()

    def set_preview(self, preview):
        self.preview = preview or {}
        # Reset pan/zoom only if not in edit mode or if it's a completely different job
        # For now, let's just keep them to allow seamless editing
        # self.offset = QtCore.QPointF(0, 0)
        # self.zoom = 1.0
        self.update()

    def sync_placement(self, dx, dy, rotation):
        self.live_offset = QtCore.QPointF(dx, dy)
        self.live_rotation = rotation
        self.update()

    @staticmethod
    def nice_grid_step(span):
        if span <= 0: return 10.0
        raw_step = span / 8.0
        magnitude = 10 ** math.floor(math.log10(raw_step))
        for multiplier in [1, 2, 5, 10]:
            step = multiplier * magnitude
            if raw_step <= step: return step
        return 10 * magnitude

    def job_bounds_values(self):
        bounds = self.preview.get("job_bounds") or [0, 100, 0, 100]
        try:
            x_min, x_max, y_min, y_max = [float(v) for v in bounds]
        except (TypeError, ValueError):
            x_min, x_max, y_min, y_max = 0.0, 100.0, 0.0, 100.0
        if abs(x_max - x_min) < 1e-9:
            x_max = x_min + 0.1
        if abs(y_max - y_min) < 1e-9:
            y_max = y_min + 0.1
        return x_min, x_max, y_min, y_max

    def object_bounds_values(self):
        bounds = self.preview.get("path_bounds") or self.preview.get("object_bounds")
        if bounds:
            try:
                x_min, x_max, y_min, y_max = [float(v) for v in bounds]
                if abs(x_max - x_min) >= 1e-9 and abs(y_max - y_min) >= 1e-9:
                    return x_min, x_max, y_min, y_max
            except (TypeError, ValueError):
                pass
        return self.job_bounds_values()

    def canvas_transform(self):
        canvas_rect = self.rect().adjusted(4, 4, -4, -4)
        x_min, x_max, y_min, y_max = self.job_bounds_values()
        span_x = max(0.1, x_max - x_min)
        span_y = max(0.1, y_max - y_min)
        base_scale = min(canvas_rect.width() / span_x, canvas_rect.height() / span_y) * 0.9
        return canvas_rect, x_min, x_max, y_min, y_max, max(1e-9, base_scale * self.zoom)

    def world_to_canvas(self, x, y):
        canvas_rect, x_min, x_max, y_min, y_max, total_scale = self.canvas_transform()
        px = canvas_rect.center().x() + (float(x) - (x_min + x_max) / 2) * total_scale + self.offset.x()
        py = canvas_rect.center().y() - (float(y) - (y_min + y_max) / 2) * total_scale + self.offset.y()
        return QtCore.QPointF(px, py)

    def live_object_xy(self, x, y):
        obj_x_min, obj_x_max, obj_y_min, obj_y_max = self.object_bounds_values()
        cx, cy = (obj_x_min + obj_x_max) / 2.0, (obj_y_min + obj_y_max) / 2.0
        rx, ry = float(x), float(y)

        if self.live_rotation != 0:
            rad = math.radians(self.live_rotation)
            tx, ty = rx - cx, ry - cy
            rx = tx * math.cos(rad) - ty * math.sin(rad) + cx
            ry = tx * math.sin(rad) + ty * math.cos(rad) + cy

        return rx + self.live_offset.x(), ry + self.live_offset.y()

    def object_to_canvas(self, x, y):
        return self.world_to_canvas(*self.live_object_xy(x, y))

    @staticmethod
    def points_are_close(point_a, point_b, tolerance=0.001):
        try:
            return (
                abs(float(point_a[0]) - float(point_b[0])) <= tolerance and
                abs(float(point_a[1]) - float(point_b[1])) <= tolerance
            )
        except (TypeError, ValueError, IndexError):
            return False

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        palette = self.palette()
        text_color = palette.color(QtGui.QPalette.ColorRole.WindowText)

        if not self.preview or not self.preview.get("segments"):
            painter.setPen(QtGui.QColor("#777777"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No Preview Available")
            return

        outer = self.rect()
        canvas_rect = outer.adjusted(4, 4, -4, -4)

        # Draw Background
        painter.setBrush(QtGui.QColor("#fbfdff") if text_color.lightness() > 128 else QtGui.QColor("#1e1e1e"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#b8c2d0"), 1.2))
        painter.drawRect(canvas_rect)

        # Full Screen Button
        if self.enable_fs_button:
            fs_rect = QtCore.QRect(outer.right() - 28, outer.top() + 8, 20, 18)
            painter.setBrush(QtGui.QColor("#337ab7"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QtCore.QRectF(fs_rect), 3, 3)
            painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 1.2))
            painter.drawPolyline([
                QtCore.QPoint(fs_rect.left()+4, fs_rect.top()+7),
                QtCore.QPoint(fs_rect.left()+4, fs_rect.top()+4),
                QtCore.QPoint(fs_rect.left()+7, fs_rect.top()+4)
            ])
            painter.drawPolyline([
                QtCore.QPoint(fs_rect.right()-4, fs_rect.top()+7),
                QtCore.QPoint(fs_rect.right()-4, fs_rect.top()+4),
                QtCore.QPoint(fs_rect.right()-7, fs_rect.top()+4)
            ])
            painter.drawPolyline([
                QtCore.QPoint(fs_rect.left()+4, fs_rect.bottom()-7),
                QtCore.QPoint(fs_rect.left()+4, fs_rect.bottom()-4),
                QtCore.QPoint(fs_rect.left()+7, fs_rect.bottom()-4)
            ])
            painter.drawPolyline([
                QtCore.QPoint(fs_rect.right()-4, fs_rect.bottom()-7),
                QtCore.QPoint(fs_rect.right()-4, fs_rect.bottom()-4),
                QtCore.QPoint(fs_rect.right()-7, fs_rect.bottom()-4)
            ])

        # Bounds calculation
        x_min, x_max, y_min, y_max = self.job_bounds_values()
        obj_x_min, obj_x_max, obj_y_min, obj_y_max = self.object_bounds_values()
        span_x = max(0.1, x_max - x_min)
        span_y = max(0.1, y_max - y_min)
        total_scale = self.canvas_transform()[5]

        def to_canvas(x, y):
            return self.world_to_canvas(x, y)

        def to_object_canvas(x, y):
            return self.object_to_canvas(x, y)

        origin_xy = self.preview.get("origin") or [0.0, 0.0]

        def to_segment_canvas(point, rapid=False):
            if self.edit_mode and rapid and self.points_are_close(point, origin_xy):
                return to_canvas(point[0], point[1])
            return to_object_canvas(point[0], point[1])

        painter.setClipRect(canvas_rect)

        # 1. Draw Job/Material Outline (The PCB Board Area)
        job_pen = QtGui.QPen(QtGui.QColor("#5bc0de"), 2, Qt.PenStyle.SolidLine)
        painter.setPen(job_pen)
        painter.setBrush(QtGui.QColor("#fcfdfd") if text_color.lightness() > 128 else QtGui.QColor("#252525"))
        p_bl = to_canvas(x_min, y_min)
        p_tr = to_canvas(x_max, y_max)
        painter.drawRect(QtCore.QRectF(p_bl, p_tr).normalized())

        # 2. Draw Margin Guides (Origin/Placement Guides)
        margin_guides = self.preview.get("margin_guides", [])
        painter.setPen(QtGui.QPen(QtGui.QColor("#f0ad4e"), 1, Qt.PenStyle.DashLine))
        for guide in margin_guides:
            if guide["axis"] == "X":
                p1, p2 = to_canvas(guide["value"], y_min), to_canvas(guide["value"], y_max)
                painter.drawLine(p1, p2)
            else:
                p1, p2 = to_canvas(x_min, guide["value"]), to_canvas(x_max, guide["value"])
                painter.drawLine(p1, p2)

        # 3. Draw Grid (Subtle)
        grid_step = self.nice_grid_step(max(span_x, span_y))
        painter.setPen(QtGui.QPen(QtGui.QColor("#dce2ea") if text_color.lightness() > 128 else QtGui.QColor("#333333"), 1))
        curr_x = math.ceil(x_min / grid_step) * grid_step
        while curr_x <= x_max:
            p1, p2 = to_canvas(curr_x, y_min), to_canvas(curr_x, y_max)
            painter.drawLine(p1, p2)
            curr_x += grid_step
        curr_y = math.ceil(y_min / grid_step) * grid_step
        while curr_y <= y_max:
            p1, p2 = to_canvas(x_min, curr_y), to_canvas(x_max, curr_y)
            painter.drawLine(p1, p2)
            curr_y += grid_step

        # 4. Draw G-Code Path Bounds (If outside job)
        if self.preview.get("outside"):
            path_bounds = self.preview.get("path_bounds")
            if path_bounds:
                painter.setPen(QtGui.QPen(QtGui.QColor("#d9534f"), 1, Qt.PenStyle.DotLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                p_bl = to_object_canvas(path_bounds[0], path_bounds[2])
                p_tr = to_object_canvas(path_bounds[1], path_bounds[3])
                painter.drawRect(QtCore.QRectF(p_bl, p_tr).normalized())

        # 5. Draw G-Code Segments
        rapid_pen = QtGui.QPen(QtGui.QColor("#9aa6b5"), 1, Qt.PenStyle.DashLine)
        cut_pen = QtGui.QPen(QtGui.QColor("#3156d9"), max(2.0, total_scale * 0.1), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        for seg in self.preview.get("segments", []):
            is_rapid = bool(seg.get("rapid"))
            painter.setPen(rapid_pen if is_rapid else cut_pen)
            painter.drawLine(
                to_segment_canvas(seg["start"], is_rapid),
                to_segment_canvas(seg["end"], is_rapid)
            )

        # 6. Origin Marker (0,0 of Work CS)
        origin_pt = to_canvas(0, 0)
        painter.setPen(QtGui.QPen(QtGui.QColor("#d9534f"), 2))
        painter.drawLine(QtCore.QPointF(origin_pt.x() - 10, origin_pt.y()), QtCore.QPointF(origin_pt.x() + 10, origin_pt.y()))
        painter.drawLine(QtCore.QPointF(origin_pt.x(), origin_pt.y() - 10), QtCore.QPointF(origin_pt.x(), origin_pt.y() + 10))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(origin_pt, 5, 5)

        # 7. Live Spindle (Current Tool Position)
        pos = self.preview.get("live_pos")
        if pos:
            spindle_pt = to_canvas(pos.get("X", 0), pos.get("Y", 0))
            painter.setBrush(QtGui.QColor("#d9534f"))
            painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 1.5))
            painter.drawEllipse(spindle_pt, 6, 6)
            # Crosshair
            painter.setPen(QtGui.QPen(QtGui.QColor("#d9534f"), 1))
            painter.drawLine(QtCore.QPointF(spindle_pt.x() - 15, spindle_pt.y()), QtCore.QPointF(spindle_pt.x() + 15, spindle_pt.y()))
            painter.drawLine(QtCore.QPointF(spindle_pt.x(), spindle_pt.y() - 15), QtCore.QPointF(spindle_pt.x(), spindle_pt.y() + 15))

        painter.setClipping(False)

        # 8. Draw Rotation Handle and Bounding Box if editing
        if self.edit_mode:
            # Draw a bounding box for the object being placed
            p1 = to_object_canvas(obj_x_min, obj_y_min)
            p2 = to_object_canvas(obj_x_max, obj_y_max)
            painter.setPen(QtGui.QPen(QtGui.QColor("#ff6900"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QtCore.QRectF(p1, p2).normalized())

            # Handle is above the object
            obj_span_y = max(0.1, obj_y_max - obj_y_min)
            handle_center = (obj_x_min + obj_x_max) / 2, obj_y_max + max(2.0, obj_span_y * 0.1)
            handle_pt = to_object_canvas(*handle_center)
            self.rotation_handle_rect = QtCore.QRectF(handle_pt.x() - 10, handle_pt.y() - 10, 20, 20)

            painter.setPen(QtGui.QPen(QtGui.QColor("#ff6900"), 2))
            painter.setBrush(QtGui.QColor("#ffffff"))
            painter.drawEllipse(self.rotation_handle_rect)
            painter.setBrush(QtGui.QColor("#ff6900"))
            painter.drawEllipse(handle_pt, 3, 3)

            # Line to object
            painter.drawLine(handle_pt, to_object_canvas((obj_x_min + obj_x_max) / 2, obj_y_max))

        # Draw Info Label at Top Left
        label = self.preview.get("label", "")
        if self.edit_mode:
            label = "[LIVE PLACEMENT MODE] " + (label or "Job")

        if label:
            painter.setPen(QtGui.QColor("#ff6900") if self.edit_mode else text_color)
            painter.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Weight.Bold if self.edit_mode else QtGui.QFont.Weight.Normal))
            painter.drawText(canvas_rect.adjusted(6, 4, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, label)

    def wheelEvent(self, event):
        angle = event.angleDelta().y()
        factor = 1.1 if angle > 0 else 0.9
        self.zoom *= factor
        self.zoom = max(0.1, min(self.zoom, 50.0))
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        pos_f = QtCore.QPointF(event.pos())
        if event.button() == Qt.MouseButton.LeftButton:
            outer = self.rect()
            fs_rect = QtCore.QRect(outer.right() - 28, outer.top() + 8, 20, 18)
            if self.enable_fs_button and fs_rect.contains(event.pos()):
                self.full_screen_requested.emit()
                return

            if self.edit_mode:
                if hasattr(self, 'rotation_handle_rect') and self.rotation_handle_rect.contains(pos_f):
                    self.is_rotating_object = True
                    self.last_mouse_pos = event.pos()
                    return

                self.is_dragging_object = True
                self.drag_start_pos = event.pos()
                self.last_mouse_pos = event.pos()
                return

            self.is_panning = True
            self.last_mouse_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_panning and self.last_mouse_pos:
            delta = event.pos() - self.last_mouse_pos
            self.offset += QtCore.QPointF(delta)
            self.last_mouse_pos = event.pos()
            self.update()
        elif self.is_rotating_object and self.last_mouse_pos:
            obj_x_min, obj_x_max, obj_y_min, obj_y_max = self.object_bounds_values()
            center_world = (obj_x_min + obj_x_max) / 2.0, (obj_y_min + obj_y_max) / 2.0
            center_pt = self.object_to_canvas(*center_world)
            p1 = QtCore.QPointF(self.last_mouse_pos) - center_pt
            p2 = QtCore.QPointF(event.pos()) - center_pt
            angle1 = math.atan2(p1.y(), p1.x())
            angle2 = math.atan2(p2.y(), p2.x())
            diff = math.degrees(angle2 - angle1)
            self.live_rotation += diff
            self.last_mouse_pos = event.pos()
            self.placement_changed.emit(self.live_offset.x(), self.live_offset.y(), self.live_rotation)
            self.update()
        elif self.is_dragging_object and self.last_mouse_pos:
            delta = event.pos() - self.last_mouse_pos
            job_bounds = self.preview.get("job_bounds") or [0, 100, 0, 100]
            span_x = max(0.1, float(job_bounds[1]) - float(job_bounds[0]))
            span_y = max(0.1, float(job_bounds[3]) - float(job_bounds[2]))
            canvas_rect = self.rect().adjusted(4, 4, -4, -4)
            base_scale = min(canvas_rect.width() / span_x, canvas_rect.height() / span_y) * 0.9
            total_scale = max(1e-9, base_scale * self.zoom)
            dx = delta.x() / total_scale
            dy = -delta.y() / total_scale
            self.live_offset += QtCore.QPointF(dx, dy)
            self.last_mouse_pos = event.pos()
            self.placement_changed.emit(self.live_offset.x(), self.live_offset.y(), self.live_rotation)
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_panning = False
            self.is_dragging_object = False
            self.is_rotating_object = False
            self.last_mouse_pos = None
        super().mouseReleaseEvent(event)


class DashboardGauge(QtWidgets.QWidget):
    def __init__(self, title, unit, max_value, accent="#31b0d5", parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.max_value = float(max_value)
        self.accent = QtGui.QColor(accent)
        self._value = 0.0
        self._target = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._animate_value)
        self.setMinimumSize(150, 170)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

    def set_value(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        self._target = max(0.0, value)
        if not self._timer.isActive():
            self._timer.start()

    def _animate_value(self):
        delta = self._target - self._value
        if abs(delta) < 0.5:
            self._value = self._target
            self._timer.stop()
        else:
            self._value += delta * 0.18
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        palette = self.palette()
        text_color = palette.color(QtGui.QPalette.ColorRole.WindowText)
        mid_color = palette.color(QtGui.QPalette.ColorRole.Mid)
        base_color = palette.color(QtGui.QPalette.ColorRole.Base)

        rect = self.rect().adjusted(6, 4, -6, -4)
        painter.setPen(QtGui.QPen(mid_color, 1))
        painter.setBrush(base_color)
        painter.drawRoundedRect(QtCore.QRectF(rect), 6, 6)

        title_font = QtGui.QFont(painter.font())
        title_font.setBold(True)
        title_font.setPointSize(max(8, title_font.pointSize()))
        painter.setFont(title_font)
        painter.setPen(text_color)
        painter.drawText(rect.adjusted(0, 4, 0, 0), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self.title)

        gauge_top = rect.top() + 24
        gauge_bottom = rect.bottom() - 30
        gauge_height = max(40, gauge_bottom - gauge_top)
        side = min(rect.width() - 26, gauge_height)
        arc_rect = QtCore.QRectF(
            rect.center().x() - side / 2,
            gauge_top + (gauge_height - side) / 2,
            side,
            side
        )

        track_pen = QtGui.QPen(mid_color.lighter(135), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(arc_rect, 225 * 16, -270 * 16)

        segment_span = -90 * 16
        for start, color in [
            (225, "#4cc26f"),
            (135, "#f0c04a"),
            (45, "#e85d5d"),
        ]:
            painter.setPen(QtGui.QPen(QtGui.QColor(color), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(arc_rect, start * 16, segment_span)

        ratio = 0.0 if self.max_value <= 0 else self._value / self.max_value
        ratio = max(0.0, min(ratio, 1.0))
        painter.setPen(QtGui.QPen(self.accent, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(arc_rect.adjusted(7, 7, -7, -7), 225 * 16, int(-270 * ratio * 16))

        center = QtCore.QPointF(arc_rect.center().x(), arc_rect.center().y() + side * 0.12)
        needle_radius = side * 0.36
        angle = 225 - (270 * ratio)
        rad = angle * 3.141592653589793 / 180.0
        needle_end = QtCore.QPointF(
            center.x() + needle_radius * math.cos(rad),
            center.y() - needle_radius * math.sin(rad)
        )
        painter.setPen(QtGui.QPen(text_color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(center, needle_end)
        painter.setBrush(self.accent)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, 4, 4)

        value_font = QtGui.QFont(painter.font())
        value_font.setBold(True)
        value_font.setPointSize(11)
        painter.setFont(value_font)
        painter.setPen(text_color)
        value_text = "%d %s" % (round(self._value), self.unit)
        painter.drawText(rect.adjusted(0, 0, 0, -8), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, value_text)
