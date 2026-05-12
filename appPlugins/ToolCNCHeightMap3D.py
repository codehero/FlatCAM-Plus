# ##########################################################
# FlatCAM PLUS: CNC Height Map 3D Plugin                  #
# File Updated By Sadri ERCAN - 2026                      #
# License:  FlatCAM Plus CNC Control Module Non-Commercial License #
# See:      appPlugins/cnc_control/LICENSE                #
# ##########################################################

import builtins
import gettext
import math

import numpy as np
import vispy.scene as scene
from vispy.scene.visuals import Line, Mesh, Markers
from vispy.util.quaternion import Quaternion

from PyQt6 import QtCore, QtWidgets

from appGUI.GUIElements import FCLabel
from appPlugins.cnc_control.widgets import FluidStyleButton
from appTool import AppTool

import appTranslation as fcTranslate

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class HeightMap3DCanvas(scene.SceneCanvas):
    def __init__(self):
        super().__init__(keys=None, bgcolor="#f5f7f8", show=False)
        self.unfreeze()
        self.view = self.central_widget.add_view(bgcolor="#f5f7f8")
        self.view.camera = scene.ArcballCamera(fov=0)
        self.visuals = []
        self.scene_center = (0.0, 0.0, 0.0)
        self.scene_span = 50.0
        self.freeze()

    def clear_map(self):
        for visual in self.visuals:
            try:
                visual.parent = None
            except Exception:
                pass
        self.visuals = []
        self.update()

    @staticmethod
    def set_visual_state(visual, preset="opaque", **kwargs):
        try:
            visual.set_gl_state(preset, **kwargs)
        except Exception:
            try:
                visual.set_gl_state(**kwargs)
            except Exception:
                pass

    @staticmethod
    def normalized_colors(z_values):
        z_min = float(np.min(z_values))
        z_max = float(np.max(z_values))
        span = max(z_max - z_min, 1e-9)
        ratios = (z_values - z_min) / span
        colors = np.zeros((z_values.size, 4), dtype=np.float32)
        colors[:, 0] = 0.12 + (0.88 * ratios)
        colors[:, 1] = 0.42 + (0.38 * (1.0 - np.abs(ratios - 0.55) * 1.6).clip(0.0, 1.0))
        colors[:, 2] = 0.90 * (1.0 - ratios)
        colors[:, 3] = 1.0
        return colors

    @staticmethod
    def build_grid_lines(x_values, y_values, z_display):
        points = []
        rows, columns = z_display.shape
        for row in range(rows):
            for column in range(columns - 1):
                points.append([x_values[column], y_values[row], z_display[row, column]])
                points.append([x_values[column + 1], y_values[row], z_display[row, column + 1]])
        for column in range(columns):
            for row in range(rows - 1):
                points.append([x_values[column], y_values[row], z_display[row, column]])
                points.append([x_values[column], y_values[row + 1], z_display[row + 1, column]])
        return np.asarray(points, dtype=np.float32) if points else None

    @staticmethod
    def build_zero_plane(x_min, x_max, y_min, y_max):
        return np.asarray([
            [x_min, y_min, 0.0],
            [x_max, y_min, 0.0],
            [x_max, y_min, 0.0],
            [x_max, y_max, 0.0],
            [x_max, y_max, 0.0],
            [x_min, y_max, 0.0],
            [x_min, y_max, 0.0],
            [x_min, y_min, 0.0],
        ], dtype=np.float32)

    def render_height_map(self, height_map, exaggeration=50.0, show_points=True):
        self.clear_map()

        x_values = np.asarray(height_map.get("x_values", []), dtype=np.float32)
        y_values = np.asarray(height_map.get("y_values", []), dtype=np.float32)

        # Convert z_values safely: None entries (incomplete probe points) become NaN
        raw_z = height_map.get("z_values", [])
        try:
            z_values = np.array(
                [[float(v) if v is not None else float("nan") for v in row] for row in raw_z],
                dtype=np.float32,
            )
        except (TypeError, ValueError):
            return {"ok": False, "message": _("Height map Z data is malformed.")}

        if x_values.size < 2 or y_values.size < 2 or z_values.shape != (y_values.size, x_values.size):
            return {"ok": False, "message": _("Height map data is not valid.")}

        reference_z = float(height_map.get("reference_z", 0.0) or 0.0)
        z_relative = z_values - reference_z

        # Replace NaN (incomplete probe points) with 0 for display purposes
        has_nan = bool(np.any(np.isnan(z_relative)))
        z_display_raw = np.where(np.isnan(z_relative), 0.0, z_relative)
        z_display = z_display_raw * float(exaggeration)

        vertices = []
        for row, y_value in enumerate(y_values):
            for column, x_value in enumerate(x_values):
                vertices.append([float(x_value), float(y_value), float(z_display[row, column])])
        vertices = np.asarray(vertices, dtype=np.float32)

        faces = []
        columns = x_values.size
        for row in range(y_values.size - 1):
            for column in range(x_values.size - 1):
                i0 = row * columns + column
                i1 = i0 + 1
                i2 = i0 + columns
                i3 = i2 + 1
                faces.append([i0, i1, i3])
                faces.append([i0, i3, i2])
        faces = np.asarray(faces, dtype=np.uint32)

        # Use only valid (non-NaN) values for color normalization
        valid_z = z_display_raw[~np.isnan(z_display_raw)]
        color_source = np.where(np.isnan(z_relative.reshape(-1)), 0.0, z_relative.reshape(-1))
        mesh = Mesh(
            vertices=vertices,
            faces=faces,
            vertex_colors=self.normalized_colors(color_source),
            shading=None,
            parent=self.view.scene
        )
        self.set_visual_state(mesh, "opaque", depth_test=True, cull_face=False)
        self.visuals.append(mesh)

        grid_positions = self.build_grid_lines(x_values, y_values, z_display)
        if grid_positions is not None:
            grid = Line(
                pos=grid_positions,
                color=(0.08, 0.10, 0.12, 0.70),
                width=1.2,
                connect="segments",
                method="gl",
                parent=self.view.scene
            )
            self.set_visual_state(grid, "opaque", depth_test=True)
            self.visuals.append(grid)

        plane = Line(
            pos=self.build_zero_plane(float(x_values.min()), float(x_values.max()), float(y_values.min()), float(y_values.max())),
            color=(0.18, 0.22, 0.25, 0.45),
            width=1.0,
            connect="segments",
            method="gl",
            parent=self.view.scene
        )
        self.set_visual_state(plane, "translucent", depth_test=False)
        self.visuals.append(plane)

        if show_points:
            # Only show markers for valid (non-NaN) probe points
            valid_mask = ~np.isnan(z_display_raw.reshape(-1))
            valid_vertices = vertices[valid_mask]
            if valid_vertices.shape[0] > 0:
                markers = Markers(parent=self.view.scene)
                markers.set_data(
                    valid_vertices,
                    face_color=(1.0, 1.0, 1.0, 0.95),
                    edge_color=(0.08, 0.10, 0.12, 0.95),
                    size=7
                )
                self.set_visual_state(markers, "opaque", depth_test=False)
                self.visuals.append(markers)

        x_min = float(x_values.min())
        x_max = float(x_values.max())
        y_min = float(y_values.min())
        y_max = float(y_values.max())
        z_min = float(np.nanmin(z_display)) if not has_nan else float(np.min(z_display))
        z_max = float(np.nanmax(z_display)) if not has_nan else float(np.max(z_display))
        self.scene_center = ((x_min + x_max) / 2.0, (y_min + y_max) / 2.0, (z_min + z_max) / 2.0)
        self.scene_span = max(x_max - x_min, y_max - y_min, abs(z_max - z_min), 1.0)
        self.set_named_view("iso")
        self.update()

        # Statistics use only valid (non-NaN) Z values
        z_valid_relative = valid_z if valid_z.size > 0 else np.array([0.0], dtype=np.float32)
        return {
            "ok": True,
            "rows": int(y_values.size),
            "columns": int(x_values.size),
            "points": int(valid_mask.sum()),
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
            "z_min": float(z_valid_relative.min()),
            "z_max": float(z_valid_relative.max()),
            "mode": height_map.get("probe_coordinate_mode", _("unknown")),
        }

    def fit_current_view(self):
        try:
            self.view.camera.center = tuple(self.scene_center)
            self.view.camera.scale_factor = max(float(self.scene_span) * 1.35, 1.0)
            self.view.camera.view_changed()
        except Exception:
            pass

    def set_named_view(self, view_name):
        views = {
            "top": (Quaternion.create_from_axis_angle(-90, 1, 0, 0, degrees=True), 0, 1.15),
            "front": (Quaternion.create_from_axis_angle(0, 1, 0, 0, degrees=True), 0, 1.35),
            "right": (Quaternion.create_from_axis_angle(90, 0, 0, 1, degrees=True), 0, 1.35),
            "iso": (Quaternion.create_from_euler_angles(58, 0, -38, degrees=True), 28, 1.45),
        }
        quaternion, fov, scale = views.get(view_name, views["iso"])
        try:
            self.view.camera.set_state({"center": self.scene_center, "_quaternion": quaternion, "fov": fov})
            self.view.camera.scale_factor = max(float(self.scene_span) * scale, 1.0)
            self.view.camera.view_changed()
        except Exception:
            self.fit_current_view()


