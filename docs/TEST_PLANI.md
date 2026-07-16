# Kurulum ve Kabul Test Planı

Bu testler gerçek kabinde sürüm yayınlanmadan önce uygulanmalıdır. Röle/solenoid testleri önce yüksüz yapılır.

## A. Elektrik kapalı kontrol

- 3V3 ve GND arasında kısa devre yoktur.
- ADC pinleri 5 V hattına bağlı değildir.
- Röle/solenoid yükü GPIO'ya doğrudan bağlı değildir.
- Flyback diyot yönü doğrudur.
- P1 ve P2 röle kabloları karışmamıştır.
- Aktif-LOW röle modülü veya aktif-HIGH MOSFET sürücüsü seçimi belgelenmiştir.
- Gerçek yük güç konektörü ilk açılış için ayrılmıştır.

## B. Yüksüz ilk açılış

- Üç Pico Windows'ta görünür.
- Uygulama rolleri `Controller`, `P1 Gun`, `P2 Gun` olarak doğru tanır.
- Üç cihaz da canlı durum göndererek hazır görünür.
- Firmware sürümleri `0.4.0`, protokol alanları `3` olarak görünür.
- Watchdog reboot alanı sürekli `true` değildir.
- Röle çıkışları açılışta LED/multimetre ile güvenli boş seviyededir.
- Pico USB sök/tak sonrası polarite ayarı korunur ve çıkış yine güvenlidir.
- İki silahın hareket durumu her tam açılışta `AKTİF`tir.

## C. Giriş ve tek darbe testi

Her buton en az 50 kez denenir:

- Tek basış tek HID olayı oluşturur ve bırakma algılanır.
- Coin `1`, P1 Start `2`, P2 Start `5`, P1 tetik `3`, P2 tetik `6` olarak görünür.
- Coin ve bomba uzun tutulduğunda yalnız bir kısa darbe oluşur.
- P1/P2 Start tek başına basılıp bırakıldığında yalnız bir kısa Start darbesi oluşur.
- İki oyuncunun girişleri karışmaz.
- `KEY_PULSE_MS` yalnız `20..200 ms` aralığında kabul edilir.
- Tetik basılıyken Controller USB sök/tak yapılırsa yeniden bağlanmada hayalet tetik oluşmaz; bırakıp yeniden basınca çalışır.

## D. 10 saniyelik kalibrasyon çağrısı

### Fiziksel Start butonları

1. Uygulama Windows başlangıcında küçültülmüş çalışır durumda başlatılır.
2. P1 Start + P2 Start 9 saniye tutulup biri bırakılır.
   - Kalibrasyon açılmaz.
   - Silah hareketi aktif kalır.
   - Oyuna P1/P2 Start gönderilmez.
3. İki Start kesintisiz 10 saniye tutulur.
   - Komut yalnız bir kez çalışır.
   - Controller `motion_enabled=false` ve `maintenance=true` olur.
   - İki Gun Pico `motion_enabled=false` olur.
   - Recoil/röleler kapanır ve oyun klavye girişleri susturulur.
   - Uygulama öne gelir ve Kalibrasyon sekmesini seçer.
4. Tuşlar basılı kalmaya devam ederken ikinci istek oluşmaz.
5. Yeni istek için iki Start tamamen bırakılır.
6. Bu uzun basış ikinci kez yapıldığında hareket aç/kapat yapılmaz; yine kalibrasyon oturumu açılır.

### Klavyede 2 + 5

- Ana sayı satırı ve nümerik tuş takımında aynı 9/10 saniye testleri uygulanır.
- Tek `2` ve tek `5` basıp bırakma normal Start darbesi olarak oyuna ulaşır.
- Başarısız ortak basıştan sonra iki Start darbesi oyuna geri gönderilmez.
- Oyun yönetici yetkisiyle çalışıyorsa GT uygulaması aynı yetki düzeyinde denenir; yetki farkında `SendInput` hatası günlüğe açıkça yazılır.

### Kayıp olay kurtarma

