# ##########################################################
# FlatCAM PLUS: 2D Post-processing for Manufacturing       #
# http://flatcam.org                                       #
# File Updated By Sadri ERCAN - 2026                        #
# File Author: Dennis Hayrullin                            #
# Date: 2/5/2016                                           #
# MIT Licence                                              #
# ##########################################################

from PyQt6.QtGui import QPalette
from PyQt6.QtCore import QSettings

import numpy as np

import vispy.scene as scene
from vispy.scene.cameras.base_camera import BaseCamera
# from vispy.scene.widgets import Widget as VisPyWidget
from vispy.color import Color
from vispy.visuals.shaders import Function

import time

white = Color("#ffffff")
black = Color("#000000")


_PCB_GRID_COLOR = """
uniform vec4 u_gridlines_bounds;
uniform float u_border_width;

vec4 grid_color(vec2 pos) {
    vec4 px_pos = $map_to_doc(vec4(pos, 0, 1));
    px_pos /= px_pos.w;

    // Compute vectors representing width, height of pixel in local coords.
    vec4 local_pos = $map_doc_to_local(px_pos);
    vec4 dx = $map_doc_to_local(px_pos + vec4(1.0, 0, 0, 0));
    vec4 dy = $map_doc_to_local(px_pos + vec4(0, 1.0, 0, 0));
    local_pos /= local_pos.w;
    dx = dx / dx.w - local_pos;
    dy = dy / dy.w - local_pos;

    vec2 px = vec2(abs(dx.x) + abs(dy.x), abs(dx.y) + abs(dy.y));
    float log10 = log(10.0);
    float sx = pow(10.0, floor(log(px.x) / log10) + 1.) * $scale.x;
    float sy = pow(10.0, floor(log(px.y) / log10) + 1.) * $scale.y;

    float step_x = 5.0 * sx;
    float step_y = 5.0 * sy;
    if (step_x / px.x < 14.0) {
        step_x = 10.0 * sx;
    }
    if (step_y / px.y < 14.0) {
        step_y = 10.0 * sy;
    }

    vec2 grid_step = vec2(step_x, step_y);
    vec2 cell_pos = mod(local_pos.xy + 0.5 * grid_step, grid_step) - 0.5 * grid_step;
    vec2 line_pos_px = abs(vec2(cell_pos.x / px.x, cell_pos.y / px.y));
    float line_distance = min(line_pos_px.x, line_pos_px.y);
    float alpha = 1.0 - smoothstep(0.72, 1.28, line_distance);

    if (alpha <= 0.0) {
        discard;
    }

    if (any(lessThan(local_pos.xy + u_border_width / 2, u_gridlines_bounds.xz)) ||
        any(greaterThan(local_pos.xy - u_border_width / 2, u_gridlines_bounds.yw))) {
        discard;
    }

    return vec4($color.rgb, $color.a * alpha * 0.62);
}
"""


def apply_pcb_grid_shader(grid, color, scale=(1, 1)):
    grid._grid_color_fn = Function(_PCB_GRID_COLOR)
    grid._grid_color_fn['color'] = Color(color).rgba
    grid._grid_color_fn['scale'] = scale
    grid.shared_program.frag['get_data'] = grid._grid_color_fn


