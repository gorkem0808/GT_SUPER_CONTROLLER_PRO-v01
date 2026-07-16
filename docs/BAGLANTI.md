# Bağlantı ve Elektrik Güvenliği

## 1. Güç kuralları

1. Pico GPIO ve ADC pinlerine **5 V uygulanmaz**.
2. Potansiyometreler yalnızca Pico `3V3(OUT)` ve `GND` arasında beslenir.
3. Solenoid, motor, lamba veya röle bobini GPIO'dan doğrudan sürülmez.
4. Yük beslemesi ayrı olmalı; sürücü katı gerektiriyorsa Pico GND ile güç kaynağı GND ortaklanmalıdır.
5. Bobinli DC yükte ters EMK için flyback diyodu zorunludur. AC yükte uygun snubber/SSR ve yetkili elektrikçi denetimi gerekir.
6. Şebeke gerilimi tarafı düşük voltaj devresinden fiziksel olarak ayrılmalıdır.
7. İlk ayar ve polarite testinde gerçek yükün güç kaynağı **kapalı ve fiziksel olarak ayrılmış** olmalıdır.

## 2. Ortak kontrol Pico

Tüm butonlar aktif LOW'dur. Her butonun bir ucu ilgili GPIO'ya, diğer ucu GND'ye bağlanır. Harici pull-up gerekmez.

| GPIO | Bağlantı | Açıklama |
|---|---|---|
| GP2 | Coin butonu → GND | HID `1` |
| GP3 | P1 Start → GND | HID `2` |
| GP4 | P1 tetik → GND | HID `3` + Röle 1 |
| GP5 | P1 bomba → GND | HID `4` |
| GP6 | P2 Start → GND | HID `5` |
| GP7 | P2 tetik → GND | HID `6` + Röle 2 |
| GP8 | P2 bomba → GND | HID `7` |
| GP27 | Sürücü 1 lojik girişi | Röle/solenoid P1 |
| GP26 | Sürücü 2 lojik girişi | Röle/solenoid P2 |

Coin ve bomba tuşları basılı tutulduğunda tekrar üretmez. Start tuşları normal kullanımda bırakıldığında tek klavye darbesi oluşturur. İki Start aynı anda tutulursa oyun Start komutları kesilir; kesintisiz 10 saniye sonunda güvenli kalibrasyon oturumu başlatılır.

### Kalibrasyon programını açma komutu

```text
P1 Start (GP3) + P2 Start (GP6)
              10 saniye
                   ↓
İki silah hareketi PASİF
Controller bakım modu AÇIK
Windows Kalibrasyon sekmesi ÖNDE
```

Bu komut aktif/pasif geçişi değildir. Süre dolmadan herhangi bir Start bırakılırsa işlem iptal edilir ve oyuna Start gönderilmez. Yeni deneme için iki buton da tamamen bırakılmalıdır. Başarılı kayıt veya iptal sonunda iki silah hareketi tekrar aktif yapılır. Geçici pasif durum kalıcı belleğe yazılmaz; her açılışta aktiftir.

## 3. Röle çıkış polaritesi — bağlamadan önce okuyun

Firmware ilk kurulumda **aktif LOW** röle girişi varsayar:

- röle açık komutu: GPIO LOW,
- röle kapalı komutu: GPIO HIGH.

Bu ayar, birçok optokuplörlü aktif-LOW röle modülüne uygundur. Aşağıdaki düşük taraf N-MOSFET devresi ise **aktif HIGH** çalışır; gate HIGH olduğunda yük açılır. Bu nedenle N-MOSFET devresi kullanılacaksa gerçek yük bağlanmadan önce Windows uygulamasında `Röle aktif LOW` seçimi kapatılmalı, ayar `Kaydet` ile Pico'ya yazılmalı ve çıkış LED/multimetreyle doğrulanmalıdır.

> Yanlış polarite gerçek yükü açılışta sürekli enerjili bırakabilir. İlk enerji verme her zaman yüksüz yapılmalıdır. `Varsayılanlar` komutu polariteyi tekrar aktif LOW'a çevirir; gerçek yük bağlıyken kullanılmamalıdır.

### Aktif-HIGH düşük taraf N-MOSFET örneği

```text
Pico GP27 ── 100 Ω ── Gate (logic-level N-MOSFET)
                       │
                    100 kΩ
                       │
Pico GND ──────────────┴──────── Source

Harici +V ── Bobin/Yük ── Drain
              │      │
              └─|<|──┘  Flyback diyodu

Harici GND ───────────── Pico GND
```