- Test aracı `calibration_request` satırını kasıtlı olarak düşürür.
- Sonraki Controller durumundaki `maintenance=true` ve `motion_enabled=false` çifti uygulamanın Kalibrasyon sekmesini yine açmalıdır.

## E. Dört köşe kalibrasyonu

Her oyuncu için ayrı uygulanır:

1. Kalibrasyon ekranında merkez hedefi bulunmadığını doğrulayın.
2. Sıra `SOL ÜST → SAĞ ÜST → SAĞ ALT → SOL ALT` olmalıdır.
3. P1 kalibrasyonunda yalnız P1 tetiği, P2 kalibrasyonunda yalnız P2 tetiği köşe yakalamalıdır.
4. Her hedefte tetiğe bir kez basıp bırakın; oyun HID'i ve recoil darbesi oluşmamalıdır.
5. Bir hedefte silahı hareket ettirerek ateş edin; nokta ilerlememeli ve aynı hedef yeniden istenmelidir.
6. Köşeleri ters geometriyle alın; `wrong_order` oluşmalı ve önceki kalibrasyon korunmalıdır.
7. Hareket aralığını çok dar tutun; `range_too_small` oluşmalı ve önceki kalibrasyon korunmalıdır.
8. Başarılı dördüncü köşeden sonra:
   - Gun Pico önce kalibrasyonu flash'a kaydetmelidir.
   - Uygulama bağlı Gun profillerine atomik `APPLY` göndermelidir.
   - Gerekli tüm `saved=true, profile=true` onayları gelmeden hareket aktif olmamalıdır.
   - Onaylar tamamlanınca önce iki Gun hareketi `AKTİF`, sonra Controller bakım modu kapalı olmalıdır.
9. Uygulama durumu `Tamamlandı ve kaydedildi — iki silah AKTİF` göstermelidir.
10. Güç kesip yeniden açınca kalibrasyon korunmalıdır.

## F. Yalnız ayar değişikliği ve güvenli çıkış

- Kalibrasyon oturumu açılır, köşe kalibrasyonu başlatılmadan kenar payı/X ters/Y ters değiştirilir.
- **KAYDET VE SİLAHLARI AKTİF ET** düğmesine basılır.
- Bağlı Gun Pico'ların her biri atomik `APPLY` onayı vermelidir.
- Son onaydan önce bakım modu veya pasif hareket kapanmamalıdır.
- Son onaydan sonra iki silah hareketi aktif ve Controller bakım modu kapalı olmalıdır.
- USB'si çıkarılmış bir Gun için uygulama bağlı cihazları kaydetmeli; bağlı olmayan cihaz varmış gibi sahte başarı göstermemelidir.

## G. İptal, hata ve fail-safe

- Kalibrasyon sırasında **İPTAL / HAREKETİ AKTİF ET** seçilir; `CAL CANCEL` gönderilir, önceki kayıt korunur, iki silah aktif olur.
- Kalibrasyon sırasında Gun USB'si çıkarılır; işlem iptal edilir, önceki kayıt korunur, diğer cihazlar güvenli normale döner.
- Controller USB'si çıkarılır; aktif kalibrasyon iptal edilir ve uygulama hizmet oturumunu kapatır.
- `APPLY` flash hatası simüle edilir; hata gösterilir, önceki CRC-geçerli kayıt korunur ve hareket aktif yapılır.
- `APPLY` onayı 5 saniye gelmezse zaman aşımı gösterilir ve güvenli çıkış yapılır.
- Uygulama açık kalırken hizmet oturumunun 60 saniyede bir yenilendiği doğrulanır.
- Uygulama zorla kapatılır veya bilgisayar bağlantısı tamamen kaybolur; Controller ve Gun hareket kilitleri en geç 180 saniyede kendiliğinden aktif olmalıdır.
- Gun kalibrasyonu 120 saniye işlemsiz bırakılır; yarım ölçüm iptal edilmeli ve önceki ayar kullanılmalıdır.
- Uygulama yeniden açıldığında normal varsayılan hareket aktif olmalıdır.

## H. Flash güç kesintisi testi

