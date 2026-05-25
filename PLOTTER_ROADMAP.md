# FlatCAM Plus Pen Plotter Roadmap

Bu roadmap, MKS DLC32/GRBL tabanli mevcut CNC yapisini bozmadan FlatCAM Plus icine
PCB kalem plotter akisi eklemek icin kullanilacak ana plandir.

## Hedef

FlatCAM Plus icinde Gerber/Geometry nesnelerinden kalem plotter icin guvenli
GRBL G-code uretmek:

- Spindle/laser komutlari calismayacak.
- Z ekseni kalem yukari/kalem asagi olarak kullanilacak.
- Mevcut milling, isolation ve CNC control akislari korunacak.
- Plotter ayarlari ayri tutulacak ve geri alinabilir olacak.

## Faz 0 - Guvenli Baslangic ve Mimari Okuma

Durum: Tamamlandi.

Amac:

- Kullanici yedegini dogrulamak.
- FlatCAM Plus postprocessor yukleme akisini anlamak.
- Mevcut CNC, Milling, Isolation ve Follow/Paint akislari ile cakismadan ilerlemek.

Ilk bulgular:

- Preprocessor dosyalari `preprocessors/*.py` altindan yukleniyor.
- Preprocessor siniflari `appPreProcessor.PreProc` uzerinden otomatik kaydoluyor.
- Milling/Isolation tarafinda preprocessor secimi `tools_mill_ppname_g` ile yapiliyor.
- Gerber follow ve paint akislari zaten mevcut; plotter modu bunlari kullanabilir.

## Faz 1 - MVP: GRBL Pen Plotter Preprocessor

Durum: Ilk preprocessor eklendi ve duman testi gecti.

Amac:

- Yeni bir `GRBL_11_pen_plotter` preprocessor eklemek.
- Mevcut GRBL preprocessor davranisini temel almak.
- M3/M4/M5 gibi spindle bagimli komutlari plotter icin guvenli hale getirmek.
- `z_move` degerini kalem yukari, `z_cut` degerini kalem asagi kabul etmek.

Beklenen cikti:

- Preprocessor listesinde `GRBL_11_pen_plotter` gorunur.
- Geometry/Milling ile uretilen G-code kalem hareketi olarak calisir.
- MKS DLC32 tarafinda mevcut GRBL ayarlari degismeden kullanilir.

## Faz 2 - Plotter Varsayilanlari ve Profil Mantigi

Durum: Tamamlandi.

Amac:

- Kalem plotter icin guvenli baslangic degerleri tanimlamak.
- Kullanici freze profilini bozmadan plotter profili secilebilir hale getirmek.
- `Plotter Pen` presetini Tools Database icinde saklamak.

Baslangic degerleri:

- Pen width/tool dia: `0.4 mm`
- Pen down Z/cut Z: `-0.3 mm`
- Pen up Z/travel Z: `3.0 mm`
- XY feed: `600 mm/min`
- Z feed: `200 mm/min`
- Rapid feed: `1500 mm/min`
- Toolchange: kapali
- Spindle speed: bos/0

## Faz 3 - Is Akisi: Follow, Paint ve PCB Transfer

Durum: Tamamlandi.

Amac:

- Ince cizgiler icin Gerber Follow akisini belgelemek.
- Bakirda kalacak alanlar icin Paint/Fill akisini kullanmak.
- Kagida transfer ve dogrudan bakira cizim icin ayna/mirror kararini netlestirmek.

Karar notu:

- Kagida cizip bakira transfer edilecekse cogu durumda mirror gerekir.
- Dogrudan bakir uzerine etch-resistant kalem ile cizimde layer tarafina gore mirror karari verilir.
- Asit icin sadece merkez cizgisi yeterli olmayabilir; bakirda kalacak alanlar doldurulmalidir.

## Faz 4 - GUI Entegrasyonu: Plotter Paneli

Durum: Tamamlandi.

Amac:

- Mevcut Milling aracini bozmadan plotter icin sade bir panel ya da preset eklemek.
- Kullanici kalem parametrelerini tek yerden ayarlayabilsin.

Kontroller:

- Preprocessor secimi
- Pen width
- Pen down Z
- Pen up Z
- Draw feed
- Plunge feed
- Mirror secimi
- Follow/Fill modu
- Export plotter G-code
- Load from DB / Plotter Pen preset
- Trace/pad odakli fill geometry uretimi

## Faz 5 - G-code Dogrulama ve Simulasyon

Durum: Tamamlandi.

Amac:

- Uretilen G-code icinde riskli komutlari yakalamak.
- Kalem yukari/asagi hareketlerini ve XY sinirlarini kontrol etmek.

Kontroller:

- Spindle baslatma komutu yok ya da guvenli.
- Z hareketleri beklenen aralikta.
- G-code GRBL uyumlu.
- Ilk deneme icin kagit test dosyasi uretilmis.

## Faz 6 - Makine Test Protokolu

Durum: Hazirlik/protokol tamamlandi.

Amac:

- Yazilim tamamlandiktan sonra kontrollu fiziksel test akisi hazirlamak.

Test sirasi:

1. Havada kuru kosu.
2. Kalemsiz Z yukari/asagi testi.
3. Kagitta kare ve yazi testi.
4. Kagitta PCB outline/follow testi.
5. Bakir uzerinde kucuk test kuponu.
6. Asit sonrasi sonuc kontrolu.

## Kabul Kriterleri

- Mevcut CNC milling akisi etkilenmez.
- Yeni plotter preprocessor secilebilir.
- G-code MKS DLC32/GRBL icin guvenli bicimde uretilir.
- Kalem yukari/asagi Z hareketleri ayarlanabilir.
- Follow ve Paint tabanli PCB cizim akisi dokumante edilir.
- Ilk kagit testi icin ornek G-code uretilebilir.
