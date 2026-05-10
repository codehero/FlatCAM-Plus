# FlatCAM Plus CNC 3D Preview Module
# License: FlatCAM Plus CNC 3D Preview Module Non-Commercial License.
# See appPlugins/cnc_preview_3d/LICENSE.

import builtins
import gettext
import math
import re

import numpy as np
import vispy.scene as scene
from vispy.scene.visuals import Line, Mesh
from vispy.util.quaternion import Quaternion

import appTranslation as fcTranslate

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class CNCPreview3DCamera(scene.ArcballCamera):
    """Arcball camera with explicit middle-button panning for the preview canvas."""

    PAN_BUTTONS = {3}

    def viewbox_mouse_event(self, event):
        if event.handled or not self.interactive:
            return

        if event.type == "mouse_release":
            self._event_value = None

        if event.type == "mouse_press" and event.button in self.PAN_BUTTONS:
            event.handled = True
            return

        if event.type == "mouse_move" and event.press_event is not None:
            modifiers = event.mouse_event.modifiers
            if not modifiers and any(button in event.buttons for button in self.PAN_BUTTONS):
                self.pan_from_mouse_event(event)
                event.handled = True
                return

        super().viewbox_mouse_event(event)

    def pan_from_mouse_event(self, event):
        p1 = np.array(event.mouse_event.press_event.pos)[:2]
        p2 = np.array(event.mouse_event.pos)[:2]
        norm = np.mean(self._viewbox.size)
        if norm <= 0:
            return

        if self._event_value is None:
            self._event_value = self.center

        dist = (p1 - p2) / norm * self._scale_factor
        dist[1] *= -1
        dx, dy, dz = self._dist_to_trans(dist)

        flip = self._flip_factors
        up, forward, right = self._get_dim_vectors()
        dx, dy, dz = right * dx + forward * dy + up * dz
        dx, dy, dz = flip[0] * dx, flip[1] * dy, dz * flip[2]

        center = self._event_value
        self.center = center[0] + dx, center[1] + dy, center[2] + dz
        self.view_changed()