Gerçek solenoid gücü kapalıyken:

- Bilinen eski ayar kaydedilir.
- Yeni kalibrasyon veya `APPLY` kaydı sırasında denetimli USB kesme/reset testi sınırlı sayıda tekrarlanır.
- Her açılışta ya eski ya yeni CRC-geçerli ayar yüklenir.
- Yarım/bozuk değer, rastgele polarite veya rastgele kalibrasyon görülmez.
- Şema 1 kayıtlı 0.2.x/0.3.x cihaz 0.4.0 firmware'e yükseltilir; kalibrasyon ve röle ayarları korunur.
- İlk şema 2 yazımı sırasında güç kesilse bile eski şema 1 kaydı okunabilir kalır.
- GitHub derlemesinde `check_firmware_size.py` üç `.bin` için geçer.

## I. Röle testi

Önce yüksüz/LED ile:

- Aktif-LOW/aktif-HIGH ayarı sürücüyle eşleşir.
- P1 tetik yalnız Röle 1'i, P2 tetik yalnız Röle 2'yi sürer.
- PULSE süresi ve cooldown ölçülür.
- USB çıkarıldığında, askıya almada, reboot/BOOTSEL öncesinde ve bakım modunda çıkışlar kapanır.
- 5 dakika hareketsizlik sonrası röle kapanır; ilk yeni oyuncu girişi sistemi yeniden kurar.
- FOLLOW modunda güvenlik kesmesi ayarlanan sürede çalışır.

Gerçek yükle üreticinin görev çevrimi sınırını aşmadan en az 1000 tetik çevrimi yapılır; MOSFET/röle, diyot, kablo ve güç kaynağı sıcaklığı kontrol edilir.

## J. Oyun ve 1 kredi testi

- TeknoParrot doğru profil ile açılır.
- RawInput'ta P1/P2 ayrı GT Gun aygıtlarını kullanır.
- Tek coin basışı tam bir kredi ekler; basılı tutma ilave kredi eklemez.
- P1 ve P2 Start doğru oyuncuyu başlatır.
- Kalibrasyon uzun basışı sırasında oyuna Start/coin/tetik/bomba sızmaz.
- `1 coin = 1 credit` ayarı 10 soğuk açılışta korunur.
- Servis makrosu kullanılıyorsa yükleme süresi varyasyonlarında yanlış menüye girmez.
- Üç Pico'dan biri canlı veri göndermiyorsa, bu seçenek açıksa otomatik oyun başlatma gerçekleşmez.

## K. Bağlantı ve uzun süre testi

En az 8 saat:

- Uygulama açık ve başlangıçta küçültülmüş durumdadır.
- Üç Pico bağlıdır; oyun birkaç kez açılıp kapanır.
- USB hub yeniden bağlanır; roller doğru geri gelir.
- Seri günlüklerinde sürekli reconnect/watchdog döngüsü yoktur.
- CDC veri akışı 10 saniyeden uzun kesildiğinde port otomatik yenilenir.
- Bölünmüş JSON satırları doğru birleşir; bozuk/aşırı uzun satırdan sonraki geçerli satır kaybolmaz.
- Giriş gecikmesi veya mouse takılması yoktur.
- Açık kalibrasyon hizmeti boyunca 60 saniyelik keepalive nedeniyle yanlışlıkla hareket aktif olmaz.
- Log ve UI kuyrukları büyüyerek bellek tüketmez.

## L. Sürüm kabul kriteri

- `python scripts/set_version.py --check` geçer.
- `python -m compileall -q desktop/gt_super_controller desktop/tests` geçer.
- Tüm Python testleri geçer.
- Host flash testi ve sıkı C sözdizimi kontrolleri geçer.
- GitHub firmware ve Windows işleri başarılıdır.
- Gerçek ARM derlemesinde üç `.bin` boyut denetiminden geçer.
- SHA-256 dosyaları üretilir ve indirilen dosyalar doğrulanır.
- Üç UF2 aynı sürüm ve protokol numarasını bildirir.
- Yukarıdaki donanım testlerinde kritik hata yoktur.
