# Doğrulama ve Derleme Durumu

## 0.4.0 için yerel kontroller

- `VERSION`, Python paket sürümü ve `pyproject.toml` sürümü `0.4.0` olarak eşleşir.
- Masaüstü Python kaynakları ve testleri `compileall` kontrolünden geçmiştir.
- **41 pytest testi** geçmiştir.
- Fiziksel Start mimarisi kaynak bütünlük testinde doğrulanır: 10 saniye sonunda hareket pasif, `calibration_request`, bakım modu; tersine hareket geçişi kodu bulunmaz.
- Windows `2 + 5` durum makinesinde tek tuş yeniden gönderimi, 10 saniyede tek istek, erken iptal ve tam bırakmadan yeniden kurulmama senaryoları test edilmiştir.
- Kayıp tek seferlik kalibrasyon olayının periyodik `maintenance=true` + `motion_enabled=false` durumuyla kurtarılması test edilmiştir.
- Gun ayarlarının tek atomik `APPLY` komutuyla oluşturulması, iki Gun kayıt onayının tamamının beklenmesi ve iptal edilen oturumun gecikmiş kayıtta yeniden açılmaması test edilmiştir.
- Controller, P1 Gun ve P2 Gun C kaynakları geçici Pico/TinyUSB API başlıklarıyla host GCC üzerinde `-Wall -Wextra -Werror -Wformat=2 -Wshadow -Wconversion` kontrolünden geçmiştir.
- Çift sektörlü flash şema geçişi sahte 8 KiB flash kullanan çalıştırılabilir host C testiyle doğrulanmıştır.
- Masaüstü arayüzü sanal X ekranında açılmış; kalibrasyon oturumunun Kalibrasyon sekmesini seçtiği, `MAINTENANCE 1`/`MOTION 0` gönderdiği ve kapanışta `MOTION 1`/`MAINTENANCE 0` gönderdiği smoke test ile görülmüştür.
- Seri protokol kimliği `3`, firmware/uygulama sürümü `0.4.0`dır. Flash ayar şeması geriye uyumluluk için `2` olarak kalır.

## Bu ortamda yapılmayanlar

Bu Linux çalışma ortamında Raspberry Pi Pico SDK ve Arm GNU `arm-none-eabi` araç zinciriyle gerçek RP2040 link işlemi yapılmamıştır. Gerçek `.uf2` dosyaları ve gerçek Windows PyInstaller EXE'si bu yerel doğrulamanın parçası değildir. Windows düşük seviye klavye kancasının UAC/yetki davranışı da gerçek Windows kabininde denenmelidir.

Sürüm kabulü için GitHub Actions'ta şunlar başarılı olmalıdır:

1. Pico SDK ile `gt_controller.uf2`, `gt_gun_p1.uf2`, `gt_gun_p2.uf2` gerçek ARM derlemesi ve boyut kontrolü.
2. Windows runner üzerinde testlerin geçmesi ve `GT_SUPER_CONTROLLER_0.4.0.exe` üretimi.
3. UF2 ve EXE SHA-256 dosyalarının üretilmesi.

## Fiziksel kabul testi

Gerçek kabinde en az şu kontroller uygulanmalıdır:

1. P1 tetik `GP4`, P2 tetik `GP7` ve ilgili recoil çıkışları.
2. Normal açılışta iki Gun hareketinin aktif olması.
3. İki Start'ın 9 saniyede iptal, 10 saniyede yalnız bir kalibrasyon isteği üretmesi; Start/kredi sızıntısı olmaması.
4. Uygulamanın küçültülmüş durumdan Kalibrasyon sekmesiyle öne gelmesi.
5. Oturum boyunca iki Gun hareketinin, oyun HID girişlerinin ve recoil çıkışlarının kapalı kalması.
6. Dört köşe kaydı sonrası gerçek flash onaylarının alınması ve iki Gun hareketinin otomatik aktif olması.
7. `KAYDET VE SİLAHLARI AKTİF ET` düğmesinin ayarları kaydedip aynı güvenli çıkışı yapması.
8. İptal, USB kopması, uygulama kapanması ve 180 saniyelik fail-safe davranışı.
9. Güç kesip yeniden açınca kalibrasyonun korunması.
10. TeknoParrot RawInput, ayrı P1/P2 HID aygıtları ve Paradise Lost `1 coin = 1 credit` ayarı.

Ayrıntılı sıra için [TEST_PLANI.md](TEST_PLANI.md) kullanılmalıdır.