class CNCPreview3DCanvas(scene.SceneCanvas):
    BOARD_TOP = 0.0
    BOARD_BOTTOM = -1.6
    MIN_VISIBLE_DEPTH = -0.04
    MIN_VISIBLE_WIDTH_RATIO = 0.003
    TRACE_Z_OFFSET = 0.035
    HOLE_Z_OFFSET = 0.006

    def __init__(self, app):
        super().__init__(keys=None, bgcolor="#f3f5f1", show=False)
        self.unfreeze()
        self.fc_app = app
        self.view = self.central_widget.add_view(bgcolor="#f3f5f1")
        self.view.camera = CNCPreview3DCamera(fov=0)
        self.visuals = []
        self.scene_center = (0.0, 0.0, 0.0)
        self.scene_span = 100.0
        self.freeze()

    def clear_preview(self):
        for visual in self.visuals:
            try:
                visual.parent = None
            except Exception:
                pass
        self.visuals = []

    @staticmethod
    def clean_line(line):
        line = re.sub(r"\([^)]*\)", "", line or "")
        line = line.split(";", 1)[0]
        return line.strip()

    @staticmethod
    def words(line):
        return {
            key.upper(): float(value)
            for key, value in re.findall(r"([A-Za-z])\s*([+-]?\d+(?:\.\d+)?)", line)
        }

    def parse_gcode(self, gcode_text, detect_drills=False):
        position = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        absolute = True
        unit_scale = 1.0
        line_count = 0
        travel_segments = []
        cut_segments = []
        drill_hits = []
        active_drill_cycle = False
        drill_cycle_depth = None

        for raw_line in gcode_text.splitlines():
            clean = self.clean_line(raw_line)
            if not clean:
                continue
            line_count += 1
            upper = clean.upper()
            words = self.words(upper)
            g_codes = [int(float(value)) for value in re.findall(r"\bG\s*([+-]?\d+(?:\.\d+)?)", upper)]

            if 20 in g_codes:
                unit_scale = 25.4
            if 21 in g_codes:
                unit_scale = 1.0
            if 90 in g_codes:
                absolute = True
            if 91 in g_codes:
                absolute = False

            if 80 in g_codes:
                active_drill_cycle = False

            if any(g_code in [81, 82, 83] for g_code in g_codes):
                active_drill_cycle = True
                if "Z" in words:
                    drill_cycle_depth = words["Z"] * unit_scale

            if active_drill_cycle and any(axis in words for axis in "XY"):
                next_position = dict(position)
                for axis in "XY":
                    if axis in words:
                        value = words[axis] * unit_scale
                        next_position[axis] = position[axis] + value if not absolute else value
                depth = words["Z"] * unit_scale if "Z" in words else drill_cycle_depth
                if depth is None:
                    depth = self.MIN_VISIBLE_DEPTH
                drill_hits.append((next_position["X"], next_position["Y"], min(depth, self.MIN_VISIBLE_DEPTH)))
                position["X"] = next_position["X"]
                position["Y"] = next_position["Y"]
                continue

            motion = None
            for g_code in g_codes:
                if g_code in [0, 1, 2, 3]:
                    motion = g_code
            if motion is None:
                continue

            next_position = dict(position)
            has_axis = False
            for axis in "XYZ":
                if axis in words:
                    has_axis = True
                    value = words[axis] * unit_scale
                    next_position[axis] = position[axis] + value if not absolute else value
            if not has_axis:
                continue

            start = (position["X"], position["Y"], position["Z"])
            end = (next_position["X"], next_position["Y"], next_position["Z"])
            xy_changed = abs(start[0] - end[0]) > 1e-9 or abs(start[1] - end[1]) > 1e-9
            z_plunged = start[2] >= -1e-9 and end[2] < -1e-9
            below_surface = min(start[2], end[2]) < 0

            if motion == 0 or not below_surface:
                if xy_changed:
                    travel_segments.append((start, end))
            elif xy_changed:
                cut_segments.append((start, end))
            elif detect_drills and z_plunged:
                drill_hits.append((end[0], end[1], min(end[2], self.MIN_VISIBLE_DEPTH)))

            position = next_position

        return {
            "line_count": line_count,
            "travel_segments": travel_segments,
            "cut_segments": cut_segments,
            "drill_hits": self.dedupe_drill_hits(drill_hits),
        }

    @staticmethod
    def dedupe_drill_hits(drill_hits):
        deduped = {}
        for x_pos, y_pos, z_pos in drill_hits:
            key = (round(x_pos, 4), round(y_pos, 4))
            if key not in deduped or z_pos < deduped[key][2]:
                deduped[key] = (x_pos, y_pos, z_pos)
        return list(deduped.values())

    @staticmethod
    def box_mesh(minx, miny, maxx, maxy, zmin, zmax):
        vertices = np.asarray([
            [minx, miny, zmin], [maxx, miny, zmin], [maxx, maxy, zmin], [minx, maxy, zmin],
            [minx, miny, zmax], [maxx, miny, zmax], [maxx, maxy, zmax], [minx, maxy, zmax],
        ], dtype=np.float32)
        faces = np.asarray([
            [0, 1, 2], [0, 2, 3],
            [4, 6, 5], [4, 7, 6],
            [0, 4, 5], [0, 5, 1],
            [1, 5, 6], [1, 6, 2],
            [2, 6, 7], [2, 7, 3],
            [3, 7, 4], [3, 4, 0],
        ], dtype=np.uint32)
        return vertices, faces

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
    def engraved_channel_mesh(segments, width, board_top=0.0):
        vertices = []
        faces = []
        half_width = width / 2.0
        for start, end in segments:
            x1, y1 = start[0], start[1]
            x2, y2 = end[0], end[1]
            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            if length <= 1e-9:
                continue

            depth_z = min(start[2], end[2], CNCPreview3DCanvas.MIN_VISIBLE_DEPTH)
            nx = -dy / length * half_width
            ny = dx / length * half_width
            idx = len(vertices)
            vertices.extend([
                [x1 + nx, y1 + ny, board_top],
                [x1 - nx, y1 - ny, board_top],
                [x2 - nx, y2 - ny, board_top],
                [x2 + nx, y2 + ny, board_top],
                [x1 + nx, y1 + ny, depth_z],
                [x1 - nx, y1 - ny, depth_z],
                [x2 - nx, y2 - ny, depth_z],
                [x2 + nx, y2 + ny, depth_z],
            ])
            faces.extend([
                [idx + 4, idx + 5, idx + 6],
                [idx + 4, idx + 6, idx + 7],
                [idx + 0, idx + 4, idx + 7],
                [idx + 0, idx + 7, idx + 3],
                [idx + 1, idx + 2, idx + 6],
                [idx + 1, idx + 6, idx + 5],
                [idx + 0, idx + 1, idx + 5],
                [idx + 0, idx + 5, idx + 4],
                [idx + 3, idx + 7, idx + 6],
                [idx + 3, idx + 6, idx + 2],
            ])

        if not vertices:
            return None, None
        return np.asarray(vertices, dtype=np.float32), np.asarray(faces, dtype=np.uint32)

    @staticmethod
    def resolved_trace_width(span, tool_dia=None):
        min_visible_width = max(span * 0.009, 0.18)
        if tool_dia not in [None, ""]:
            try:
                width = float(str(tool_dia).replace(",", "."))
                return max(min(width, span * 0.08), min_visible_width)
            except (TypeError, ValueError):
                pass
        return max(min(span * 0.012, 1.2), min_visible_width)

    @staticmethod
    def line_positions(segments, z_pos):
        points = []
        for start, end in segments:
            points.append([start[0], start[1], z_pos])
            points.append([end[0], end[1], z_pos])
        if not points:
            return None
        return np.asarray(points, dtype=np.float32)

    @staticmethod
    def surface_trace_mesh(segments, width, z_pos):
        vertices = []
        faces = []
        half_width = width / 2.0
        for start, end in segments:
            x1, y1 = start[0], start[1]
            x2, y2 = end[0], end[1]
            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            if length <= 1e-9:
                continue

            nx = -dy / length * half_width
            ny = dx / length * half_width
            idx = len(vertices)
            vertices.extend([
                [x1 + nx, y1 + ny, z_pos],
                [x1 - nx, y1 - ny, z_pos],
                [x2 - nx, y2 - ny, z_pos],
                [x2 + nx, y2 + ny, z_pos],
            ])
            faces.extend([
                [idx + 0, idx + 1, idx + 2],
                [idx + 0, idx + 2, idx + 3],
            ])

        if not vertices:
            return None, None
        return np.asarray(vertices, dtype=np.float32), np.asarray(faces, dtype=np.uint32)

    @staticmethod
    def resolved_hole_radius(span, tool_dia=None):
        min_visible_radius = max(span * 0.004, 0.12)
        if tool_dia not in [None, ""]:
            try:
                radius = float(str(tool_dia).replace(",", ".")) / 2.0
                return max(min(radius, span * 0.035), min_visible_radius)
            except (TypeError, ValueError):
                pass
        return max(min(span * 0.007, 0.75), min_visible_radius)

    @staticmethod
    def hole_mesh(drill_hits, radius, board_bottom, board_top, steps=36):
        vertices = []
        faces = []
        for x_pos, y_pos, _z_pos in drill_hits:
            idx = len(vertices)
            top_z = board_top + CNCPreview3DCanvas.HOLE_Z_OFFSET
            bottom_z = board_bottom + 0.01
            vertices.append([x_pos, y_pos, top_z])
            for step in range(steps):
                angle = 2.0 * math.pi * step / steps
                x_val = x_pos + math.cos(angle) * radius
                y_val = y_pos + math.sin(angle) * radius
                vertices.append([x_val, y_val, top_z])
                vertices.append([x_val, y_val, bottom_z])

            for step in range(steps):
                next_step = (step + 1) % steps
                top_a = idx + 1 + step * 2
                bottom_a = top_a + 1
                top_b = idx + 1 + next_step * 2
                bottom_b = top_b + 1
                faces.append([idx, top_b, top_a])
                faces.append([top_a, top_b, bottom_b])
                faces.append([top_a, bottom_b, bottom_a])

        if not vertices:
            return None, None
        return np.asarray(vertices, dtype=np.float32), np.asarray(faces, dtype=np.uint32)

    @staticmethod
    def is_drill_job(gcode_text, job_type=None):
        if job_type and "excellon" in str(job_type).lower():
            return True
        lower_gcode = str(gcode_text).lower()
        return any(token in lower_gcode for token in [
            "total drills",
            "drilling with tool",
            "drills for this tool",
            "type: excellon",
        ])

    def render_job(self, name, gcode_text, tool_dia=None, job_type=None):
        self.clear_preview()
        detect_drills = self.is_drill_job(gcode_text, job_type=job_type)
        parsed = self.parse_gcode(gcode_text, detect_drills=detect_drills)
        cut_segments = parsed["cut_segments"]
        travel_segments = parsed["travel_segments"]
        drill_hits = parsed["drill_hits"]

        xy_points = []
        for start, end in cut_segments:
            xy_points.extend([[start[0], start[1]], [end[0], end[1]]])
        xy_points.extend([[x, y] for x, y, _z in drill_hits])

        if xy_points:
            points = np.asarray(xy_points, dtype=np.float32)
            minx, miny = points.min(axis=0)
            maxx, maxy = points.max(axis=0)
        else:
            minx, miny, maxx, maxy = 0.0, 0.0, 80.0, 60.0

        span = max(float(maxx - minx), float(maxy - miny), 1.0)
        margin = span * 0.08
        minx -= margin
        miny -= margin
        maxx += margin
        maxy += margin

        min_cut_depth = min(
            [min(start[2], end[2]) for start, end in cut_segments] + [z for _x, _y, z in drill_hits] + [-0.08]
        )
        board_bottom = min(self.BOARD_BOTTOM, min_cut_depth - 0.20)
        board_top = self.BOARD_TOP
        board_vertices, board_faces = self.box_mesh(minx, miny, maxx, maxy, board_bottom, board_top)
        board = Mesh(
            vertices=board_vertices,
            faces=board_faces,
            color=(0.020, 0.420, 0.165, 1.0),
            shading=None,
            parent=self.view.scene
        )
        self.set_visual_state(board, "opaque", depth_test=True, cull_face=False)
        self.visuals.append(board)

        trace_width = self.resolved_trace_width(span, tool_dia=tool_dia)
        trace_z = board_top + self.TRACE_Z_OFFSET
        outline_vertices, outline_faces = self.surface_trace_mesh(cut_segments, trace_width * 1.28, trace_z)
        if outline_vertices is not None:
            trace_outline = Mesh(
                vertices=outline_vertices,
                faces=outline_faces,
                color=(0.13, 0.060, 0.015, 1.0),
                shading=None,
                parent=self.view.scene
            )
            self.set_visual_state(trace_outline, "opaque", depth_test=False, cull_face=False)
            self.visuals.append(trace_outline)

        trace_vertices, trace_faces = self.surface_trace_mesh(cut_segments, trace_width, trace_z + 0.004)
        if trace_vertices is not None:
            trace_body = Mesh(
                vertices=trace_vertices,
                faces=trace_faces,
                color=(0.95, 0.48, 0.12, 1.0),
                shading=None,
                parent=self.view.scene
            )
            self.set_visual_state(trace_body, "opaque", depth_test=False, cull_face=False)
            self.visuals.append(trace_body)

        line_pos = self.line_positions(cut_segments, trace_z + 0.008)
        if line_pos is not None:
            trace_highlight = Line(
                pos=line_pos,
                color=(1.0, 0.78, 0.36, 1.0),
                width=1.4,
                connect="segments",
                method="gl",
                parent=self.view.scene
            )
            self.set_visual_state(trace_highlight, "opaque", depth_test=False)
            self.visuals.append(trace_highlight)

        hole_radius = self.resolved_hole_radius(span, tool_dia=tool_dia)
        hole_vertices, hole_faces = self.hole_mesh(drill_hits, hole_radius, board_bottom, board_top)
        if hole_vertices is not None:
            holes = Mesh(
                vertices=hole_vertices,
                faces=hole_faces,
                color=(0.008, 0.010, 0.008, 1.0),
                shading=None,
                parent=self.view.scene
            )
            self.set_visual_state(holes, "opaque", depth_test=False, cull_face=False)
            self.visuals.append(holes)

        center = ((minx + maxx) / 2.0, (miny + maxy) / 2.0, board_bottom / 2.0)
        self.scene_center = center
        self.scene_span = max(maxx - minx, maxy - miny, 1.0)
        self.set_top_view()
        self.update()

        return {
            "name": name,
            "line_count": parsed["line_count"],
            "cut_count": len(cut_segments),
            "travel_count": len(travel_segments),
            "drill_count": len(drill_hits),
            "bounds": "X%.3f..%.3f  Y%.3f..%.3f" % (minx + margin, maxx - margin, miny + margin, maxy - margin),
        }

    def set_top_view(self):
        self.set_named_view("top")

    def fit_current_view(self):
        try:
            self.view.camera.center = tuple(self.scene_center)
            self.view.camera.scale_factor = max(float(self.scene_span) * 1.25, 1.0)
            self.view.camera.view_changed()
        except Exception:
            pass

    def set_named_view(self, view_name):
        views = {
            "top": (Quaternion.create_from_axis_angle(-90, 1, 0, 0, degrees=True), 0, 1.25),
            "bottom": (Quaternion.create_from_axis_angle(90, 1, 0, 0, degrees=True), 0, 1.25),
            "front": (Quaternion.create_from_axis_angle(0, 1, 0, 0, degrees=True), 0, 1.35),
            "back": (Quaternion.create_from_axis_angle(180, 0, 0, 1, degrees=True), 0, 1.35),
            "right": (Quaternion.create_from_axis_angle(90, 0, 0, 1, degrees=True), 0, 1.35),
            "left": (Quaternion.create_from_axis_angle(-90, 0, 0, 1, degrees=True), 0, 1.35),
            "iso": (Quaternion.create_from_euler_angles(58, 0, -38, degrees=True), 28, 1.45),
        }
        quaternion, fov, scale = views.get(view_name, views["iso"])
        try:
            self.view.camera.center = tuple(self.scene_center)
            self.view.camera.scale_factor = max(float(self.scene_span) * scale, 1.0)
            self.view.camera.fov = fov
            self.view.camera.set_state({"_quaternion": quaternion})
            self.view.camera.view_changed()
        except Exception:
            pass

    def set_orbit_view(self):
        self.set_named_view("iso")
