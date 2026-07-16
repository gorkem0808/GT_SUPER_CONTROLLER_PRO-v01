# Profesyonel Dört Köşe Kalibrasyonu

Kalibrasyon operatöre yalnız gerekli adımları gösterir. **Ekranın ortasına nişan alma adımı yoktur.** Her silah için sıra:

```text
SOL ÜST → SAĞ ÜST → SAĞ ALT → SOL ALT
```

## Kalibrasyon programını açma

Normal durumda iki silahın hareketi her zaman aktiftir. Kalibrasyon oturumu şu iki yöntemden biriyle açılır:

```text
P1 START + P2 START → kesintisiz 10 saniye
```

veya Windows klavyesinde:

```text
2 + 5 → kesintisiz 10 saniye
```

10 saniye tamamlandığında sistem şu sırayı uygular:

1. Normal P1/P2 Start komutları iptal edilir; oyun yanlışlıkla başlamaz ve kredi harcanmaz.
2. Controller bakım moduna girer; coin, Start, bomba, tetik HID ve recoil çıkışları durur.
3. P1 ve P2 Gun Pico'ya `MOTION 0` gönderilir; iki nişangâhın X/Y hareketi pasif olur.
4. Küçültülmüş `GT SUPER CONTROLLER` uygulaması öne gelir ve **Kalibrasyon** sekmesi açılır.
5. Operatör kalibre edilecek oyuncuyu seçer.

Tuşlardan biri 10 saniye dolmadan bırakılırsa işlem tamamen iptal edilir. Ortak basış sırasında hiçbir Start darbesi oyuna iletilmez. Yeniden denemek için iki tuşun da tamamen bırakılması gerekir.

> Fiziksel Start kısayolunun Windows penceresini açabilmesi için uygulama Windows başlangıcında çalışmalı ve normal kullanımda küçültülmüş olarak beklemelidir.

## Dört köşe işlemi

1. İlgili oyuncu bölümünde **KALİBRASYONU BAŞLAT** düğmesine basın.
2. Tam ekrandaki **SOL ÜST** hedefe nişan alın; ilgili oyuncunun Controller'a bağlı tetiğine bir kez basıp bırakın.
3. Aynı işlemi **SAĞ ÜST**, **SAĞ ALT** ve **SOL ALT** için yapın.
4. Dördüncü noktadan sonra Gun firmware'i ölçümü doğrular.
5. Geçerli köşe değerleri CRC32 ve sıra numarasıyla çift sektörlü flash kaydına atomik olarak yazılır.
6. Uygulama ekrandaki **Kenar payı**, **X ters** ve **Y ters** değerlerini bağlı her Gun Pico’ya ayrı bir atomik `APPLY` komutuyla kaydeder.
7. Gerekli tüm cihazlardan `saved:true, profile:true` flash onayı alındığında önce iki silah otomatik **AKTİF** yapılır, ardından Controller bakım modu kapanır.

Başarılı işlem sonunda ayrıca elle kaydetmeye gerek yoktur. Sadece servis ayarları değiştirildiyse üstteki **KAYDET VE SİLAHLARI AKTİF ET** düğmesi bağlı Gun Pico'lara ayarları kaydeder ve iki silahı aktif eder.

## Başlatma kontrolleri

Program kalibrasyondan önce otomatik olarak şunları denetler:

- ortak Controller Pico bağlı mı,
- seçilen P1/P2 Gun Pico bağlı mı,
- ilgili oyuncunun Controller üzerindeki tetiği bırakılmış mı,
- başka bir oyuncunun kalibrasyonu çalışıyor mu.

Koşullardan biri uygun değilse kalibrasyon başlamaz ve önceki geçerli kayıt değiştirilmez.

## Güvenlik ve otomatik geri dönüş

Kalibrasyon oturumu açıkken:

