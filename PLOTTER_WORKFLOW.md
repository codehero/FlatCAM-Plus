# PCB Pen Plotter Workflow

Bu belge, FlatCAM Plus icindeki yeni `PCB Plotter` paneli ve
`GRBL_11_pen_plotter` preprocessor ile kullanilacak pratik is akisidir.

## Yazilim Karari

Plotter entegrasyonu ayri bir GUI modulu olarak eklendi:

- Panel: `Plugins > PCB Plotter`
- Tools DB preset: `Plotter Pen`
- Preprocessor: `GRBL_11_pen_plotter`
- Ana uretim araci: plotter geometry uzerinden acilan `Plotter Operation` paneli
- Geometri hazirlama: `Generate Follow Path` ve `Generate Fill Path`

Bu karar mevcut CNC/freze akisina dokunmadan kalem icin ayri bir preset ve
guvenli G-code cikisi saglar.

## Tools DB Kullanimi

Uygulama acilisinda Tools Database icine `Plotter Pen` isimli bir preset eklenir.
Kayit zaten varsa kullanici ayarlari ezilmez, sadece eksik alanlar tamamlanir.

`Plotter Pen` kaydinin ana degerleri:

- Target: `Milling`
- Diameter: `0.4 mm`
- Cut Z / Pen down Z: `-0.3 mm`
- Travel Z / Pen up Z: `3.0 mm`
- Feedrate XY: `600 mm/min`
- Feedrate Z: `200 mm/min`
- Feedrate rapid: `1500 mm/min`
- Preprocessor: `GRBL_11_pen_plotter`

Kullanim:

1. `Plugins > PCB Plotter` ac.
2. Panel acilirken `Plotter Pen` DB kaydi okunur.
3. Farkli bir DB preset'i secmek istersen `Load from DB` kullan.
4. `Apply Preset` ile bu ayarlari Milling tarafina uygula.

Milling aracinda da `Add from DB` ile `Plotter Pen` dogrudan secilebilir.

## Baslangic Preseti

`PCB Plotter` panelindeki baslangic degerleri Tools DB'deki `Plotter Pen`
kaydindan gelir:

- Pen width: `0.4 mm`
- Pen down Z: `-0.3 mm`
- Pen up Z: `3.0 mm`
- Draw feed: `600 mm/min`
- Z feed: `200 mm/min`
- Rapid feed: `1500 mm/min`
- Preprocessor: `GRBL_11_pen_plotter`

Bu degerler ilk kagit testi icindir. Kalem baskisi fazla ise `Pen down Z`
degerini sifira yaklastir.

## Follow Akisi

Ince PCB izlerini merkez cizgisi gibi cizmek icin:

1. Gerber dosyasini ac.
2. `PCB Plotter` panelinde `Mode = Follow` sec.
3. Transfer yontemine gore mirror sec ve gerekiyorsa `Apply Mirror` kullan.
4. Gerekirse `Load from DB` ile `Plotter Pen` presetini yukle.
5. `Apply Preset` ile plotter ayarlarini uygula.
6. `Generate Follow Path` ile plotter geometry uret.
7. Otomatik acilan geometry panelinde `Generate` butonuna bas.
8. `Plotter Operation` panelinde Z-offset ve feed degerlerini kontrol et.
9. `Generate Plotter Job` ile CNCJob uret.
10. `Export Plotter G-code` ile G-code kaydet.
11. G-code'u `scripts/validate_pen_plotter_gcode.py` ile kontrol et.

Follow modu, sadece cizgi izlemek icin uygundur. Asitlemede kalacak bakir alanin
tam kaplanmasi gerekiyorsa Fill akisini kullan.

## Fill Akisi

Bakirda kalacak alanlari kalemle doldurmak icin:

1. Gerber dosyasini ac.
2. `PCB Plotter` panelinde `Mode = Fill` sec.
3. Pen width degerini kullandigin kalemin gercek cizgi genisligine ayarla.
4. `Apply Preset` ile plotter ayarlarini uygula.
5. `Generate Fill Path` ile sadece trace/pad alanlarindan `_plotter_fill` Geometry uret.
6. Otomatik acilan geometry panelinde `Generate` butonuna bas.
7. `Generate Plotter Job` ile CNCJob uret.
8. `Export Plotter G-code` ile kaydet ve validator ile kontrol et.

Fill modu, etch-resistant kalemle dogrudan bakira cizimde daha guvenilir
sonuc verir. Bu mod Paint aracini kullanmaz; buyuk board/background poligonlari
otomatik elenir ve sadece kucuk copper trace/pad poligonlari hatch cizgileriyle
doldurulur.

## Mirror Karari

- Dogrudan bakira cizim: katman tarafina gore gerekirse mirror uygula.
- Kagida cizip bakira transfer: genelde mirror gerekir.
- Top layer dogrudan bakir: cogu zaman mirror gerekmez.
- Bottom layer dogrudan bakir: tasarim/gerber cikisina gore kontrol gerekir.

Ilk testte PCB icine okunabilir `TOP` veya `BOT` yazisi koymak yon hatalarini
hizli yakalar.

## Ornek Test Geometrisi

Ilk mekanik test icin:

- 20x20 mm kare
- Bir adet yatay cizgi
- Bir adet dikey cizgi
- Bir adet `TOP` ya da `BOT` yazisi

Mevcut hazir test dosyasi:

- `assets/examples/pen_plotter_20x20_square.gcode`

## Kagittan Bakira Gecis

1. Havada kuru kosu yap.
2. Kagitta 20x20 mm kare testini ciz.
3. Kalem temasini ayarla.
4. PCB outline veya basit trace testini kagitta ciz.
5. Bakir plaka uzerinde kucuk test kuponu ciz.
6. Kuruma suresi ver.
7. Asit sonrasi kenar, kopuk ve delik durumunu kontrol et.

Kagit transfer yerine dogrudan bakira etch-resistant kalemle cizim ilk hedef
olarak secildi; kagit transfer ikinci asama olarak kalacak.

## G-code Guvenlik Kontrolu

Ornek:

```powershell
python scripts\validate_pen_plotter_gcode.py assets\examples\pen_plotter_20x20_square.gcode
```

Kontrol edilenler:

- `M03` / `M04` yok.
- `G20` veya `G21` var.
- `G90` var.
- Ilk XY hareketinden once pen-up Z hareketi var.
- Pen asagidayken rapid XY travel yok.
