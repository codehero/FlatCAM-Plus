# PCB Pen Plotter Physical Test Protocol

Bu protokol yazilim hazir olduktan sonra MKS DLC32/GRBL mini CNC uzerinde
guvenli ilk denemeler icindir.

## Mekanik Hazirlik

- Yayli veya floating pen holder kullan.
- Kalem ucu tablaya dik dursun.
- Kalem yatak boslugu olmasin ama Z hareketinde hafif yaylansin.
- Kagit veya bakir yuzeyi tabla uzerine duz sabitle.
- Z sifirini kalem kagida/bakira hafif temas ettigi noktada al.

## Kalem Test Listesi

Kagit icin:

- 0.3 mm teknik kalem
- 0.4 mm fineliner
- 0.5 mm permanent marker

Bakir/asit icin:

- Etch-resistant PCB marker
- Edding 3000/400 gibi kalin permanent marker
- Ince permanent marker, sadece kisa test icin

Kalem seciminde oncelik: asitte cozulmeme, cizgi surekliligi, hizli kuruma.

## Kagit Test Parametreleri

- Pen up Z: `3.0 mm`
- Pen down Z: `-0.3 mm`
- Draw feed: `600 mm/min`
- Z feed: `200 mm/min`
- Rapid feed: `1500 mm/min`

Basinc fazla ise:

- Pen down Z: `-0.2 mm`
- Gerekirse `-0.1 mm`

Cizgi kopuksa:

- Pen down Z: `-0.4 mm`
- Draw feed: `400 mm/min`

## Bakir Test Parametreleri

- Bakir yuzeyi ince zimpara veya temizleyici ile oksitten arindir.
- Yuzeyi yagdan temizle.
- Pen down Z icin kagit testinden daha kucuk basinc ile basla.
- Baslangic Pen down Z: `-0.2 mm`
- Draw feed: `300 - 500 mm/min`
- Cizim sonrasi murekkebin kurumasini bekle.

## Z Ekseni Kontrolu

MKS DLC32 uzerinde ilk test sirasi:

1. `$H` veya manuel referans durumunu kendi makine kurulumuna gore dogrula.
2. `G21` ve `G90` modlarini kontrol et.
3. `G00 Z3.000` ile yukari hareketi dogrula.
4. `G01 Z-0.100 F100` ile cok kucuk temas denemesi yap.
5. Z ekseninde ters hareket varsa testi durdur ve motor yon/ayarlarini duzelt.

## Asit Sonrasi Degerlendirme

Basarili test kriterleri:

- Trace kenarlari kopmadan kalmis.
- Pad cevrelerinde delik veya incelme yok.
- Cizgi genisligi tasarima gore yeterli.
- Asit bakir altina fazla yurmemis.
- Transfer veya dogrudan cizim yonu dogru.

Sorun ve aksiyonlar:

- Kopuk iz: daha yavas draw feed veya daha fazla pen down.
- Yayilan murekkep: daha az pen down veya daha ince kalem.
- Asitte cozulme: farkli marker veya daha uzun kuruma.
- Boyut hatasi: steps/mm, kayis gerginligi ve mirror/origin kontrolu.
