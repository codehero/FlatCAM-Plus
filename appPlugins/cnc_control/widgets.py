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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.preview = {}
        self.setMinimumSize(360, 280)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

    def set_preview(self, preview):
        self.preview = preview or {}
        self.update()

    @staticmethod
    def nice_grid_step(span):
        if span <= 0:
            return 10.0
        raw_step = span / 8.0
        magnitude = 10 ** math.floor(math.log10(raw_step))
        for multiplier in [1, 2, 5, 10]:
            step = multiplier * magnitude
            if raw_step <= step:
                return step
        return 10 * magnitude

    @staticmethod
    def draw_cross(painter, point, radius, color):
        painter.setPen(QtGui.QPen(QtGui.QColor(color), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QtCore.QPointF(point.x() - radius, point.y()), QtCore.QPointF(point.x() + radius, point.y()))
        painter.drawLine(QtCore.QPointF(point.x(), point.y() - radius), QtCore.QPointF(point.x(), point.y() + radius))

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        palette = self.palette()
        base_color = palette.color(QtGui.QPalette.ColorRole.Base)
        text_color = palette.color(QtGui.QPalette.ColorRole.WindowText)
        mid_color = palette.color(QtGui.QPalette.ColorRole.Mid)

        outer = self.rect().adjusted(4, 4, -4, -4)
        painter.setPen(QtGui.QPen(mid_color, 1))
        painter.setBrush(base_color)
        painter.drawRoundedRect(QtCore.QRectF(outer), 8, 8)

        job_bounds = self.preview.get("job_bounds")
        if not job_bounds:
            painter.setPen(QtGui.QPen(text_color))
            painter.drawText(outer, Qt.AlignmentFlag.AlignCenter, "No job canvas preview")
            return

        x_min, x_max, y_min, y_max = [float(value) for value in job_bounds]
        job_width = x_max - x_min
        job_height = y_max - y_min
        if job_width <= 0 or job_height <= 0:
            painter.setPen(QtGui.QPen(text_color))
            painter.drawText(outer, Qt.AlignmentFlag.AlignCenter, "Invalid job size")
            return

        header_height = 24
        drawing_area = outer.adjusted(14, header_height + 8, -14, -14)
        scale = min(drawing_area.width() / job_width, drawing_area.height() / job_height)
        if scale <= 0:
            return

        canvas_width = job_width * scale
        canvas_height = job_height * scale
        canvas_rect = QtCore.QRectF(
            drawing_area.center().x() - canvas_width / 2,
            drawing_area.center().y() - canvas_height / 2,
            canvas_width,
            canvas_height
        )

        def to_canvas(x_value, y_value):
            return QtCore.QPointF(
                canvas_rect.left() + (float(x_value) - x_min) * scale,
                canvas_rect.bottom() - (float(y_value) - y_min) * scale
            )

        header = self.preview.get("label", "")
        painter.setPen(QtGui.QPen(text_color))
        header_text = painter.fontMetrics().elidedText(
            header,
            Qt.TextElideMode.ElideRight,
            max(20, outer.width() - 24)
        )
        painter.drawText(outer.adjusted(12, 5, -12, 0), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, header_text)

        painter.setBrush(QtGui.QColor("#fbfdff"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#b8c2d0"), 1.2))
        painter.drawRect(canvas_rect)

        grid_step = self.nice_grid_step(max(job_width, job_height))
        grid_pen = QtGui.QPen(QtGui.QColor("#dce2ea"), 1)
        painter.setPen(grid_pen)

        first_x = math.ceil(x_min / grid_step) * grid_step
        value = first_x
        while value <= x_max + 1e-9:
            point_a = to_canvas(value, y_min)
            point_b = to_canvas(value, y_max)
            painter.drawLine(point_a, point_b)
            value += grid_step

        first_y = math.ceil(y_min / grid_step) * grid_step
        value = first_y
        while value <= y_max + 1e-9:
            point_a = to_canvas(x_min, value)
            point_b = to_canvas(x_max, value)
            painter.drawLine(point_a, point_b)
            value += grid_step

        margin_pen = QtGui.QPen(QtGui.QColor("#f0ad4e"), 1.3, Qt.PenStyle.DashLine)
        painter.setPen(margin_pen)
        for guide in self.preview.get("margin_guides", []):
            axis = guide.get("axis")
            guide_value = float(guide.get("value", 0.0))
            if axis == "X" and x_min <= guide_value <= x_max:
                painter.drawLine(to_canvas(guide_value, y_min), to_canvas(guide_value, y_max))
            elif axis == "Y" and y_min <= guide_value <= y_max:
                painter.drawLine(to_canvas(x_min, guide_value), to_canvas(x_max, guide_value))

        axis_pen = QtGui.QPen(QtGui.QColor("#d9534f"), 1.1, Qt.PenStyle.DashLine)
        painter.setPen(axis_pen)
        if x_min <= 0 <= x_max:
            painter.drawLine(to_canvas(0, y_min), to_canvas(0, y_max))
        if y_min <= 0 <= y_max:
            painter.drawLine(to_canvas(x_min, 0), to_canvas(x_max, 0))

        painter.save()
        painter.setClipRect(canvas_rect.adjusted(1, 1, -1, -1))

        rapid_pen = QtGui.QPen(QtGui.QColor("#9aa6b5"), 1, Qt.PenStyle.DashLine)
        cut_pen = QtGui.QPen(QtGui.QColor("#3156d9"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        for segment in self.preview.get("segments", []):
            start = segment.get("start")
            end = segment.get("end")
            if not start or not end:
                continue
            painter.setPen(rapid_pen if segment.get("rapid") else cut_pen)
            painter.drawLine(to_canvas(start[0], start[1]), to_canvas(end[0], end[1]))

        path_bounds = self.preview.get("path_bounds")
        if path_bounds:
            px_min, px_max, py_min, py_max = [float(value) for value in path_bounds]
            path_rect = QtCore.QRectF(to_canvas(px_min, py_max), to_canvas(px_max, py_min)).normalized()
            painter.setPen(QtGui.QPen(QtGui.QColor("#5cb85c"), 1.1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(path_rect)

        painter.restore()

        origin = self.preview.get("origin", [0.0, 0.0])
        if x_min <= origin[0] <= x_max and y_min <= origin[1] <= y_max:
            self.draw_cross(painter, to_canvas(origin[0], origin[1]), 7, "#d9534f")

        start_point = self.preview.get("start")
        if start_point:
            painter.setPen(QtGui.QPen(QtGui.QColor("#1f7a3a"), 1))
            painter.setBrush(QtGui.QColor("#5cb85c"))
            painter.drawEllipse(to_canvas(start_point[0], start_point[1]), 4, 4)

        painter.setPen(QtGui.QPen(QtGui.QColor("#b8c2d0"), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(canvas_rect)

        if self.preview.get("outside"):
            warning_rect = outer.adjusted(12, 0, -12, -6)
            painter.setPen(QtGui.QPen(QtGui.QColor("#d9534f")))
            painter.drawText(warning_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, "Path outside job size")


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