class VisPyCanvas(scene.SceneCanvas):

    def __init__(self, config=None):
        # scene.SceneCanvas.__init__(self, keys=None, config=config)
        super().__init__(config=config, keys=None)

        self.unfreeze()

        settings = QSettings("Open Source", "FlatCAM_Plus")
        if settings.contains("axis_font_size"):
            a_fsize = settings.value('axis_font_size', type=int)
        else:
            a_fsize = 6

        if settings.contains("theme"):
            theme = settings.value('theme', type=str)
        else:
            theme = 'default'

        if settings.contains("dark_canvas"):
            dark_canvas = settings.value('dark_canvas', type=bool)
        else:
            dark_canvas = False

        if (theme == 'default' or theme == 'light') and not dark_canvas:
            theme_color = Color('#FFFFFF')
            tick_color = Color('#000000')
            back_color = str(QPalette().color(QPalette.ColorRole.Window).name())
        else:
            theme_color = Color('#071017')
            back_color = Color('#071017')
            tick_color = Color('#5f6f78')
            # back_color = Color('#272822') # darker
            # back_color = Color('#3c3f41') # lighter

        self.central_widget.bgcolor = back_color
        self.central_widget.border_color = back_color

        self.ruler_margin = 10
        self.ruler_height = 28
        self.ruler_width = 55
        ruler_bg = Color('#f3f4f6') if (theme == 'default' or theme == 'light') and not dark_canvas else Color('#2f3338')
        ruler_border = Color('#c9cdd3') if (theme == 'default' or theme == 'light') and not dark_canvas else Color('#555b63')

        self.grid_widget = self.central_widget.add_grid(margin=self.ruler_margin)
        self.grid_widget.spacing = 0

        self.ruler_corner = self.grid_widget.add_widget(row=0, col=0)
        self.ruler_corner.bgcolor = ruler_bg
        self.ruler_corner.border_color = ruler_border
        self.ruler_corner.height_min = self.ruler_height
        self.ruler_corner.height_max = self.ruler_height
        self.ruler_corner.width_min = self.ruler_width
        self.ruler_corner.width_max = self.ruler_width

        self.xaxis = scene.AxisWidget(
            orientation='top', axis_color=tick_color, text_color=tick_color, font_size=a_fsize, axis_width=1,
            anchors=['center', 'top']
        )
        self.xaxis.bgcolor = ruler_bg
        self.xaxis.border_color = ruler_border
        self.xaxis.height_min = self.ruler_height
        self.xaxis.height_max = self.ruler_height
        self.xaxis.axis.major_tick_length = 8
        self.xaxis.axis.minor_tick_length = 4
        self.xaxis.axis.tick_label_margin = 4
        self.grid_widget.add_widget(self.xaxis, row=0, col=1)

        self.yaxis = scene.AxisWidget(
            orientation='left', axis_color=tick_color, text_color=tick_color, font_size=a_fsize, axis_width=1
        )
        self.yaxis.bgcolor = ruler_bg
        self.yaxis.border_color = ruler_border
        self.yaxis.width_min = self.ruler_width
        self.yaxis.width_max = self.ruler_width
        self.yaxis.axis.major_tick_length = 8
        self.yaxis.axis.minor_tick_length = 4
        self.yaxis.axis.tick_label_margin = 4
        self.yaxis.axis._text.rotation = 45
        self.grid_widget.add_widget(self.yaxis, row=1, col=0)

        right_padding = self.grid_widget.add_widget(row=0, col=2, row_span=2)
        # right_padding.width_max = 24
        right_padding.width_max = 0

        view = self.grid_widget.add_view(row=1, col=1, border_color=tick_color, bgcolor=theme_color)
        view.camera = Camera(aspect=1, rect=(-25, -25, 150, 150))

        # Following function was removed from 'prepare_draw()' of 'Grid' class by patch,
        # it is necessary to call manually
        self.grid_widget._update_child_widget_dim()

        self.xaxis.link_view(view)
        self.yaxis.link_view(view)

        # grid1 = scene.GridLines(parent=view.scene, color='dimgray')
        # grid1.set_gl_state(depth_test=False)

        settings = QSettings("Open Source", "FlatCAM_Plus")
        if settings.contains("theme"):
            theme = settings.value('theme', type=str)
        else:
            theme = 'default'

        if settings.contains("dark_canvas"):
            dark_canvas = settings.value('dark_canvas', type=bool)
        else:
            dark_canvas = False

        self.view = view
        if (theme == 'default' or theme == 'light') and not dark_canvas:
            self.grid = scene.GridLines(parent=self.view.scene, color='dimgray')
            apply_pcb_grid_shader(self.grid, '#d1d5db66')
        else:
            self.grid = scene.GridLines(parent=self.view.scene, color='#1A2630CC')
            apply_pcb_grid_shader(self.grid, '#1A2630CC')

        self.grid.set_gl_state(depth_test=False)

        self.freeze()

        # self.measure_fps()

    def set_rulers_visible(self, visible=True):
        """
        Show or collapse the Photoshop-style top/left ruler widgets.
        """

        height = self.ruler_height if visible else 0
        width = self.ruler_width if visible else 0

        self.xaxis.height_min = height
        self.xaxis.height_max = height
        self.yaxis.width_min = width
        self.yaxis.width_max = width
        self.ruler_corner.height_min = height
        self.ruler_corner.height_max = height
        self.ruler_corner.width_min = width
        self.ruler_corner.width_max = width

        self.xaxis.visible = visible
        self.yaxis.visible = visible
        self.ruler_corner.visible = visible
        self.grid_widget._update_child_widget_dim()
        self.update()

    def translate_coords(self, pos):
        """
        Translate pixels to FlatCAM units.

        """
        tr = self.grid.get_transform('canvas', 'visual')
        return tr.map(pos)

    def translate_coords_2(self, pos):
        """
        Translate FlatCAM units to pixels.
        """
        tr = self.grid.get_transform('visual', 'document')
        return tr.map(pos)


