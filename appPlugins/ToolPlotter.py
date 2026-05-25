# ##########################################################
# FlatCAM PLUS: 2D Post-processing for Manufacturing       #
# File Updated By Sadri ERCAN - 2026                       #
# File Author: Sadri ERCAN                                 #
# Date:     05/25/2026                                     #
# License:  FlatCAM Plus CNC Control Module Non-Commercial License         #
# See:      appPlugins/cnc_control/LICENSE                  #
# ##########################################################

from PyQt6 import QtWidgets, QtGui, QtCore

from appTool import AppTool
from appGUI.GUIElements import FCLabel, FCButton, FCFrame, GLay, FCDoubleSpinner, RadioSet

from copy import deepcopy
import gettext
import simplejson as json
import os
import builtins
import appTranslation as fcTranslate
from shapely import LineString, MultiLineString, Polygon, MultiPolygon, GeometryCollection
from shapely.ops import unary_union


fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


PLOTTER_PP = 'GRBL_11_pen_plotter'


class ToolPlotter(AppTool):
    pluginName = _("PCB Plotter")

    def __init__(self, app):
        self.app = app
        self.decimals = self.app.decimals

        AppTool.__init__(self, app)

        self.pen_width_entry = None
        self.pen_down_entry = None
        self.pen_up_entry = None
        self.draw_feed_entry = None
        self.z_feed_entry = None
        self.rapid_feed_entry = None
        self.mode_radio = None
        self.mirror_radio = None

    def install(self, icon=None, separator=None, **kwargs):
        AppTool.install(self, icon, separator, **kwargs)

    def run(self, toggle=True):
        self.app.defaults.report_usage("ToolPlotter()")
        self.set_tool_ui()
        super().run()
        self.app.ui.notebook.setTabText(2, _("PCB Plotter"))

    def set_tool_ui(self):
        self.clear_ui(self.layout)

        title = FCLabel("%s" % self.pluginName, color='blue', bold=True)
        self.layout.addWidget(title)

        mode_frame = FCFrame()
        mode_grid = GLay(v_spacing=5, h_spacing=3, margins=(0, 0, 0, 0))
        mode_frame.setLayout(mode_grid)
        self.layout.addWidget(mode_frame)

        self.mode_radio = RadioSet([
            {'label': _("Follow"), 'value': 'follow'},
            {'label': _("Fill"), 'value': 'fill'}
        ])
        self.mode_radio.set_value(self.app.options.get('tools_plotter_mode', 'follow'))
        mode_grid.addWidget(FCLabel("%s:" % _("Mode")), 0, 0)
        mode_grid.addWidget(self.mode_radio, 0, 1)

        self.mirror_radio = RadioSet([
            {'label': _("None"), 'value': 'none'},
            {'label': _("X"), 'value': 'X'},
            {'label': _("Y"), 'value': 'Y'}
        ])
        self.mirror_radio.set_value(self.app.options.get('tools_plotter_mirror_axis', 'none'))
        mode_grid.addWidget(FCLabel("%s:" % _("Mirror")), 1, 0)
        mode_grid.addWidget(self.mirror_radio, 1, 1)

        param_frame = FCFrame()
        param_grid = GLay(v_spacing=5, h_spacing=3, margins=(0, 0, 0, 0))
        param_frame.setLayout(param_grid)
        self.layout.addWidget(param_frame)

        self.pen_width_entry = self._spinner(0.01, 10.0, 0.05)
        self.pen_width_entry.set_value(self.app.options.get('tools_plotter_pen_width', 0.4))
        param_grid.addWidget(FCLabel("%s:" % _("Pen Width")), 0, 0)
        param_grid.addWidget(self.pen_width_entry, 0, 1)

        self.pen_down_entry = self._spinner(-20.0, 20.0, 0.05)
        self.pen_down_entry.set_value(self.app.options.get('tools_plotter_pen_down_z', -0.3))
        param_grid.addWidget(FCLabel("%s:" % _("Pen Down Z")), 1, 0)
        param_grid.addWidget(self.pen_down_entry, 1, 1)

        self.pen_up_entry = self._spinner(-20.0, 50.0, 0.1)
        self.pen_up_entry.set_value(self.app.options.get('tools_plotter_pen_up_z', 3.0))
        param_grid.addWidget(FCLabel("%s:" % _("Pen Up Z")), 2, 0)
        param_grid.addWidget(self.pen_up_entry, 2, 1)

        self.draw_feed_entry = self._spinner(1.0, 50000.0, 10.0, precision=1)
        self.draw_feed_entry.set_value(self.app.options.get('tools_plotter_draw_feedrate', 600.0))
        param_grid.addWidget(FCLabel("%s:" % _("Draw Feed")), 3, 0)
        param_grid.addWidget(self.draw_feed_entry, 3, 1)

        self.z_feed_entry = self._spinner(1.0, 50000.0, 10.0, precision=1)
        self.z_feed_entry.set_value(self.app.options.get('tools_plotter_z_feedrate', 200.0))
        param_grid.addWidget(FCLabel("%s:" % _("Z Feed")), 4, 0)
        param_grid.addWidget(self.z_feed_entry, 4, 1)

        self.rapid_feed_entry = self._spinner(1.0, 50000.0, 10.0, precision=1)
        self.rapid_feed_entry.set_value(self.app.options.get('tools_plotter_rapid_feedrate', 1500.0))
        param_grid.addWidget(FCLabel("%s:" % _("Rapid Feed")), 5, 0)
        param_grid.addWidget(self.rapid_feed_entry, 5, 1)

        db_tool = self._find_plotter_pen_tool()
        if db_tool is not None:
            self._set_values_from_tool(db_tool)

        db_btn = FCButton(_("Load from DB"))
        db_btn.setIcon(QtGui.QIcon(self.app.resource_location + '/database32.png'))
        db_btn.clicked.connect(self.on_tool_add_from_db_clicked)
        self.layout.addWidget(db_btn)

        apply_btn = FCButton(_("Apply Preset"))
        apply_btn.setIcon(QtGui.QIcon(self.app.resource_location + '/apply32.png'))
        apply_btn.clicked.connect(self.on_apply_preset)
        self.layout.addWidget(apply_btn)

        mirror_btn = FCButton(_("Apply Mirror"))
        mirror_btn.setIcon(QtGui.QIcon(self.app.resource_location + '/flipx.png'))
        mirror_btn.clicked.connect(self.on_apply_mirror)
        self.layout.addWidget(mirror_btn)

        workflow_frame = FCFrame()
        workflow_lay = QtWidgets.QHBoxLayout()
        workflow_lay.setContentsMargins(0, 0, 0, 0)
        workflow_frame.setLayout(workflow_lay)
        self.layout.addWidget(workflow_frame)

        follow_btn = FCButton(_("Generate Follow Path"))
        follow_btn.setIcon(QtGui.QIcon(self.app.resource_location + '/follow32.png'))
        follow_btn.clicked.connect(self.on_generate_follow_geometry)
        workflow_lay.addWidget(follow_btn)

        paint_btn = FCButton(_("Generate Fill Path"))
        paint_btn.setIcon(QtGui.QIcon(self.app.resource_location + '/paint32.png'))
        paint_btn.clicked.connect(self.on_generate_fill_geometry)
        workflow_lay.addWidget(paint_btn)

        export_btn = FCButton(_("Export Plotter G-code"))
        export_btn.setIcon(QtGui.QIcon(self.app.resource_location + '/save_as.png'))
        export_btn.clicked.connect(self.on_export_plotter_gcode)
        self.layout.addWidget(export_btn)

        self.layout.addStretch(1)

    def _spinner(self, min_val, max_val, step, precision=None):
        spinner = FCDoubleSpinner()
        spinner.set_precision(self.decimals if precision is None else precision)
        spinner.set_range(min_val, max_val)
        spinner.set_step(step)
        return spinner

    def _values(self):
        return {
            'mode': self.mode_radio.get_value(),
            'mirror_axis': self.mirror_radio.get_value(),
            'pen_width': self.pen_width_entry.get_value(),
            'pen_down_z': self.pen_down_entry.get_value(),
            'pen_up_z': self.pen_up_entry.get_value(),
            'draw_feedrate': self.draw_feed_entry.get_value(),
            'z_feedrate': self.z_feed_entry.get_value(),
            'rapid_feedrate': self.rapid_feed_entry.get_value()
        }

    def _set_values(self, values):
        self.pen_width_entry.set_value(values['pen_width'])
        self.pen_down_entry.set_value(values['pen_down_z'])
        self.pen_up_entry.set_value(values['pen_up_z'])
        self.draw_feed_entry.set_value(values['draw_feedrate'])
        self.z_feed_entry.set_value(values['z_feedrate'])
        self.rapid_feed_entry.set_value(values['rapid_feedrate'])

    def _set_values_from_tool(self, tool):
        data = tool.get('data', {}) if isinstance(tool, dict) else {}
        if not isinstance(data, dict):
            data = {}

        values = {
            'pen_width': float(data.get('tools_mill_tooldia', tool.get('tooldia', 0.4))),
            'pen_down_z': float(data.get('tools_mill_cutz', -0.3)),
            'pen_up_z': float(data.get('tools_mill_travelz', 3.0)),
            'draw_feedrate': float(data.get('tools_mill_feedrate', 600.0)),
            'z_feedrate': float(data.get('tools_mill_feedrate_z', 200.0)),
            'rapid_feedrate': float(data.get('tools_mill_feedrate_rapid', 1500.0))
        }
        self._set_values(values)

    def _find_plotter_pen_tool(self):
        try:
            self.app.ensure_tools_database()
            filename = self.app.tools_database_path()
            with open(filename, 'r', encoding='utf-8') as f:
                tools = json.load(f)
        except Exception as err:
            self.app.log.error("ToolPlotter._find_plotter_pen_tool() --> %s" % str(err))
            return None

        if not isinstance(tools, dict):
            return None

        for tool in tools.values():
            if not isinstance(tool, dict):
                continue
            data = tool.get('data', {})
            if str(tool.get('name', '')).casefold() == 'plotter pen':
                return tool
            if isinstance(data, dict) and data.get('tools_mill_ppname_g') == PLOTTER_PP:
                return tool
        return None

    def _plotter_option_updates(self, values):
        return {
            'tools_plotter_mode': values['mode'],
            'tools_plotter_mirror_axis': values['mirror_axis'],
            'tools_plotter_pen_width': values['pen_width'],
            'tools_plotter_pen_down_z': values['pen_down_z'],
            'tools_plotter_pen_up_z': values['pen_up_z'],
            'tools_plotter_draw_feedrate': values['draw_feedrate'],
            'tools_plotter_z_feedrate': values['z_feedrate'],
            'tools_plotter_rapid_feedrate': values['rapid_feedrate']
        }

    def _milling_option_updates(self, values):
        return {
            'tools_mill_tooldia': str(values['pen_width']),
            'tools_mill_offset_type': 0,
            'tools_mill_offset_value': 0.0,
            'tools_mill_job_type': 0,
            'tools_mill_cutz': values['pen_down_z'],
            'tools_mill_multidepth': False,
            'tools_mill_depthperpass': abs(values['pen_down_z']),
            'tools_mill_travelz': values['pen_up_z'],
            'tools_mill_feedrate': values['draw_feedrate'],
            'tools_mill_feedrate_z': values['z_feedrate'],
            'tools_mill_feedrate_rapid': values['rapid_feedrate'],
            'tools_mill_spindlespeed': 0,
            'tools_mill_dwell': False,
            'tools_mill_dwelltime': 0,
            'tools_mill_toolchange': False,
            'tools_mill_startz': None,
            'tools_mill_endz': values['pen_up_z'],
            'tools_mill_endxy': None,
            'tools_mill_min_power': 0.0,
            'tools_mill_laser_on': 'M3',
            'tools_mill_ppname_g': PLOTTER_PP
        }

    def on_apply_preset(self):
        if PLOTTER_PP not in self.app.preprocessors:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Pen plotter preprocessor was not loaded."))
            return

        values = self._values()
        updates = self._plotter_option_updates(values)
        updates.update(self._milling_option_updates(values))

        for option, value in updates.items():
            self.app.options[option] = value

        for obj in self._selected_geometry_objects():
            self._apply_to_geometry_object(obj, updates, values)

        self._sync_milling_ui(updates)
        self.app.inform.emit('[success] %s' % _("PCB Plotter preset applied."))

    def on_tool_add_from_db_clicked(self):
        for idx in range(self.app.ui.plot_tab_area.count()):
            if self.app.ui.plot_tab_area.tabText(idx) == _("Tools Database"):
                self.app.ui.plot_tab_area.setCurrentWidget(self.app.tools_db_tab)
                self.app.tools_db_tab.on_tool_request = self.on_tool_from_db_inserted
                break

        ret_val = self.app.on_tools_database(source='plotter')
        if ret_val == 'fail':
            return

        self.app.tools_db_tab.ok_to_add = True
        self.app.tools_db_tab.ui.buttons_frame.hide()
        self.app.tools_db_tab.ui.add_tool_from_db.show()
        self.app.tools_db_tab.ui.cancel_tool_from_db.show()

    def on_tool_from_db_inserted(self, tool):
        data = tool.get('data', {}) if isinstance(tool, dict) else {}
        target = data.get('tool_target', 0) if isinstance(data, dict) else 0

        if target not in [0, 1]:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Selected tool can't be used as a plotter pen."))
            return

        is_plotter_tool = (
            str(tool.get('name', '')).casefold() == 'plotter pen' or
            data.get('tools_mill_ppname_g') == PLOTTER_PP
        )
        if not is_plotter_tool:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Select the Plotter Pen preset from Tools Database."))
            return

        self._set_values_from_tool(tool)
        self.on_apply_preset()
        self._close_tools_db_tab()
        self.app.inform.emit('[success] %s' % _("Plotter Pen preset loaded from Tools Database."))

    def _close_tools_db_tab(self):
        for idx in range(self.app.ui.plot_tab_area.count()):
            if self.app.ui.plot_tab_area.tabText(idx) == _("Tools Database"):
                wdg = self.app.ui.plot_tab_area.widget(idx)
                wdg.deleteLater()
                self.app.ui.plot_tab_area.removeTab(idx)
                break

    def _selected_geometry_objects(self):
        selected = []
        try:
            selected = [obj for obj in self.app.collection.get_selected() if obj.kind == 'geometry']
        except Exception:
            selected = []

        if selected:
            return selected

        active = self.app.collection.get_active()
        if active is not None and getattr(active, 'kind', None) == 'geometry':
            return [active]
        return []

    def _apply_to_geometry_object(self, obj, updates, values):
        for option, value in updates.items():
            if option.startswith('tools_mill_'):
                obj.obj_options[option] = value

        obj.obj_options['tools_mill_tooldia'] = str(values['pen_width'])
        obj.obj_options['tools_mill_ppname_g'] = PLOTTER_PP

        tools = getattr(obj, 'tools', None)
        if not isinstance(tools, dict):
            return

        for tool in tools.values():
            tool['tooldia'] = values['pen_width']
            data = tool.setdefault('data', {})
            for option, value in updates.items():
                if option.startswith('tools_mill_'):
                    data[option] = value
            data['tools_mill_tooldia'] = values['pen_width']
            data['tools_mill_ppname_g'] = PLOTTER_PP

    def _sync_milling_ui(self, updates):
        milling_tool = getattr(self.app, 'milling_tool', None)
        ui = getattr(milling_tool, 'ui', None)
        if ui is None:
            return

        widget_map = {
            'tools_mill_cutz': 'cutz_entry',
            'tools_mill_travelz': 'travelz_entry',
            'tools_mill_feedrate': 'xyfeedrate_entry',
            'tools_mill_feedrate_z': 'feedrate_z_entry',
            'tools_mill_feedrate_rapid': 'feedrate_rapid_entry',
            'tools_mill_ppname_g': 'pp_geo_name_cb',
            'tools_mill_toolchange': 'toolchange_cb',
            'tools_mill_endz': 'endz_entry',
            'tools_mill_spindlespeed': 'spindlespeed_entry',
            'tools_mill_dwell': 'dwell_cb',
            'tools_mill_dwelltime': 'dwelltime_entry'
        }

        for option, attr_name in widget_map.items():
            widget = getattr(ui, attr_name, None)
            if widget is None or option not in updates:
                continue
            try:
                widget.set_value(updates[option])
            except Exception:
                try:
                    widget.setCurrentText(str(updates[option]))
                except Exception:
                    pass

        addtool_entry = getattr(ui, 'addtool_entry', None)
        if addtool_entry is not None:
            try:
                addtool_entry.set_value(float(updates['tools_mill_tooldia']))
            except Exception:
                pass

    def on_apply_mirror(self):
        axis = self.mirror_radio.get_value()
        self.app.options['tools_plotter_mirror_axis'] = axis

        if axis == 'none':
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("No mirror axis selected."))
            return

        objects = self.app.collection.get_selected()
        if not objects:
            active = self.app.collection.get_active()
            objects = [active] if active is not None else []

        mirrored = 0
        for obj in objects:
            if getattr(obj, 'kind', None) not in ['gerber', 'geometry']:
                continue
            try:
                xmin, ymin, xmax, ymax = obj.bounds()
                px = (xmin + xmax) / 2.0
                py = (ymin + ymax) / 2.0
                obj.mirror(axis, [px, py])
                obj.plot()
                mirrored += 1
            except Exception as err:
                self.app.log.error("ToolPlotter.on_apply_mirror() --> %s" % str(err))

        if mirrored:
            self.app.inform.emit('[success] %s' % _("Mirror applied."))
        else:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Select a Gerber or Geometry object to mirror."))

    def on_open_milling(self):
        self.on_apply_preset()
        self._run_tool('milling_tool')

    def on_generate_follow_geometry(self):
        self.on_apply_preset()

        gerber = self._active_or_selected_gerber()
        if gerber is None:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Select a Gerber object for plotter follow."))
            return

        follow_geometry = getattr(gerber, 'follow_geometry', None)
        if follow_geometry is None:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("No follow geometry found in the selected Gerber."))
            return

        values = self._values()
        outname = "%s_plotter_follow" % gerber.obj_options['name']
        updates = self._plotter_option_updates(values)
        updates.update(self._milling_option_updates(values))

        def follow_init(new_obj, app_obj):
            new_obj.multigeo = True
            new_obj.multitool = True
            new_obj.solid_geometry = deepcopy(follow_geometry)
            self._prepare_plotter_geometry_object(new_obj, app_obj, values, updates, outname)

        try:
            new_obj = self.app.app_obj.new_object("geometry", outname, follow_init)
            if new_obj == 'fail':
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("Plotter follow geometry failed."))
                return

            self._focus_created_object(new_obj)
            self.app.inform.emit('[success] %s' % _("Plotter follow geometry created."))
        except Exception as err:
            self.app.log.error("ToolPlotter.on_generate_follow_geometry() --> %s" % str(err))
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Plotter follow geometry failed."))

    def on_generate_fill_geometry(self):
        self.on_apply_preset()

        gerber = self._active_or_selected_gerber()
        if gerber is None:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Select a Gerber object for plotter fill."))
            return

        values = self._values()
        source_polygons = self._trace_pad_polygons_from_gerber(gerber)
        if not source_polygons:
            self.app.inform.emit(
                '[ERROR_NOTCL] %s' %
                _("No trace/pad polygons found. Check that the selected object is a copper Gerber.")
            )
            return

        fill_lines = self._hatch_polygons(source_polygons, values['pen_width'])
        if not fill_lines:
            self.app.inform.emit(
                '[ERROR_NOTCL] %s' %
                _("No fill lines were generated. Try a smaller pen width.")
            )
            return

        outname = "%s_plotter_fill" % gerber.obj_options['name']
        updates = self._plotter_option_updates(values)
        updates.update(self._milling_option_updates(values))

        def fill_init(new_obj, app_obj):
            new_obj.multigeo = True
            new_obj.multitool = True
            new_obj.solid_geometry = deepcopy(fill_lines)
            self._prepare_plotter_geometry_object(new_obj, app_obj, values, updates, outname)

            try:
                minx, miny, maxx, maxy = unary_union(fill_lines).bounds
                new_obj.obj_options['xmin'] = minx
                new_obj.obj_options['ymin'] = miny
                new_obj.obj_options['xmax'] = maxx
                new_obj.obj_options['ymax'] = maxy
            except Exception:
                pass

        try:
            new_obj = self.app.app_obj.new_object("geometry", outname, fill_init)
            if new_obj == 'fail':
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("Plotter fill geometry failed."))
                return

            self._focus_created_object(new_obj)
            self.app.inform.emit('[success] %s' % _("Plotter fill geometry created."))
        except Exception as err:
            self.app.log.error("ToolPlotter.on_generate_fill_geometry() --> %s" % str(err))
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Plotter fill geometry failed."))

    def _prepare_plotter_geometry_object(self, new_obj, app_obj, values, updates, outname):
        default_data = {}
        for opt_key, opt_val in app_obj.options.items():
            if opt_key.find('geometry' + "_") == 0:
                oname = opt_key[len('geometry') + 1:]
                default_data[oname] = deepcopy(opt_val)
            if opt_key.find('tools_mill' + "_") == 0:
                default_data[opt_key] = deepcopy(opt_val)

        for option, value in updates.items():
            if option.startswith('tools_mill_'):
                default_data[option] = deepcopy(value)
                new_obj.obj_options[option] = deepcopy(value)

        new_obj.obj_options["tools_mill_tooldia"] = str(values['pen_width'])
        new_obj.obj_options["tools_mill_ppname_g"] = PLOTTER_PP
        new_obj.obj_options["plotter_geometry"] = True

        default_data["tools_mill_tooldia"] = values['pen_width']
        default_data["tools_mill_ppname_g"] = PLOTTER_PP
        default_data["plotter_geometry"] = True
        default_data["name"] = outname

        new_obj.tools = {
            1: {
                'tooldia': app_obj.dec_format(float(values['pen_width']), self.decimals),
                'data': deepcopy(default_data),
                'solid_geometry': new_obj.solid_geometry
            }
        }

    def _focus_created_object(self, obj_or_name, retry=0):
        if isinstance(obj_or_name, str):
            obj_name = obj_or_name
            obj = self.app.collection.get_by_name(obj_name)
        else:
            obj = obj_or_name
            obj_name = getattr(obj, 'obj_options', {}).get('name', None)

        if obj is None or obj_name is None:
            if retry < 5:
                QtCore.QTimer.singleShot(100, lambda: self._focus_created_object(obj_or_name, retry + 1))
            return

        try:
            self.app.collection.set_all_inactive()
            self.app.collection.set_active(obj_name)
        except Exception:
            if retry < 5:
                QtCore.QTimer.singleShot(100, lambda: self._focus_created_object(obj_name, retry + 1))
            return

        try:
            obj.build_ui()
        except RuntimeError:
            try:
                obj.set_ui(obj.ui_type(app=self.app))
                obj.build_ui()
            except Exception as err:
                self.app.log.error("ToolPlotter._focus_created_object() --> %s" % str(err))
        except Exception as err:
            self.app.log.error("ToolPlotter._focus_created_object() --> %s" % str(err))

        if hasattr(self.app.ui, "ensure_properties_tab_visible"):
            self.app.ui.ensure_properties_tab_visible(title=obj_name)
        else:
            self.app.ui.notebook.setCurrentWidget(self.app.ui.properties_tab)

    def _active_or_selected_gerber(self):
        active = self.app.collection.get_active()
        if active is not None and getattr(active, 'kind', None) == 'gerber':
            return active

        try:
            for obj in self.app.collection.get_selected():
                if getattr(obj, 'kind', None) == 'gerber':
                    return obj
        except Exception:
            pass
        return None

    def _trace_pad_polygons_from_gerber(self, gerber):
        try:
            bounds = gerber.bounds()
        except Exception:
            bounds = gerber.obj_options['xmin'], gerber.obj_options['ymin'], gerber.obj_options['xmax'], gerber.obj_options['ymax']

        raw_polygons = []
        apertures = getattr(gerber, 'apertures', {})
        if isinstance(apertures, dict):
            for aperture in apertures.values():
                for geo_el in aperture.get('geometry', []):
                    if isinstance(geo_el, dict) and 'solid' in geo_el:
                        raw_polygons.extend(self._polygon_parts(geo_el['solid']))

        if not raw_polygons:
            raw_polygons.extend(self._polygon_parts(getattr(gerber, 'solid_geometry', [])))

        polygons = []
        for polygon in raw_polygons:
            if polygon.is_empty or polygon.area <= 0:
                continue
            if self._looks_like_board_background(polygon, bounds):
                continue
            polygons.append(polygon)

        return polygons

    def _polygon_parts(self, geometry):
        parts = []
        if geometry is None:
            return parts

        if isinstance(geometry, Polygon):
            return [geometry]

        if isinstance(geometry, MultiPolygon):
            for polygon in geometry.geoms:
                parts.extend(self._polygon_parts(polygon))
            return parts

        if isinstance(geometry, GeometryCollection):
            for geom in geometry.geoms:
                parts.extend(self._polygon_parts(geom))
            return parts

        if isinstance(geometry, (list, tuple)):
            for geom in geometry:
                parts.extend(self._polygon_parts(geom))
            return parts

        return parts

    @staticmethod
    def _looks_like_board_background(polygon, bounds):
        minx, miny, maxx, maxy = bounds
        board_w = max(maxx - minx, 0.000001)
        board_h = max(maxy - miny, 0.000001)
        board_area = board_w * board_h

        p_minx, p_miny, p_maxx, p_maxy = polygon.bounds
        poly_w = p_maxx - p_minx
        poly_h = p_maxy - p_miny
        area_ratio = polygon.area / board_area

        if area_ratio > 0.30:
            return True

        covers_board = poly_w > (board_w * 0.90) and poly_h > (board_h * 0.90)
        if covers_board and area_ratio > 0.10:
            return True

        return False

    def _hatch_polygons(self, polygons, pen_width):
        spacing = max(float(pen_width) * 0.55, 0.05)
        min_segment_len = max(float(pen_width) * 0.25, 0.02)
        fill_lines = []

        for polygon in polygons:
            fill_lines.append(LineString(polygon.exterior.coords))
            for interior in polygon.interiors:
                fill_lines.append(LineString(interior.coords))

            minx, miny, maxx, maxy = polygon.bounds
            y = miny + spacing / 2.0
            while y <= maxy:
                scan_line = LineString([(minx - spacing, y), (maxx + spacing, y)])
                intersection = polygon.intersection(scan_line)
                fill_lines.extend(self._line_parts(intersection, min_segment_len))
                y += spacing

        return [line for line in fill_lines if line and not line.is_empty and line.length >= min_segment_len]

    def _line_parts(self, geometry, min_segment_len):
        lines = []
        if geometry is None or geometry.is_empty:
            return lines

        if isinstance(geometry, LineString):
            if geometry.length >= min_segment_len:
                lines.append(geometry)
            return lines

        if isinstance(geometry, MultiLineString):
            for line in geometry.geoms:
                lines.extend(self._line_parts(line, min_segment_len))
            return lines

        if isinstance(geometry, GeometryCollection):
            for geom in geometry.geoms:
                lines.extend(self._line_parts(geom, min_segment_len))
            return lines

        return lines

    def on_export_plotter_gcode(self):
        cncjob = self._active_or_selected_cncjob()
        if cncjob is None:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Select a CNCJob object to export."))
            return

        if not self._is_plotter_cncjob(cncjob):
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("Selected CNCJob was not generated with the plotter preprocessor."))

        cncjob.on_exportgcode_button_click()

    def _active_or_selected_cncjob(self):
        active = self.app.collection.get_active()
        if active is not None and getattr(active, 'kind', None) == 'cncjob':
            return active

        try:
            for obj in self.app.collection.get_selected():
                if getattr(obj, 'kind', None) == 'cncjob':
                    return obj
        except Exception:
            pass
        return None

    @staticmethod
    def _is_plotter_cncjob(cncjob):
        tools = getattr(cncjob, 'tools', {})
        if not isinstance(tools, dict):
            return False

        for tool in tools.values():
            data = tool.get('data', {})
            if data.get('tools_mill_ppname_g') == PLOTTER_PP:
                return True
        return False

    def on_open_square_test(self):
        filename = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'assets', 'examples', 'pen_plotter_20x20_square.gcode'
        ))
        self.app.f_handlers.on_file_open_gcode(name=filename)

    def _run_tool(self, tool_attr):
        tool = getattr(self.app, tool_attr, None)
        if tool is None:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Tool is not available."))
            return
        tool.run(toggle=True)
