# ##########################################################
# FlatCAM PLUS: 2D Post-processing for Manufacturing       #
# File Updated By Sadri ERCAN - 2026                       #
# File Author: Sadri ERCAN                                 #
# Date:     05/25/2026                                     #
# License:  FlatCAM Plus CNC Control Module Non-Commercial License         #
# See:      appPlugins/cnc_control/LICENSE                  #
# ##########################################################

from appPreProcessor import PreProc


class GRBL_11_pen_plotter(PreProc):

    include_header = True
    coordinate_format = "%.*f"
    feedrate_format = "%.*f"

    def start_code(self, p):
        units = " " + str(p["units"]).lower()
        obj_options = p["obj_options"]
        coords_xy = p["xy_toolchange"]
        end_coords_xy = p["xy_end"]

        xmin = self.coordinate_format % (p.coords_decimals, obj_options["xmin"])
        xmax = self.coordinate_format % (p.coords_decimals, obj_options["xmax"])
        ymin = self.coordinate_format % (p.coords_decimals, obj_options["ymin"])
        ymax = self.coordinate_format % (p.coords_decimals, obj_options["ymax"])

        gcode = "(FlatCAM Plus GRBL pen plotter preprocessor.)\n"
        gcode += "(Target: GRBL/MKS DLC32 with Z used as pen up/down.)\n"
        gcode += "(No spindle or laser start command is emitted.)\n\n"

        if str(obj_options["type"]) == "Geometry":
            gcode += "(PEN WIDTH / TOOL DIAMETER: %s%s)\n" % (str(obj_options["tool_dia"]), units)
            gcode += "(Draw Feedrate XY: %s%s/min)\n" % (str(p["feedrate"]), units)
            gcode += "(Pen Down Feedrate Z: %s%s/min)\n" % (str(p["z_feedrate"]), units)
            gcode += "(Rapid Feedrate: %s%s/min)\n\n" % (str(p["feedrate_rapid"]), units)
            gcode += "(Pen Down Z: %s%s)\n" % (str(p["z_cut"]), units)
            gcode += "(Pen Up Z: %s%s)\n" % (str(p["z_move"]), units)

        if p["toolchange"] is True:
            gcode += "(Z Toolchange: %s%s)\n" % (str(p["z_toolchange"]), units)
            if coords_xy is not None:
                gcode += "(X,Y Toolchange: %.*f, %.*f%s)\n" % (
                    p.decimals, coords_xy[0], p.decimals, coords_xy[1], units
                )
            else:
                gcode += "(X,Y Toolchange: None%s)\n" % units

        gcode += "(Z Start: %s%s)\n" % (str(p["startz"]), units)
        gcode += "(Z End: %s%s)\n" % (str(p["z_end"]), units)
        if end_coords_xy is not None:
            gcode += "(X,Y End: %.*f, %.*f%s)\n" % (
                p.decimals, end_coords_xy[0], p.decimals, end_coords_xy[1], units
            )
        else:
            gcode += "(X,Y End: None%s)\n" % units

        gcode += "(Preprocessor Geometry: %s)\n" % str(p["pp_geometry_name"])
        gcode += "(X range: %9s ... %9s %s)\n" % (xmin, xmax, units)
        gcode += "(Y range: %9s ... %9s %s)\n\n" % (ymin, ymax, units)

        gcode += "M5\n"
        gcode += ("G20" if p.units.upper() == "IN" else "G21") + "\n"
        gcode += "G90\n"
        gcode += "G17\n"
        gcode += "G94\n"

        return gcode

    def startz_code(self, p):
        if p.startz is not None:
            return "G00 Z" + self.coordinate_format % (p.coords_decimals, p.startz)
        return ""

    def lift_code(self, p):
        return "G00 Z" + self.coordinate_format % (p.coords_decimals, p.z_move)

    def down_code(self, p):
        return "G01 Z" + self.coordinate_format % (p.coords_decimals, p.z_cut)

    def toolchange_code(self, p):
        z_toolchange = p.z_toolchange
        toolchangexy = p.xy_toolchange

        if int(p.tool) == 1 and p.startz is not None:
            z_toolchange = p.startz

        gcode = "M5\n"
        gcode += "G00 Z%s\n" % (self.coordinate_format % (p.coords_decimals, z_toolchange))

        if toolchangexy is not None:
            gcode += "G00 X%s Y%s\n" % (
                self.coordinate_format % (p.coords_decimals, toolchangexy[0]),
                self.coordinate_format % (p.coords_decimals, toolchangexy[1])
            )

        gcode += "(Install pen / verify pen height.)\n"
        gcode += "M0\n"
        gcode += "G00 Z%s" % (self.coordinate_format % (p.coords_decimals, z_toolchange))
        return gcode

    def up_to_zero_code(self, p):
        return "G01 Z0"

    def position_code(self, p):
        if p._bed_skew_x == 0:
            x_pos = p.x + p._bed_offset_x
        else:
            x_pos = (p.x + p._bed_offset_x) + ((p.y / p._bed_limit_y) * p._bed_skew_x)

        if p._bed_skew_y == 0:
            y_pos = p.y + p._bed_offset_y
        else:
            y_pos = (p.y + p._bed_offset_y) + ((p.x / p._bed_limit_x) * p._bed_skew_y)

        return ("X" + self.coordinate_format + " Y" + self.coordinate_format) % (
            p.coords_decimals, x_pos, p.coords_decimals, y_pos
        )

    def rapid_code(self, p):
        return ("G00 " + self.position_code(p)).format(**p)

    def linear_code(self, p):
        return ("G01 " + self.position_code(p)).format(**p)

    def end_code(self, p):
        coords_xy = p["xy_end"]
        gcode = "M5\n"
        gcode += "G00 Z" + self.feedrate_format % (p.fr_decimals, p.z_end) + "\n"

        if coords_xy and coords_xy != "":
            gcode += "G00 X{x} Y{y}".format(x=coords_xy[0], y=coords_xy[1]) + "\n"
        return gcode.rstrip()

    def feedrate_code(self, p):
        return "G01 F" + str(self.feedrate_format % (p.fr_decimals, p.feedrate))

    def z_feedrate_code(self, p):
        return "G01 F" + str(self.feedrate_format % (p.fr_decimals, p.z_feedrate))

    def spindle_code(self, p):
        return ""

    def dwell_code(self, p):
        return ""

    def spindle_stop_code(self, p):
        return "M5"