class Camera(scene.PanZoomCamera):

    def __init__(self, **kwargs):
        super(Camera, self).__init__(**kwargs)

        self.minimum_scene_size = 0.01
        self.maximum_scene_size = 10000

        self.last_event = None
        self.last_time = 0

        # Default mouse button for panning is RMB
        self.pan_button_setting = "2"

        self.zoom_callback = lambda *args: None

    def zoom(self, factor, center=None):
        center = center if (center is not None) else self.center
        super(Camera, self).zoom(factor, center)

    def _has_valid_viewbox(self):
        viewbox = getattr(self, '_viewbox', None)
        if viewbox is None:
            return False

        try:
            rect = viewbox.rect
            return rect.width > 0 and rect.height > 0
        except Exception:
            return False

    def viewbox_resize_event(self, event):
        if not self._has_valid_viewbox():
            return

        try:
            super().viewbox_resize_event(event)
        except np.linalg.LinAlgError as e:
            if str(e) != "Singular matrix":
                raise

    def _update_transform(self):
        if not self._has_valid_viewbox():
            return

        try:
            rect = self.rect
            if rect.width <= 0 or rect.height <= 0:
                return
        except Exception:
            return

        try:
            super()._update_transform()
        except np.linalg.LinAlgError as e:
            if str(e) != "Singular matrix":
                raise

    def viewbox_mouse_event(self, event):
        """
        The SubScene received a mouse event; update transform
        accordingly.

        Parameters
        ----------
        event : instance of Event
            The event.
        """
        if event.handled or not self.interactive:
            return

        # key modifiers
        modifiers = event.mouse_event.modifiers

        # Limit mouse move events
        last_event = event.last_event
        t = time.time()
        if t - self.last_time > 0.015:
            self.last_time = t
            if self.last_event:
                last_event = self.last_event
                self.last_event = None
        else:
            if not self.last_event:
                self.last_event = last_event
            event.handled = True
            return

        # ################### Scrolling ##########################
        BaseCamera.viewbox_mouse_event(self, event)

        if event.type == 'mouse_wheel':
            if not modifiers:
                center = self._scene_transform.imap(event.pos)
                scale = (1 + self.zoom_factor) ** (-event.delta[1] * 30)
                self.limited_zoom(scale, center)

            if self.zoom_callback:
                self.zoom_callback()
            event.handled = True

        elif event.type == 'mouse_move':
            if event.press_event is None:
                return

            # ################ Panning ############################
            # self.pan_button_setting is actually self.FlatCAM.APP.defaults['global_pan_button']
            if event.button == int(self.pan_button_setting) and not modifiers:
                # Translate
                p1 = np.array(last_event.pos)[:2]
                p2 = np.array(event.pos)[:2]
                p1s = self._transform.imap(p1)
                p2s = self._transform.imap(p2)
                self.pan(p1s-p2s)
                event.handled = True
            elif event.button in [2, 3] and 'Shift' in modifiers:
                # Zoom
                p1c = np.array(last_event.pos)[:2]
                p2c = np.array(event.pos)[:2]
                scale = ((1 + self.zoom_factor) **
                         ((p1c-p2c) * np.array([1, -1])))
                center = self._transform.imap(event.press_event.pos[:2])
                self.limited_zoom(scale, center)
                event.handled = True
            else:
                event.handled = False
        elif event.type == 'mouse_press':
            # accept the event if it is button 1 or 2.
            # This is required in order to receive future events
            event.handled = event.button in [1, 2, 3]
        else:
            event.handled = False

    def limited_zoom(self, scale, center):

        try:
            zoom_in = scale[1] < 1
        except IndexError:
            zoom_in = scale < 1

        if (not zoom_in and self.rect.width < self.maximum_scene_size) \
                or (zoom_in and self.rect.width > self.minimum_scene_size):
            self.zoom(scale, center)