- iki silahın X/Y HID hareketi kapalıdır,
- Controller klavye ve recoil çıkışları kapalıdır,
- ham ADC verisi ve tetik olayları kalibrasyon için çalışmaya devam eder,
- uygulama oturumu canlı tutmak için 60 saniyede bir bakım ve hareket kilidini yeniler,
- Gun ölçüm oturumu 120 saniye işlem yapılmazsa iptal edilir,
- Controller ve Gun hareket kilitleri 180 saniyede fail-safe olarak kendiliğinden açılır.

Uygulama çöker, USB ayrılır veya Windows yeniden başlarsa geçici pasif durum flash'a yazılmadığı için sistem normal açılışta **AKTİF** başlar. USB bağlantısı kesildiğinde yarım kalmış kalibrasyon atılır ve önceki geçerli ayar geri yüklenir.

Kalibrasyon iptal edilir veya hata oluşursa yeni ölçüm kaydedilmez. Önceki geçerli ayar korunur, bakım modu kapatılır ve iki silah yeniden aktif edilir.

## Otomatik ölçüm kalitesi

Her köşede firmware X ve Y eksenlerini aynı kısa zaman penceresinde 25 kez ölçer. Uç örnekleri dışarıda bırakır ve kararlı orta örneklerden tek değer üretir. Ölçüm sırasında silah hareket ederse nokta kaydedilmez; aynı hedef yeniden istenir.

Dört nokta sonunda firmware:

- yatay ve dikey hareket aralığını,
- köşelerin doğru sırada alınıp alınmadığını,
- üst/alt ve sol/sağ kenarların tutarlılığını,
- örnek kararlılığını

kontrol eder. Geçersiz sonuçta önceki kalibrasyon korunur.

## Kalıcı kayıt

Kalibrasyon kaydı, flash belleğin sonundaki iki ayrı 4 KiB sektöre dönüşümlü yazılır. Kayıt CRC32 ve sıra numarasıyla doğrulanır. Yeni kayıt doğrulanmadan önceki geçerli kayıt kaybedilmez; yazma sırasında güç kesilse bile açılışta son geçerli kayıt seçilir.

Servis ayarları için kullanılan `APPLY <kenar_payısı> <x_ters> <y_ters>` işlemi de tek flash işlemi olarak uygulanır. Flash yazımı başarısızsa RAM'deki değişiklik geri alınır ve önceki geçerli kayıt korunur. Uygulama gerekli tüm bağlı Gun Pico’lardan `profile:true` kayıt onayı gelmeden oturumu başarılı saymaz; 5 saniyelik onay zaman aşımında hata gösterip önceki kayıtla güvenli biçimde aktif duruma döner.

## Servis ayarları

Arayüzde yalnız şu temel seçenekler bulunur:

- **Kenar payı %:** Mekanik sınıra dayanmadan ekran kenarına erişim. Varsayılan `%2`.
- **X ters / Y ters:** Yalnız oyun içindeki yön gerçekten tersse kullanılır.

Merkez ayarı, kullanıcıya açık filtre ayrıntıları ve titreşim engelleme menüsü yoktur.

## Sıfırlama

**Kalibrasyonu Sıfırla**, mevcut köşe verilerini siler ve bu durumu doğrudan Pico'ya kaydeder. İşlemden sonra gerçek kullanım öncesi dört köşe kalibrasyonu yeniden yapılmalıdır.

## Hata mesajları

| Mesaj | Yapılacak işlem |
|---|---|
| Tetik basılı | Controller üzerindeki ilgili oyuncu tetiğini bırakıp yeniden başlatın. |
| Ölçüm kararsız | Silahı hedefte sabit tutup aynı hedefe tekrar ateş edin. |
| Hareket aralığı yetersiz | Potansiyometre, mekanik aktarım ve ADC bağlantısını kontrol edin. |
| Köşeler doğru sırada alınmadı | Kalibrasyonu yeniden başlatıp ekrandaki sırayı izleyin. |
| Flash kayıt başarısız | Pico güç/USB bağlantısını kontrol edin; önceki kayıt korunmuştur. |
| Kayıt onayı alınamadı | USB/seri bağlantısını kontrol edin; sistem önceki kayıtla aktif olur. |
| Zaman aşımı | Kalibrasyonu yeniden başlatın; önceki ayar korunmuştur. |