class ToolCNCHeightMap3D(AppTool):
    pluginName = _("Height Map 3D")

    def __init__(self, app):
        self.app = app
        AppTool.__init__(self, app)
        self.canvas = None
        self.status_label = None
        self.stats_label = None
        self.exaggeration_slider = None
        self.exaggeration_value = None
        self._ui_built = False

    def ensure_ui(self):
        if self._ui_built:
            return

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        controls = QtWidgets.QFrame()
        controls.setObjectName("height_map_controls")
        controls_lay = QtWidgets.QHBoxLayout(controls)
        controls_lay.setContentsMargins(8, 8, 8, 8)
        controls_lay.setSpacing(8)

        refresh_btn = FluidStyleButton(_("Refresh"), "#337ab7", "#286090")
        top_btn = FluidStyleButton(_("Top"), "#444444", "#222222")
        iso_btn = FluidStyleButton(_("ISO"), "#444444", "#222222")
        fit_btn = FluidStyleButton(_("Fit"), "#444444", "#222222")

        self.exaggeration_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.exaggeration_slider.setRange(1, 250)
        self.exaggeration_slider.setValue(60)
        self.exaggeration_slider.setMinimumWidth(180)
        self.exaggeration_value = FCLabel("60x")
        self.status_label = FCLabel(_("No height map loaded."))

        controls_lay.addWidget(refresh_btn)
        controls_lay.addWidget(top_btn)
        controls_lay.addWidget(iso_btn)
        controls_lay.addWidget(fit_btn)
        controls_lay.addSpacing(10)
        controls_lay.addWidget(FCLabel(_("Z Scale"), bold=True))
        controls_lay.addWidget(self.exaggeration_slider)
        controls_lay.addWidget(self.exaggeration_value)
        controls_lay.addWidget(self.status_label, 1)

        self.canvas = HeightMap3DCanvas()
        self.stats_label = FCLabel("")
        self.stats_label.setContentsMargins(10, 7, 10, 7)

        self.layout.addWidget(controls)
        self.layout.addWidget(self.canvas.native, 1)
        self.layout.addWidget(self.stats_label)

        refresh_btn.clicked.connect(self.render_current_map)
        top_btn.clicked.connect(lambda: self.canvas.set_named_view("top"))
        iso_btn.clicked.connect(lambda: self.canvas.set_named_view("iso"))
        fit_btn.clicked.connect(self.canvas.fit_current_view)
        self.exaggeration_slider.valueChanged.connect(self.on_exaggeration_changed)

        self._ui_built = True

    def run(self, toggle=True):
        self.ensure_ui()
        tab_exists = False
        for idx in range(self.app.ui.plot_tab_area.count()):
            if self.app.ui.plot_tab_area.tabText(idx) == self.pluginName:
                self.app.ui.plot_tab_area.setCurrentIndex(idx)
                tab_exists = True
                break

        if not tab_exists:
            self.app.ui.plot_tab_area.addTab(self, self.pluginName)
            self.app.ui.plot_tab_area.setCurrentIndex(self.app.ui.plot_tab_area.count() - 1)

        self.render_current_map()

    def height_map(self):
        cnc_tool = getattr(self.app, "cnc_control_tool", None) or getattr(self.app, "levelling_tool", None)
        return getattr(cnc_tool, "auto_level_map", None)

    def on_exaggeration_changed(self, value):
        self.exaggeration_value.setText("%dx" % int(value))
        self.render_current_map()

    def render_current_map(self):
        self.ensure_ui()
        height_map = self.height_map()
        if not height_map:
            self.canvas.clear_map()
            self.status_label.setText(_("No active height map."))
            self.stats_label.setText(_("Run Probe Map in CNC Control, then refresh this view."))
            return

        result = self.canvas.render_height_map(
            height_map,
            exaggeration=float(self.exaggeration_slider.value()),
            show_points=True
        )
        if not result.get("ok"):
            self.status_label.setText(result.get("message", _("Height map could not be rendered.")))
            self.stats_label.setText("")
            return

        self.status_label.setText(_("Height map rendered."))
        self.stats_label.setText(
            _("Grid: %d x %d (%d points)   X %.3f..%.3f mm   Y %.3f..%.3f mm   Z %.4f..%.4f mm   Probe: %s") % (
                result["columns"], result["rows"], result["points"],
                result["x_min"], result["x_max"], result["y_min"], result["y_max"],
                result["z_min"], result["z_max"], result.get("mode", _("unknown"))
            )
        )
