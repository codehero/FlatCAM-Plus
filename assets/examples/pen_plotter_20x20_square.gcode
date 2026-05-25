(FlatCAM Plus pen plotter 20x20 mm square smoke test)
(Set XY zero at the lower-left corner of the paper test area.)
(Set Z zero at light pen contact before running.)
(Pen up: Z3.000 mm)
(Pen down: Z-0.300 mm)
(Draw feed: 600 mm/min)
(Z feed: 200 mm/min)

M5
G21
G90
G17
G94

G00 Z3.000
G00 X0.000 Y0.000
G01 F200.0
G01 Z-0.300
G01 F600.0
G01 X20.000 Y0.000
G01 X20.000 Y20.000
G01 X0.000 Y20.000
G01 X0.000 Y0.000
G00 Z3.000
M5
