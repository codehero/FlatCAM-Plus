# FlatCAM Plus Pen Plotter Tasks

Bu dosya, plotter entegrasyonu boyunca canli gorev takip dosyasidir.
Her tamamlanan is burada isaretlenecek.

## Durum Ozeti

- Baslangic tarihi: 2026-05-24
- Hedef kart: MKS DLC32 / GRBL
- Mevcut CAM: FlatCAM Plus
- Yaklasim: Mevcut CNC yapisini bozmadan ayri plotter preprocessor ve akisi

## Faz 0 - Guvenli Baslangic ve Mimari Okuma

- [x] Kullanici proje yedegini aldigini bildirdi.
- [x] Git durumunu kontrol et.
- [x] Mevcut kullanici degisikliklerini tespit et ve dokunmadan ilerle.
- [x] Preprocessor yukleme mekanizmasini incele.
- [x] GRBL preprocessor ornegini incele.
- [x] Milling/Isolation tarafinda preprocessor secim anahtarlarini bul.
- [x] Follow/Paint akisinin varligini dogrula.
- [x] Roadmap dosyasini olustur.
- [x] Task takip dosyasini olustur.

Notlar:

- Mevcut degisik dosyalar: `appDatabase.py`, `appPlugins/ToolCNCControl.py`,
  `appPlugins/ToolIsolation.py`, `appPlugins/ToolMilling.py`, `camlib.py`,
  `defaults.py`.
- Ilk MVP icin en dusuk riskli yol yeni bir preprocessor dosyasi eklemek.

## Faz 1 - MVP GRBL Pen Plotter Preprocessor

- [x] Yeni `preprocessors/GRBL_11_pen_plotter.py` dosyasini ekle.
- [x] `GRBL_11_no_M6` davranisini temel al.
- [x] Baslangic G-code basligini plotter amacina gore duzenle.
- [x] `G21`, `G90`, `G17`, `G94` baslangiclarini koru.
- [x] `M03/M04` spindle baslatma komutlarini uretme.
- [x] `M05` spindle durdurma komutunu opsiyonel/zararsiz hale getir.
- [x] Toolchange davranisini plotter icin sade ve guvenli hale getir.
- [x] `z_move` degerini pen up olarak kullan.
- [x] `z_cut` degerini pen down olarak kullan.
- [x] XY linear hareketlerinde draw feed kullanildigini kod seviyesinde dogrula.
- [x] Z plunge hareketlerinde Z feed kullanildigini kod seviyesinde dogrula.
- [x] Kod import/syntax kontrolu yap.

## Faz 2 - Preprocessor Secimi ve Varsayilanlar

- [x] Yeni preprocessor otomatik yukleniyor mu kontrol et.
- [x] `tools_mill_preprocessor_list` icine gerekirse plotter adini ekle.
- [x] Varsayilan milling profilini bozmadan plotter preset stratejisini belirle.
- [x] Pen plotter icin onerilen degerleri uygulama icinde ayri tut.
- [x] Mevcut kullanici degisiklikleri olan `defaults.py` ile cakisma riskini kontrol et.

Not:

- `appMain.py` preprocessor listesini acilista dinamik doldurdugu icin su anda
  `defaults.py` dosyasina dokunmak gerekmiyor.
- Plotter degerleri ayri `tools_plotter_*` opsiyonlari olarak eklendi.
- `PCB Plotter` panelindeki `Apply Preset`, Milling degerlerini sadece kullanici
  istediginde plotter presetine cevirir.

## Faz 3 - Plotter Is Akisi

- [x] Gerber Follow ile merkez cizgi akisini test et.
- [x] Paint/Fill ile bakirda kalacak alan doldurma akisini test et.
- [x] Mirror gereksinimini layer/transfer tipine gore dokumante et.
- [x] Ornek PCB test geometrisi icin adimlari yaz.
- [x] Kagit testinden bakir testine gecis protokolunu yaz.

Not:

- Is akisi `PLOTTER_WORKFLOW.md` dosyasinda dokumante edildi.
- Follow tarzi test: `assets/examples/pen_plotter_follow_trace_test.gcode`.
- Fill tarzi test: `assets/examples/pen_plotter_fill_hatch_test.gcode`.

## Faz 4 - GUI/Preset Entegrasyonu

- [x] Plotter icin en uygun UI noktasini belirle: Milling preset mi, ayri Tool mu?
- [x] Pen width kontrolu.
- [x] Pen down Z kontrolu.
- [x] Pen up Z kontrolu.
- [x] Draw feed kontrolu.
- [x] Z feed kontrolu.
- [x] Mirror secimi.
- [x] Follow/Fill modu secimi.
- [x] Export Plotter G-code aksiyonu.
- [x] Fill modunda tum kart yuzeyini dolduran Paint davranisini kaldir.
- [x] Fill modunda sadece trace/pad poligonlarindan `_plotter_fill` Geometry uret.

Not:

- Ayri `PCB Plotter` plugin'i eklendi.
- Panel, Milling aracina guvenli plotter preset uygular ve Follow/Paint/Milling
  akislarini tek yerden acar.
