# USB CDC Seri Protokolü — Sürüm 3

Her Pico bilgisayara hem HID hem USB CDC/COM aygıtı olarak görünür. Masaüstü uygulaması cihazları COM numarasına göre değil `role` ve `player` alanlarına göre tanır.

- Bilgisayardan Pico'ya komutlar: ASCII, bir komut bir satır, satır sonu `\n`.
- Pico'dan bilgisayara yanıt/olaylar: tek satırlık JSON, satır sonu `\r\n`.
- Komutlar büyük/küçük harfe duyarsızdır.
- Yarım JSON geçerli sayılmaz. Firmware TX kuyruğuna bütünüyle sığmayan satırı tamamen atar; masaüstü bir sonraki `\n` sınırından devam eder.

## 1. Ortak komutlar

Her üç Pico şu komutları kabul eder:

```text
PING
INFO
STATUS
GET CONFIG
SAVE
DEFAULTS
BOOTSEL
REBOOT
```

`BOOTSEL` ve `REBOOT` öncesinde Controller röleleri kapatır. `DEFAULTS` kalıcı değildir; kalıcı olması için ayrıca `SAVE` gerekir. Gun kalibrasyonu ve `APPLY` işlemi kendi kaydını otomatik yapar.

## 2. Controller komutları

```text
MAINTENANCE 0|1
MOTION 0|1
SET RELAY_MODE OFF|PULSE|FOLLOW
SET RELAY_ACTIVE_LOW 0|1
SET PULSE_MS 10..500
SET COOLDOWN_MS 20..2000
SET FOLLOW_MAX_MS 20..1000
SET KEY_PULSE_MS 20..200
SET INACTIVITY_S 0..3600
SET TRIGGER_HID 0|1
SET KEY <COIN|P1_START|P1_TRIGGER|P1_BOMB|P2_START|P2_TRIGGER|P2_BOMB> <0..9|A..Z|NONE>
```

`MAINTENANCE 1` tüm röleleri kapatır ve oyun HID çıkışlarını susturur. Fiziksel tetik değişimleri seri `input` olayı olarak gönderilmeye devam eder; masaüstü bunları yalnız aktif kalibrasyon oyuncusunun köşe yakalaması için kullanır. Bakım komutu yenilenmezse 180 saniye sonra firmware kendiliğinden normal moda döner.

`MOTION 0` Controller'ın oturum durumunu pasif yapar. Bu komut Gun Pico'lara masaüstü uygulaması tarafından ayrıca gönderilir. Durum kalıcı flash'a yazılmaz ve 180 saniye yenilenmezse tekrar aktif olur.

## 3. İki Start ile kalibrasyon isteği

P1 Start ve P2 Start aynı anda tutulduğunda normal Start darbeleri bastırılır. Kesintisiz `10000 ms` sonunda Controller:

1. `motion_enabled=false` yapar,
2. aşağıdaki kalibrasyon isteğini gönderir,
3. bakım moduna girerek oyun HID ve recoil çıkışlarını kapatır.

```json
{"event":"calibration_request","role":"controller","source":"start_buttons","hold_ms":10000,"change_id":1}
```

Basış başladığında ve erken bırakıldığında şu olaylar görülebilir:

```json
{"event":"calibration_hold_started","role":"controller","hold_ms":10000}
{"event":"calibration_hold_cancelled","role":"controller"}
```

Bu komut **hareket aç/kapat geçişi değildir**. Her başarılı 10 saniyelik basış güvenli bir kalibrasyon oturumu ister. Yeni deneme için iki Start'ın da tamamen bırakılması gerekir.

Tek seferlik `calibration_request` satırı kaybolursa masaüstü, Controller'ın periyodik durumundaki `maintenance=true` ve `motion_enabled=false` çiftini kurtarma sinyali olarak kullanır.

## 4. Controller olayları ve durum

Giriş olayı:

```json
{"event":"input","role":"controller","name":"P1_TRIGGER","active":true}
```

Hareket oturum durumu:

```json
{"event":"motion_state","role":"controller","enabled":false,"source":"calibration_start_buttons","change_id":1}
```

Bakım olayı:

```json
{"event":"maintenance","enabled":true,"timeout_ms":180000}
```

Controller yaklaşık 500 ms aralıkla şu alanları içeren durum gönderir:

```json
{"type":"status","role":"controller","coin":false,"p1_start":false,"p1_trigger":false,"p1_bomb":false,"p2_start":false,"p2_trigger":false,"p2_bomb":false,"p1_relay":false,"p2_relay":false,"p1_armed":true,"p2_armed":true,"maintenance":true,"motion_enabled":false,"motion_change_id":1,"uptime_ms":12345}
```

## 5. Gun komutları

```text
STREAM 0|1
MOTION 0|1
SET FILTER 0..95
SET THRESHOLD 0..2000
SET OVERSCAN 0..20
SET INVERT_X 0|1
SET INVERT_Y 0|1
APPLY <overscan 0..20> <invert_x 0|1> <invert_y 0|1>
CAL START
CAL CAPTURE
CAL CANCEL
CAL RESET
```

