# Değişiklik Günlüğü

## 0.4.0 — Tek Komutla Güvenli Kalibrasyon Oturumu

- P1 Start + P2 Start uzun basışı artık hareket aç/kapat anahtarı değildir.
- İki fiziksel Start butonu kesintisiz 10 saniye tutulduğunda Controller iki silahın X/Y hareketini pasif yapar, bakım moduna girer ve Windows uygulamasına `calibration_request` gönderir.
- Windows'taki `2 + 5` uzun basışı da aynı kalibrasyon oturumunu açar. Tek `2` ve tek `5` kullanımı normal Start darbesi olarak korunur.
- Kalibrasyon uygulaması Windows başlangıcında küçültülmüş çalışır; istek geldiğinde öne gelir ve doğrudan Kalibrasyon sekmesini açar.
- Bakım modunda coin, Start, bomba, tetik HID çıkışları ve recoil/röleler oyuna iletilmez; Controller tetik olayları yalnız köşe yakalama için masaüstüne gönderilir.
- Kalibrasyon yine yalnız **Sol Üst → Sağ Üst → Sağ Alt → Sol Alt** sırasındadır; merkez adımı yoktur.
- Dördüncü köşe doğrulandığında Gun Pico kalibrasyonunu çift sektörlü CRC kaydına atomik olarak yazar.
- Ardından masaüstü uygulaması bağlı iki Gun Pico'nun kenar payı ve eksen yönü profilini tek `APPLY` komutuyla kaydeder; gerçek flash onayları gelmeden oturum kapanmaz.
- Tüm gerekli kayıt onayları alındığında önce iki silahın hareketi aktif edilir, sonra Controller bakım modu kapatılır.
- Kalibrasyon yapılmadan yalnız ayarlar değiştirildiyse **KAYDET VE SİLAHLARI AKTİF ET** düğmesi aynı onaylı çıkış işlemini uygular.
- İptal, USB kopması, kayıt hatası veya zaman aşımında önceki geçerli kalibrasyon korunur ve iki silah yeniden aktif edilir.
- Uygulama veya seri olay kaybolursa Controller'ın periyodik `maintenance=true` + `motion_enabled=false` durumu kalibrasyon penceresini kurtarma sinyali olarak kullanılır.
- Uygulama açık bir servis oturumunu 60 saniyede bir yeniler. Controller ve Gun firmware'leri bağlantı tamamen kaybolursa en geç 180 saniyede hareketi tekrar aktif eden fail-safe uygular.
- Seri protokol sürümü `3` oldu; `calibration_request` oturum semantiği ve atomik Gun `APPLY` kayıt onayı belgelendi.
- Otomatik Python test sayısı 41'e çıkarıldı.

## 0.3.0 — Controller Tetikleri ve 10 Saniyelik Hareket Kilidi

- P1 ve P2 tetik girişleri tamamen ortak Controller Pico'ya taşındı: P1 `GP4`, P2 `GP7`.
- Gun Pico'larından yerel tetik ve `GP19` hareket anahtarı kaldırıldı; Gun Pico'ları yalnız X/Y konumu, mutlak HID ve kalibrasyonu yönetir.
- İki fiziksel Start butonunu kesintisiz 10 saniye tutarak iki silahın hareketini birlikte aktif/pasif yapan ilk durum makinesi eklendi.
- Windows genel klavye kancasıyla ana sayı satırı veya nümerik tuş takımındaki `2 + 5` tuşlarını 10 saniye tutma desteği eklendi.
- Ortak basış 10 saniye dolmadan bozulursa iki Start komutu da bastırılır; kredi harcanmaz ve oyuncu yanlışlıkla başlatılmaz.
- Komut yalnız bir kez çalışır; yeni işlem için iki tuşun da tamamen bırakılması gerekir.
- Tek `2`, tek `5` ve tek fiziksel Start kullanımı normal tek Start darbesi olarak korunur.
- Hareket durumu kalıcı değildir; Controller, Gun Pico'ları ve Windows uygulaması her tam başlangıçta `AKTİF` durumuyla açılır.
- Kalibrasyon köşe yakalama tetiği Controller olayından ilgili Gun Pico'ya `CAL CAPTURE` olarak yönlendirilir.
- Protokol sürümü `2` oldu ve `MOTION 0|1` komutu ile `motion_state` olayları eklendi.

## 0.2.0 — PRO Kalibrasyon

- Merkez hedefi tamamen kaldırıldı; kalibrasyon yalnızca **Sol Üst → Sağ Üst → Sağ Alt → Sol Alt** sırasıyla yapılır.
- Tam ekran, operatör odaklı kalibrasyon sihirbazı eklendi.
- Teknik titreşim/filtre ayrıntıları ana kalibrasyon ekranından kaldırıldı.
- Her hedefte X/Y birlikte çoklu örneklenir; uç değerler ayıklanır ve kararsız ölçüm aynı hedefte otomatik tekrarlanır.
- Yanlış köşe geometrisi ve yetersiz mekanik hareket aralığı kabul edilmez.
- Yeni kalibrasyon doğrulanıp flash'a yazılana kadar önceki geçerli ayar korunur.
- Kalibrasyon sırasında Controller bakım modu ile röle/recoil ve oyun klavye çıkışları kapatılır.
- Masaüstü bağlantısı kesilirse Controller bakım modu 180 saniyede, Gun kalibrasyon oturumu 120 saniyede güvenli biçimde çözülür.
- USB kesilmesinde yarım kalibrasyon iptal edilir ve önceki ayar geri yüklenir.
- PyInstaller giriş noktası paketlenmiş çalıştırmaya uygun bağımsız launcher ile düzeltildi.
- GitHub Actions, üç UF2 ve Windows EXE üretip sürüm etiketinde Release'e ekleyecek şekilde sabitlendi.