- Tools Database icine `Plotter Pen` preset'i otomatik eklenir.
- `PCB Plotter` paneli `Plotter Pen` ayarlarini DB'den okur.
- `Load from DB` ile farkli plotter preset'i transfer edilebilir.

## Faz 4.1 - Tools DB Plotter Pen Entegrasyonu

- [x] Tools DB icin `Plotter Pen` default kaydini tanimla.
- [x] Mevcut kullanici DB kaydini ezmeden eksik alanlari tamamla.
- [x] `Plotter Pen` kaydini Milling hedefli preset olarak ayarla.
- [x] DB kaydinda `GRBL_11_pen_plotter` preprocessor bilgisini tut.
- [x] `PCB Plotter` panelini acilista DB kaydindan doldur.
- [x] `PCB Plotter` paneline `Load from DB` aksiyonu ekle.
- [x] Tools DB transfer callback'ini plotter paneline bagla.

## Faz 4.2 - Plotter UI Akis Duzeltmeleri

- [x] `PCB Plotter` kisayolunu toolbar'a ekle.
- [x] `Follow` butonunu `Generate Follow Path` olarak guncelle.
- [x] `Generate Fill` butonunu `Generate Fill Path` olarak guncelle.
- [x] Plotter panelinden `Milling` butonunu kaldir.
- [x] Plotter panelinden `Open 20x20 Test` butonunu kaldir.
- [x] `Generate Follow Path` ile dogrudan plotter geometry olustur.
- [x] `Generate Fill Path` sonrasi olusan plotter geometry'yi otomatik sec.
- [x] Olusan plotter geometry icin sag properties panelini otomatik ac.
- [x] Plotter geometry properties panelinde `Milling` butonunu `Generate` yap.
- [x] Plotter geometry properties panelinde `Paint`, `NCC`, `Utilities` ve `Transformations` alanlarini gizle.
- [x] Plotter geometry uzerinden acilan CNCJob panelinde basligi `Plotter Operation` yap.
- [x] Plotter operation panelinde Excellon tip secenegini gizle.
- [x] `Parameters for Tool 1` alanini plotter icin `Pen Parameters` yap.
- [x] Plotter operation panelinde `Shape` secenegini gizle.
- [x] Plotter operation panelinde `Cut Z` etiketini `Z-Offset` yap.
- [x] Plotter operation panelinde spindle/dwell alanlarini gizle.
- [x] Plotter operation panelinde `Common Parameters` bolumunu gizle.
- [x] `Generate CNCJob object` butonunu plotter icin `Generate Plotter Job` yap.

## Faz 5 - G-code Guvenlik Kontrolleri

- [x] Uretilen G-code icinde `M03`/`M04` aramasi yap.
- [x] Z minimum/maksimum hareketlerini kontrol et.
- [x] `G20/G21` unit secimini kontrol et.
- [x] `G90` absolute mode kontrolu yap.
- [x] Kalem yukari hareketlerinin travel oncesi geldigini dogrula.
- [x] Ilk test icin 20x20 mm kare G-code uret.

Not:

- Ilk duman testi preprocessor seviyesinde yapildi. Tam CNCJob uretimi sonraki
  dogrulama adiminda ayrica test edilecek.
- Ilk kagit testi dosyasi: `assets/examples/pen_plotter_20x20_square.gcode`.
- G-code validator: `scripts/validate_pen_plotter_gcode.py`.

## Faz 6 - Fiziksel Test Hazirligi

- [x] Yayli/floating pen holder gereksinimini not et.
- [x] Kalem tipi icin test listesi hazirla.
- [x] Kagit test parametrelerini yaz.
- [x] Bakir plaka test parametrelerini yaz.
- [x] Asit sonrasi sonuc degerlendirme kriterlerini yaz.

Not:

- Fiziksel test hazirligi `PLOTTER_TEST_PROTOCOL.md` dosyasinda dokumante edildi.

## Acik Kararlar

- [x] Plotter sadece preprocessor olarak mi kalacak, yoksa ayri GUI modulu olacak mi?
- [x] Ilk hedef dogrudan bakira cizim mi, kagit transfer mi?
- [x] Kalem cizgi genisligi icin baslangic degeri kesinlesecek mi?
- [x] MKS DLC32 uzerinde Z ekseni step/mm ve limit davranisi test edilecek mi?

Kararlar:

- Ayri GUI modulu eklendi: `PCB Plotter`.
- Ilk hedef: dogrudan bakira etch-resistant kalemle cizim; kagit transfer ikinci asama.
- Baslangic pen width: `0.4 mm`.
- Z step/mm ve limit davranisi fiziksel test protokolunde ilk kontrol adimi olarak yer alacak.

## Kisa Kullanim Hedefi

Ilk calisir surumde beklenen akis:

1. Gerber dosyasini ac.
2. Gerekirse mirror uygula.
3. `Generate Follow Path` veya `Generate Fill Path` ile plotter Geometry olustur.
4. Otomatik acilan plotter Geometry panelinde `Generate` butonuna bas.
5. `Plotter Operation` panelinde pen Z-offset ve feed degerlerini kontrol et.
6. `Generate Plotter Job` ile CNCJob olustur.
7. G-code'u kontrol et.
8. Kagit uzerinde test et.