`MOTION 0` yalnız X/Y HID mouse raporunu durdurur. Ham ADC, seri durum ve kalibrasyon çalışmaya devam eder. Durum kalıcı değildir; komut 60 saniyede bir yenilenen servis oturumu dışında 180 saniye sonra fail-safe ile aktif olur.

`APPLY` üç servis ayarını önce tamamen doğrular, RAM'e birlikte uygular ve tek atomik flash kaydı yapar. Başarılı kayıt onayı:

```json
{"ok":true,"role":"gun","player":1,"saved":true,"profile":true,"sequence":8}
```

Masaüstü uygulaması kalibrasyon/ayar oturumunu yalnız gerekli tüm bağlı Gun Pico'lardan bu `profile:true` kayıt onayını aldıktan sonra kapatır.

## 6. Dört köşe kalibrasyonu

Kalibrasyon sırası sabittir:

```text
TL → TR → BR → BL
SOL ÜST → SAĞ ÜST → SAĞ ALT → SOL ALT
```

Merkez noktası yoktur. Her Controller tetik basışında masaüstü yalnız seçili oyuncunun Gun Pico'suna `CAL CAPTURE` gönderir. Her noktada X ve Y aynı kısa zaman aralığında 25 kez örneklenir; uç değerler ayıklanır. Silah hareket ediyorsa nokta ilerlemez ve `cal_retry` gönderilir.

Örnek olaylar:

```json
{"event":"cal_ready","role":"gun","player":1,"point":"TL"}
{"event":"cal_point","role":"gun","player":1,"point":"TL","raw_x":312,"raw_y":3710}
{"event":"cal_retry","role":"gun","player":1,"point":"TR","reason":"unstable"}
{"event":"cal_complete","role":"gun","player":1,"saved":true,"quality":94,"x_span":3440,"y_span":3350,"x_left":300,"x_right":3740,"y_top":3680,"y_bottom":330}
{"event":"cal_error","role":"gun","player":1,"error":"timeout"}
{"event":"cal_cancelled","role":"gun","player":1}
{"event":"cal_reset","role":"gun","player":1}
```

Dördüncü köşe geçerliyse Gun firmware'i köşe verisini hemen çift sektörlü CRC kaydına yazar ve ancak ardından `cal_complete` gönderir. Geometri tersse `wrong_order`, mekanik aralık yetersizse `range_too_small`, flash kaydı başarısızsa `flash_save_failed` gönderilir. Başarısızlıkta önceki geçerli kalibrasyon RAM'e geri alınır.

Gun kalibrasyon oturumu 120 saniye işlem yapılmazsa iptal olur. USB bağlantısı kesilirse yarım işlem bırakılır, önceki ayar geri yüklenir ve hareket aktif yapılır.

## 7. Kimlik yanıtları

Controller:

```json
{"type":"info","role":"controller","name":"GT SUPER CONTROLLER","version":"0.4.0","protocol":3,"watchdog_reboot":false}
```

Gun:

```json
{"type":"info","role":"gun","player":1,"name":"GT GUN PLAYER 1","version":"0.4.0","protocol":3,"watchdog_reboot":false}
```

## 8. Hata yanıtları

Controller genel hata örneği:

```json
{"ok":false,"error":"invalid_motion"}
```

Gun hata yanıtı rol ve oyuncuyu da taşır:

```json
{"ok":false,"role":"gun","player":1,"error":"flash_save_failed"}
```

`SET` komutları RAM'de uygulanır ve normalde `SAVE` gerekir. Kalibrasyonun köşe kaydı, `CAL RESET` ve `APPLY` kendi atomik flash kaydını yapar.

## 9. Akış, yeniden bağlanma ve fail-safe

- Gun `STREAM 1` durumunda yaklaşık 250 ms aralıkla durum gönderir.
- Controller yaklaşık 500 ms aralıkla durum gönderir.
- Masaüstü istemcisi USB paketlerine bölünmüş satırları `\n` gelene kadar birleştirir.
- Geçerli protokol mesajı 10 saniye kesilirse port kapatılıp yeniden taranır.
- Açık kalibrasyon hizmeti masaüstü tarafından 60 saniyede bir `MAINTENANCE 1` ve `MOTION 0` ile yenilenir.
- Masaüstü kapanır veya USB yolu kaybolursa Controller ve Gun oturum kilitleri en geç 180 saniyede çözülür; normal varsayılan hareket durumu aktiftir.

## 10. Flash şeması

Firmware 0.4.0, Controller ve Gun ayar şeması `2`yi kullanmaya devam eder. Bu protokol sürümüyle flash şeması aynı kavram değildir.

- Şema `1` kayıtları açılışta okunabilir.
- Controller röle süreleri, polarite ve tuş eşlemeleri korunur; Controller tetik HID'i yeni kablolama için açık yapılır.
- Gun dört köşe kalibrasyonu, ters eksen ve kenar payını korur; eski yerel tetik alanı temizlenir.
- İlk şema `2` yazımı karşı sektöre yapılır; yazma sırasında güç kesilirse eski CRC-geçerli kayıt korunur.