Bu devrede uygulama ayarı: `Röle aktif LOW = kapalı`.

Hazır röle modülü kullanılıyorsa girişin 3.3 V lojikle gerçekten tetiklendiği, aktif seviyesinin LOW/HIGH olduğu ve açılışta güvenli durumda kaldığı üretici şeması ile doğrulanmalıdır. `JD-VCC` optik izolasyonlu kartlarda jumper ve toprak düzeni kart şemasına göre kurulmalıdır.

## 4. P1 ve P2 silah Pico bağlantısı

Her iki Pico için aynı bağlantı kullanılır; yalnızca yüklenen UF2 farklıdır.

### X potansiyometresi

```text
Pico 3V3(OUT) ───── Pot dış uç
Pico GP26/ADC0 ──── Pot orta uç (wiper)
Pico GND ────────── Pot diğer dış uç
```

### Y potansiyometresi

```text
Pico 3V3(OUT) ───── Pot dış uç
Pico GP27/ADC1 ──── Pot orta uç (wiper)
Pico GND ────────── Pot diğer dış uç
```

Öneri: 10 kΩ lineer potansiyometre. Kablolar uzunsa her ADC girişine Pico tarafında `1 kΩ` seri direnç ve `100 nF` GND'ye filtre kondansatörü eklenebilir. Kondansatör aşırı büyütülürse nişan gecikmesi oluşur.

Silah Pico üzerinde tetik veya hareket aç/kapat anahtarı bulunmaz. GP2 ve GP19 boş bırakılır. Her silahın tetik microswitch'i doğrudan ortak Controller Pico'ya gider:

```text
P1 tetik: Controller GP4 ── switch ── Controller GND
P2 tetik: Controller GP7 ── switch ── Controller GND
```

Bu bağlantıda tek kutuplu standart microswitch yeterlidir. Tetik oyuna klavye HID komutu gönderir ve aynı anda ilgili recoil/röle çıkışını tetikler. Kalibrasyonda ise Controller bakım modu HID ve röleyi susturur; tetik olayı yalnız kalibrasyon ölçümü için Windows uygulamasına iletilir.

## 5. Klavyeden kalibrasyon programını açma

Windows uygulaması başlangıçta küçültülmüş çalışırken ana sayı satırındaki veya nümerik tuş takımındaki `2` ve `5` tuşları 10 saniye tutulabilir. Uygulama bu tuşları genel Windows kancasıyla izler; normal tek tuş kullanımlarını kısa Start darbesi olarak yeniden gönderir, ortak basışta Start komutlarını oyuna iletmez. On saniye sonunda iki Gun hareketini pasif yapar, Controller bakım modunu açar ve Kalibrasyon sekmesini öne getirir. Kayıt tamamlanınca veya işlem iptal edilince iki silah yeniden aktif edilir.

## 6. USB bağlantısı

- Üç Pico mümkünse kaliteli, harici beslemeli bir USB 2.0 hub'a bağlanır.
- Uzun veya yalnızca şarj amaçlı USB kablo kullanılmaz.
- Windows Aygıt Yöneticisi'nde her Pico hem HID hem CDC/COM bileşeni olarak görünür.
- Ürün kimlikleri:
  - Controller VID/PID: `CAFE:4010`
  - P1 Gun VID/PID: `CAFE:4011`
  - P2 Gun VID/PID: `CAFE:4012`

`0xCAFE` geliştirme amaçlı kullanılan bir VID'dir; ticari seri üretimde atanmış bir USB VID/PID kullanılmalıdır.

## 7. İlk enerji verme kontrolü

1. Solenoid/röle/yük güç kaynağını kapatın ve mümkünse konektörünü ayırın.
2. Yalnızca Pico USB bağlantılarını takın.
3. Uygulamada üç cihazın doğru rol ve oyuncu numarasıyla ve canlı veriyle göründüğünü doğrulayın.
4. Buton ve ham ADC değerlerini test edin.
5. Röle çıkışını önce LED veya multimetreyle ölçün; açılışta ve boşta güvenli seviyede olduğunu doğrulayın.
6. Gerekirse `Röle aktif LOW` ayarını değiştirin, kaydedin, Pico'yu USB'den çıkarıp yeniden takın ve ölçümü tekrarlayın.
7. P1 ve P2 için `PULSE` darbe süresini yüksüz ölçün.
8. Polarite ve zamanlama doğrulandıktan sonra sürücü katını bağlayın.
9. En son gerçek yük güç kaynağını açın.
