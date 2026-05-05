# FlatCAM Plus CNC 3D Preview Module
# License: FlatCAM Plus CNC 3D Preview Module Non-Commercial License.
# See appPlugins/cnc_preview_3d/LICENSE.

import builtins
import gettext

from PyQt6 import QtWidgets

from appGUI.GUIElements import FCLabel

import appTranslation as fcTranslate

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class PreviewSectionPlugin:
    section_id = ""
    title = ""

    def build_panel(self, ui):
        panel, body = ui.create_panel(self.title)
        self.build(ui, body)
        return panel

    def build(self, ui, body):
        raise NotImplementedError


class JobSelectorSection(PreviewSectionPlugin):
    section_id = "job_selector"
    title = _("CNCJob Source")

    def build(self, ui, body):
        selector_lay = QtWidgets.QHBoxLayout()
        selector_lay.setContentsMargins(0, 0, 0, 0)
        selector_lay.setSpacing(6)
        selector_lay.addWidget(ui.job_combo, 1)
        selector_lay.addWidget(ui.refresh_btn)
        body.addLayout(selector_lay)

        ui.source_hint = FCLabel(_("Select a generated CNCJob object to render."))
        ui.source_hint.setWordWrap(True)
        body.addWidget(ui.source_hint)


class RenderInfoSection(PreviewSectionPlugin):
    section_id = "render_info"
    title = _("Preview Stats")

    def build(self, ui, body):
        grid = QtWidgets.QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        body.addLayout(grid)

        rows = [
            (_("Lines"), ui.lines_value),
            (_("Cut Paths"), ui.cut_value),
            (_("Drills"), ui.drill_value),
            (_("Bounds"), ui.bounds_value),
        ]
        for row, (label, value) in enumerate(rows):
            grid.addWidget(FCLabel(label, bold=True), row, 0)
            grid.addWidget(value, row, 1)

        ui.status_label.setWordWrap(True)
        body.addWidget(ui.status_label)


DEFAULT_PREVIEW_SECTIONS = {
    "job_selector": JobSelectorSection,
    "render_info": RenderInfoSection,
}
