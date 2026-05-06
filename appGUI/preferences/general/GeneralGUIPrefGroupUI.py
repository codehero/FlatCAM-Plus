
from PyQt6 import QtWidgets, QtGui
from PyQt6.QtCore import QSettings

from appGUI.GUIElements import RadioSet, FCCheckBox, FCComboBox, FCSliderWithSpinner, FCColorEntry, FCLabel, \
    GLay, FCFrame, FCComboBox2, FCButton, FCSpinner
from appGUI.preferences.OptionsGroupUI import OptionsGroupUI
from appTranslation import restart_program

import gettext
import appTranslation as fcTranslate
import builtins

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class GeneralGUIPrefGroupUI(OptionsGroupUI):
    def __init__(self, app, parent=None):
        super(GeneralGUIPrefGroupUI, self).__init__(self, parent=parent)

        self.setTitle(str(_("GUI Preferences")))
        self.decimals = app.decimals
        self.options = app.options

        self.param_lbl = FCLabel('%s' % _("Parameters"), bold=True)
        self.layout.addWidget(self.param_lbl)

        # #############################################################################################################
        # Grid0 Frame
        # #############################################################################################################
        par_frame = FCFrame()
        self.layout.addWidget(par_frame)

        grid0 = GLay(v_spacing=5, h_spacing=3)
        par_frame.setLayout(grid0)

        # Kept as non-visible compatibility fields. The application theme is fixed to Light.
        self.appearance_label = FCLabel('%s' % _("Theme"), bold=True)
        self.appearance_radio = RadioSet([
            {"label": _("Light"), "value": "light"}
        ], compact=True)
        self.appearance_radio.set_value("light")
        self.appearance_label.hide()
        self.appearance_radio.hide()

        # Kept as a non-visible compatibility field for older preferences code.
        # Canvas darkness is fixed to the Light theme policy.
        self.dark_canvas_cb = FCCheckBox('%s' % _('Dark Canvas'))
        self.dark_canvas_cb.hide()

        # self.theme_button = FCButton(_("Apply Theme"))
        # self.theme_button.setToolTip(
        #     _("Select a theme for FlatCAM.\n"
        #       "It will theme the plot area.\n"
        #       "The application will restart after change.")
        # )
        # grid0.addWidget(self.theme_button, 2, 0, 1, 3)

        # Kept as a non-visible compatibility field. The application layout is fixed to standard.
        self.layout_combo = FCComboBox()
        self.layout_combo.addItem("standard")
        self.layout_combo.setCurrentIndex(0)

        # Enable Hover box
        self.hover_cb = FCCheckBox('%s' % _('Hover Shape'))
        self.hover_cb.setToolTip(
            _("Enable display of a hover shape for the application objects.\n"
              "It is displayed whenever the mouse cursor is hovering\n"
              "over any kind of not-selected object.")
        )
        grid0.addWidget(self.hover_cb, 4, 0, 1, 3)

        # Enable Selection box
        self.selection_cb = FCCheckBox('%s' % _('Selection Shape'))
        self.selection_cb.setToolTip(
            _("Enable the display of a selection shape for the application objects.\n"
              "It is displayed whenever the mouse selects an object\n"
              "either by clicking or dragging mouse from left to right or\n"
              "right to left.")
        )
        grid0.addWidget(self.selection_cb, 6, 0, 1, 3)

        # Enable Selection box
        self.selection_outline_cb = FCCheckBox('%s' % _('Selection Outline'))
        self.selection_outline_cb.setToolTip(
            _("If checked, the selection shape is an outline.")
        )
        grid0.addWidget(self.selection_outline_cb, 7, 0, 1, 3)

        # Kept as a non-visible compatibility field. Preferences always use the normal layout.
        self.gui_lay_combo = FCComboBox2()
        self.gui_lay_combo.addItems([_("Normal"), _("Columnar")])
        self.gui_lay_combo.setCurrentIndex(0)

        # Font Size
        self.font_size_lbl = FCLabel('%s:' % _("Font Size"))
        self.font_size_lbl.setToolTip(
            _("Setting the Font Size for the entire application.")
        )
        self.app_font_size_entry = FCSpinner()
        self.app_font_size_entry.set_range(9, 18)

        grid0.addWidget(self.font_size_lbl, 9, 0)
        grid0.addWidget(self.app_font_size_entry, 9, 1)

        # Apply UI parameters
        self.apply_app_font_size_btn = FCButton(_("Apply and Restart"), bold=True)
        self.apply_app_font_size_btn.setToolTip(
            _("Setting the Font Size for the entire application.")
        )
        grid0.addWidget(self.apply_app_font_size_btn, 11, 0, 1, 2)

        # #############################################################################################################
        # Grid1 Frame
        # #############################################################################################################
        self.color_lbl = FCLabel('%s' % _("Colors"), bold=True)
        self.layout.addWidget(self.color_lbl)

        color_frame = FCFrame()
        self.layout.addWidget(color_frame)
        self.color_lbl.hide()
        color_frame.hide()

        grid1 = GLay(v_spacing=5, h_spacing=3)
        color_frame.setLayout(grid1)

        # Plot Selection (left - right) Color
        self.sel_lr_label = FCLabel('%s' % _('Left-Right Selection Color'), bold=True)
        grid1.addWidget(self.sel_lr_label, 0, 0, 1, 2)

        self.sl_color_label = FCLabel('%s:' % _('Outline'))
        self.sl_color_label.setToolTip(
            _("Set the line color for the 'left to right' selection box.")
        )
        self.sl_color_entry = FCColorEntry(icon=QtGui.QIcon(self.app.resource_location + '/set_colors64.png'))

        grid1.addWidget(self.sl_color_label, 2, 0)
        grid1.addWidget(self.sl_color_entry, 2, 1)

        self.sf_color_label = FCLabel('%s:' % _('Fill'))
        self.sf_color_label.setToolTip(
            _("Set the fill color for the selection box\n"
              "in case that the selection is done from left to right.\n"
              "First 6 digits are the color and the last 2\n"
              "digits are for alpha (transparency) level.")
        )
        self.sf_color_entry = FCColorEntry(icon=QtGui.QIcon(self.app.resource_location + '/set_colors64.png'))

        grid1.addWidget(self.sf_color_label, 4, 0)
        grid1.addWidget(self.sf_color_entry, 4, 1)

        # Plot Selection (left - right) Fill Transparency Level
        self.left_right_alpha_label = FCLabel('%s:' % _('Alpha'))
        self.left_right_alpha_label.setToolTip(
            _("Set the fill transparency for the 'left to right' selection box.")
        )
        self.left_right_alpha_entry = FCSliderWithSpinner(0, 255, 1)

        grid1.addWidget(self.left_right_alpha_label, 6, 0)
        grid1.addWidget(self.left_right_alpha_entry, 6, 1)

        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        grid1.addWidget(separator_line, 8, 0, 1, 2)

        # Plot Selection (left - right) Color
        self.sel_rl_label = FCLabel('%s' % _('Right-Left Selection Color'), bold=True)
        grid1.addWidget(self.sel_rl_label, 10, 0, 1, 2)

        # Plot Selection (right - left) Line Color
        self.alt_sl_color_label = FCLabel('%s:' % _('Outline'))
        self.alt_sl_color_label.setToolTip(
            _("Set the line color for the 'right to left' selection box.")
        )
        self.alt_sl_color_entry = FCColorEntry(icon=QtGui.QIcon(self.app.resource_location + '/set_colors64.png'))

        grid1.addWidget(self.alt_sl_color_label, 12, 0)
        grid1.addWidget(self.alt_sl_color_entry, 12, 1)

        # Plot Selection (right - left) Fill Color
        self.alt_sf_color_label = FCLabel('%s:' % _('Fill'))
        self.alt_sf_color_label.setToolTip(
            _("Set the fill color for the selection box\n"
              "in case that the selection is done from right to left.\n"
              "First 6 digits are the color and the last 2\n"
              "digits are for alpha (transparency) level.")
        )
        self.alt_sf_color_entry = FCColorEntry(icon=QtGui.QIcon(self.app.resource_location + '/set_colors64.png'))

        grid1.addWidget(self.alt_sf_color_label, 14, 0)
        grid1.addWidget(self.alt_sf_color_entry, 14, 1)

        # Plot Selection (right - left) Fill Transparency Level
        self.right_left_alpha_label = FCLabel('%s:' % _('Alpha'))
        self.right_left_alpha_label.setToolTip(
            _("Set the fill transparency for selection 'right to left' box.")
        )
        self.right_left_alpha_entry = FCSliderWithSpinner(0, 255, 1)

        grid1.addWidget(self.right_left_alpha_label, 16, 0)
        grid1.addWidget(self.right_left_alpha_entry, 16, 1)

        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        grid1.addWidget(separator_line, 18, 0, 1, 2)

        # ------------------------------------------------------------------
        # ----------------------- Editor Color -----------------------------
        # ------------------------------------------------------------------

        self.editor_color_label = FCLabel('%s' % _('Editor Color'), bold=True)
        grid1.addWidget(self.editor_color_label, 20, 0, 1, 2)

        # Editor Draw Color
        self.draw_color_label = FCLabel('%s:' % _('Drawing'))
        self.alt_sf_color_label.setToolTip(
            _("Set the color for the shape.")
        )
        self.draw_color_entry = FCColorEntry(icon=QtGui.QIcon(self.app.resource_location + '/set_colors64.png'))

        grid1.addWidget(self.draw_color_label, 22, 0)
        grid1.addWidget(self.draw_color_entry, 22, 1)

        # Editor Draw Selection Color
        self.sel_draw_color_label = FCLabel('%s:' % _('Selection'))
        self.sel_draw_color_label.setToolTip(
            _("Set the color of the shape when selected.")
        )
        self.sel_draw_color_entry = FCColorEntry(icon=QtGui.QIcon(self.app.resource_location + '/set_colors64.png'))

        grid1.addWidget(self.sel_draw_color_label, 24, 0)
        grid1.addWidget(self.sel_draw_color_entry, 24, 1)

        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        grid1.addWidget(separator_line, 26, 0, 1, 2)

        proj_item_lbl = FCLabel('%s' % _("Project Items Color"), bold=True)
        grid1.addWidget(proj_item_lbl, 27, 0, 1, 2)
        # ------------------------------------------------------------------
        # ----------------------- Project Settings -----------------------------
        # ------------------------------------------------------------------
        # Light Theme
        self.proj_settings_l_label = FCLabel('%s %s' % (_("Light"), _("Theme")), bold=True)
        grid1.addWidget(self.proj_settings_l_label, 28, 0, 1, 2)

        # Project Tab items color
        self.proj_color_l_label = FCLabel('%s:' % _('Enabled'))
        self.proj_color_l_label.setToolTip(
            '%s %s' % (_("Set the color of the items in Project Tab Tree."), _("Light Theme."))
        )
        self.proj_color_light_entry = FCColorEntry(icon=QtGui.QIcon(self.app.resource_location + '/set_colors64.png'))

        grid1.addWidget(self.proj_color_l_label, 30, 0)
        grid1.addWidget(self.proj_color_light_entry, 30, 1)

        self.proj_color_dis_l_label = FCLabel('%s:' % _('Disabled'))
        self.proj_color_dis_l_label.setToolTip(
            '%s %s' % (
                _("Set the color of the items in Project Tab Tree,\n"
                  "for the case when the items are disabled."),
                _("Light Theme."))
        )
        self.proj_color_dis_light_entry = FCColorEntry(icon=QtGui.QIcon(
            self.app.resource_location + '/set_colors64.png'))

        grid1.addWidget(self.proj_color_dis_l_label, 32, 0)
        grid1.addWidget(self.proj_color_dis_light_entry, 32, 1)

        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        grid1.addWidget(separator_line, 33, 0, 1, 2)

        # Dark Theme
        self.proj_settings_d_label = FCLabel('%s %s' % (_("Dark"), _("Theme")), bold=True)
        grid1.addWidget(self.proj_settings_d_label, 34, 0, 1, 2)

        # Project Tab items color
        self.proj_color_d_label = FCLabel('%s:' % _('Enabled'))
        self.proj_color_d_label.setToolTip(
            '%s %s' % (_("Set the color of the items in Project Tab Tree."), _("Dark Theme."))
        )
        self.proj_color_dark_entry = FCColorEntry(icon=QtGui.QIcon(self.app.resource_location + '/set_colors64.png'))

        grid1.addWidget(self.proj_color_d_label, 36, 0)
        grid1.addWidget(self.proj_color_dark_entry, 36, 1)

        self.proj_color_dis_d_label = FCLabel('%s:' % _('Disabled'))
        self.proj_color_dis_d_label.setToolTip(
            '%s %s' % (
                _("Set the color of the items in Project Tab Tree,\n"
                  "for the case when the items are disabled."),
                _("Dark Theme."))
        )
        self.proj_color_dis_dark_entry = FCColorEntry(icon=QtGui.QIcon(
            self.app.resource_location + '/set_colors64.png'))

        grid1.addWidget(self.proj_color_dis_d_label, 38, 0)
        grid1.addWidget(self.proj_color_dis_dark_entry, 38, 1)

        GLay.set_common_column_size([grid0, grid1], 0)

        # Project autohide CB
        self.project_autohide_cb = FCCheckBox(label=_('Project AutoHide'))
        self.project_autohide_cb.setToolTip(
            _("Check this box if you want the project/selected/tool tab area to\n"
              "hide automatically when there are no objects loaded and\n"
              "to show whenever a new object is created.")
        )

        self.layout.addWidget(self.project_autohide_cb)

        self.hover_cb.hide()
        self.selection_outline_cb.hide()

        self.layout.addStretch()

        # #############################################################################
        # ############################# GUI COLORS SIGNALS ############################
        # #############################################################################

        # Setting selection (left - right) colors signals
        self.sf_color_entry.editingFinished.connect(self.on_sf_color_entry)
        self.sl_color_entry.editingFinished.connect(self.on_sl_color_entry)

        self.left_right_alpha_entry.valueChanged.connect(self.on_left_right_alpha_changed)  # alpha

        # Setting selection (right - left) colors signals
        self.alt_sf_color_entry.editingFinished.connect(self.on_alt_sf_color_entry)
        self.alt_sl_color_entry.editingFinished.connect(self.on_alt_sl_color_entry)

        self.right_left_alpha_entry.valueChanged.connect(self.on_right_left_alpha_changed)  # alpha

        # Setting Editor Draw colors signals
        self.draw_color_entry.editingFinished.connect(self.on_draw_color_entry)
        self.sel_draw_color_entry.editingFinished.connect(self.on_sel_draw_color_entry)

        self.proj_color_light_entry.editingFinished.connect(self.on_proj_color_light_entry)
        self.proj_color_dis_light_entry.editingFinished.connect(self.on_proj_color_dis_light_entry)

        self.proj_color_dark_entry.editingFinished.connect(self.on_proj_color_dark_entry)
        self.proj_color_dis_dark_entry.editingFinished.connect(self.on_proj_color_dis_dark_entry)

        self.apply_app_font_size_btn.clicked.connect(
            lambda: self.handle_font_size(self.app, self.app_font_size_entry.get_value()))

        # Set UI
        q_settings = QSettings("Open Source", "FlatCAM_Plus")
        if q_settings.contains("font_size"):
            font_size = int(q_settings.value("font_size", type=str))  # noqa
            self.app_font_size_entry.set_value(font_size)

    @staticmethod
    def handle_font_size(app, val):
        settings = QSettings("Open Source", "FlatCAM_Plus")
        settings.setValue('font_size', str(val))
        # This will write the setting to the platform specific storage.
        del settings

        restart_program(app=app)

    # Setting selection colors (left - right) handlers
    def on_sf_color_entry(self):
        self.app.options['global_sel_fill'] = self.app.options['global_sel_fill'][7:9]

    def on_sl_color_entry(self):
        self.app.options['global_sel_line'] = self.sl_color_entry.get_value()[:7] + \
            self.app.options['global_sel_line'][7:9]

    def on_left_right_alpha_changed(self, spinner_value):
        """
        Change the alpha level for the color of the selection box when selection is done left to right.
        Called on valueChanged of a FCSliderWithSpinner.

        :param spinner_value:   passed value within [0, 255]
        :type spinner_value:    int
        :return:                None
        :rtype:
        """

        self.app.options['global_sel_fill'] = self.app.options['global_sel_fill'][:7] + \
            (hex(spinner_value)[2:] if int(hex(spinner_value)[2:], 16) > 0 else '00')
        self.app.options['global_sel_line'] = self.app.options['global_sel_line'][:7] + \
            (hex(spinner_value)[2:] if int(hex(spinner_value)[2:], 16) > 0 else '00')

    # Setting selection colors (right - left) handlers
    def on_alt_sf_color_entry(self):
        self.app.options['global_alt_sel_fill'] = self.alt_sf_color_entry.get_value()[:7] + \
                                                   self.app.options['global_alt_sel_fill'][7:9]

    def on_alt_sl_color_entry(self):
        self.app.options['global_alt_sel_line'] = self.alt_sl_color_entry.get_value()[:7] + \
                                                   self.app.options['global_alt_sel_line'][7:9]

    def on_right_left_alpha_changed(self, spinner_value):
        """
        Change the alpha level for the color of the selection box when selection is done right to left.
        Called on valueChanged of a FCSliderWithSpinner.

        :param spinner_value:   passed value within [0, 255]
        :type spinner_value:    int
        :return:                None
        :rtype:
        """

        self.app.options['global_alt_sel_fill'] = self.app.options['global_alt_sel_fill'][:7] + \
            (hex(spinner_value)[2:] if int(hex(spinner_value)[2:], 16) > 0 else '00')
        self.app.options['global_alt_sel_line'] = self.app.options['global_alt_sel_line'][:7] + \
            (hex(spinner_value)[2:] if int(hex(spinner_value)[2:], 16) > 0 else '00')

    # Setting Editor colors
    def on_draw_color_entry(self):
        self.app.options['global_draw_color'] = self.draw_color_entry.get_value()

    def on_sel_draw_color_entry(self):
        self.app.options['global_sel_draw_color'] = self.sel_draw_color_entry.get_value()

    def on_proj_color_light_entry(self):
        self.app.options['global_proj_item_color_light'] = self.proj_color_light_entry.get_value()

    def on_proj_color_dis_light_entry(self):
        self.app.options['global_proj_item_dis_color_light'] = self.proj_color_dis_light_entry.get_value()

    def on_proj_color_dark_entry(self):
        self.app.options['global_proj_item_color_dark'] = self.proj_color_dark_entry.get_value()

    def on_proj_color_dis_dark_entry(self):
        self.app.options['global_proj_item_dis_color_dark'] = self.proj_color_dis_dark_entry.get_value()
