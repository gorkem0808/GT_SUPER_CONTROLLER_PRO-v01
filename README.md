# GT SUPER CONTROLLER

Raspberry Pi Pico tabanlı, iki oyunculu arcade/lightgun kabini için tek depoda çalışan sistem:

- `gt_controller.uf2`: coin, start, bomba, tetik izleme ve iki bağımsız röle çıkışı.
- `gt_gun_p1.uf2`: Oyuncu 1 potansiyometreli mutlak HID mouse ve kalıcı kalibrasyon.
- `gt_gun_p2.uf2`: Oyuncu 2 potansiyometreli mutlak HID mouse ve kalıcı kalibrasyon.
- `GT_SUPER_CONTROLLER.exe`: Windows cihaz izleme, kalibrasyon, röle ayarı, TeknoParrot başlatma ve isteğe bağlı servis makrosu.
- GitHub Actions: her push veya elle çalıştırmada üç UF2 ve Windows EXE üretir; `vX.Y.Z` etiketi gönderildiğinde GitHub Release oluşturur. Pico SDK etiketi/commit kimliği, Action sürümleri ve Windows derleme bağımlılıkları sabitlenmiştir.

> Bu depo Raspberry Pi **Pico/RP2040** içindir. Pico W veya Pico 2 için pinler aynı görünse bile, `PICO_BOARD` ve elektrik bağlantıları doğrulanmadan firmware yüklenmemelidir.

## Hızlı kurulum sırası

1. [Bağlantı şemasını](docs/BAGLANTI.md) uygulayın. Röle/solenoid yükünü Pico GPIO'suna doğrudan bağlamayın.
2. GitHub Actions çıktısından veya yerel derlemeden:
   - ortak kontrol Pico'ya `gt_controller.uf2`,
   - P1 silah Pico'ya `gt_gun_p1.uf2`,
   - P2 silah Pico'ya `gt_gun_p2.uf2` yükleyin.
3. Windows'ta `GT_SUPER_CONTROLLER.exe` uygulamasını açın.
4. Uygulama Windows başlangıcında çalışır durumda olsun. Kalibrasyon ekranını açmak için P1 Start + P2 Start'ı 10 saniye tutun; ardından kalibre edilecek oyuncuyu seçip **SOL ÜST → SAĞ ÜST → SAĞ ALT → SOL ALT** hedeflerine ateş edin. Merkez adımı yoktur.
5. TeknoParrot'ta RawInput/lightgun girişlerini açın; P1 ve P2 için ayrı `GT GUN PLAYER` aygıtlarını seçin.
6. Coin/start/bomba tuşlarını aşağıdaki varsayılanlara eşleyin.
7. Paradise Lost test/service menüsünde **1 coin = 1 credit** ayarını bir kez kaydedin. Kabinin NVRAM/oyun yapılandırması bu ayarı korumuyorsa, uygulamadaki isteğe bağlı servis makrosunu yalnızca gerçek tuş sırası doğrulandıktan sonra etkinleştirin.

## Varsayılan pinler ve işlevler

### Ortak kontrol Pico

| Pico pini | İşlev | Varsayılan HID |
|---|---|---|
| GP2 | Coin | `1` |
| GP3 | P1 Start | `2` |
| GP4 | P1 tetik / Röle 1 | `3` |
| GP5 | P1 Bomba | `4` |
| GP6 | P2 Start | `5` |
| GP7 | P2 tetik / Röle 2 | `6` |
| GP8 | P2 Bomba | `7` |
| GP27 | Röle 1 kontrol çıkışı | Aktif LOW |
| GP26 | Röle 2 kontrol çıkışı | Aktif LOW |

Buton girişleri dahili pull-up kullanır; basıldığında GND'ye çekilir. Coin ve bomba her basışta tek HID darbesi üretir. Start tuşu normal kullanımda bırakıldığında tek darbe gönderir. Start 1 ile Start 2 birlikte tutulursa normal Start komutları bastırılır; kesintisiz 10 saniye sonunda güvenli kalibrasyon oturumu istenir.

### Her silah Pico

| Pico pini | İşlev |
|---|---|
| GP26 / ADC0 | X potansiyometre orta ucu |
| GP27 / ADC1 | Y potansiyometre orta ucu |
| 3V3(OUT) | Potansiyometre beslemesi |
| GND | Ortak toprak |

Silah Pico'ları yalnız X/Y konumu ve kalibrasyon verisini yönetir. P1 ve P2 tetik butonları sırasıyla ortak Controller üzerindeki GP4 ve GP7'ye bağlanır. GP2 ve GP19 silah Pico'larında kullanılmaz.

## Kalibrasyon programını açma

İki Start butonu artık bir aç/kapat anahtarı değildir. Yalnız kalibrasyon ve servis oturumu başlatır:

- **Start 1 + Start 2:** İki fiziksel Start butonunu kesintisiz 10 saniye basılı tutun.
- **Klavyede 2 + 5:** Aynı işlemi ana sayı satırından veya nümerik tuş takımından yapabilirsiniz.
- 10 saniye tamamlandığında Controller bakım moduna girer, recoil ve oyun klavye çıkışlarını kapatır, iki Gun Pico'nun X/Y hareketi pasif yapılır ve küçültülmüş uygulama Kalibrasyon sekmesiyle öne gelir.
- Süre dolmadan tuşlardan biri bırakılırsa istek iptal edilir; P1/P2 Start oyuna gönderilmez ve kredi yanlışlıkla harcanmaz.
- Oturum sırasında oyuncu seçilir, dört köşe kalibrasyonu yapılır veya temel servis ayarları değiştirilir.
- Başarılı kalibrasyon firmware tarafından atomik olarak kaydedilir. Uygulama bağlı Gun Pico’ların kenar payı ve eksen yönlerini tek `APPLY` işlemiyle kaydeder; gerekli tüm flash onaylarını aldıktan sonra önce iki silahı **AKTİF** yapar, ardından bakım modunu kapatır.
- Yalnız ayar değiştirildiyse **KAYDET VE SİLAHLARI AKTİF ET** düğmesi aynı kayıt/aktif etme işlemini yapar. İptalde önceki geçerli kayıt korunur ve hareket yeniden aktif olur.
- Uygulama veya USB bağlantısı beklenmedik biçimde kaybolursa Controller ve Gun firmware'leri en geç 180 saniye içinde hareketi tekrar aktif eden fail-safe kullanır. Her normal açılışta varsayılan durum **AKTİF**tir; geçici pasif durum flash'a yazılmaz.
- Fiziksel kısayolun Windows programını açabilmesi için `GT_SUPER_CONTROLLER.exe` Windows başlangıcında çalışmalı, normalde küçültülmüş durumda beklemelidir.
- TeknoParrot yönetici yetkisiyle çalıştırılıyorsa genel `2 + 5` kısayolunun tek `2`/`5` Start darbelerini güvenle yeniden gönderebilmesi için uygulama da aynı yetki düzeyinde çalıştırılmalıdır. En kararlı kurulumda iki program da normal kullanıcı yetkisiyle çalışır.

## Kalibrasyon

Kalibrasyon tam ekran dört köşe sihirbazıyla yapılır; merkez noktası kullanılmaz. Sıra **SOL ÜST → SAĞ ÜST → SAĞ ALT → SOL ALT** şeklindedir. Hedefte kullanılan tetik Controller Pico'dan gelir; masaüstü uygulaması ilgili silah Pico'ya `CAL CAPTURE` komutu gönderir. Kalibrasyon boyunca Controller bakım modunda, iki silah hareketi pasif durumda kalır. Başarılı değerler CRC'li iki sektörlü flash kaydına yazılır; ardından servis ayarlarının atomik kayıt onayı alınır ve iki silah otomatik aktif edilir. Doğrulama başarısızsa önceki çalışan kalibrasyon korunur. USB kesilmesi veya 120 saniyelik ölçüm süresi aşımı işlemi güvenli biçimde iptal eder.

Ayrıntı: [docs/KALIBRASYON.md](docs/KALIBRASYON.md)

## Röle güvenlik davranışı

Varsayılan mod `PULSE`:

- tetik kenarında 60 ms röle darbesi,
- 120 ms yeniden tetikleme beklemesi,
- oyuncu başına bağımsız 300 saniye hareketsizlik koruması,
- USB ayrılır veya askıya alınırsa iki röle de kapanır,
- 2 saniyelik donanım watchdog'u.

`FOLLOW` modunda röle tetiği takip eder; tek basışta en fazla 250 ms açık kalır. Bu sınır, solenoid veya recoil bobininin sürekli enerjili kalmasını engellemek için vardır. Gerçek donanımın izin verdiği darbe süresi ayrıca üretici verisine göre ayarlanmalıdır.

## 1 kredi çalışma biçimi

Coin butonu klavyeden `1` gönderir. Kredi havuzunu oyun yönetir; bu nedenle iki oyuncu aynı oyun kredi sayacını kullanır. P1 Start `2`, P2 Start `5` gönderir.

Uygulama, TeknoParrot'u şu biçimde başlatır:

```text
TeknoParrotUi.exe --profile=<ParadiseLost.xml> --startMinimized
```

Servis menüsü tuşları kabin/oyun yapılandırmasına göre değişebildiğinden projede tahmini bir tuş dizisi zorla çalıştırılmaz. Makro motoru hazırdır; yalnızca doğrulanmış `wait` ve `key` adımları kaydedilir. Ayrıntı: [docs/PARADISE_LOST_1_KREDI.md](docs/PARADISE_LOST_1_KREDI.md)

## GitHub'da yeni UF2 üretme

Depoyu GitHub'a yükledikten sonra **Actions → Build UF2 and Windows App → Run workflow** seçilir. İş akışı aşağıdaki dosyaları üretir:

```text
gt_controller.uf2
gt_gun_p1.uf2
gt_gun_p2.uf2
GT_SUPER_CONTROLLER_<sürüm>.exe
SHA256SUMS_UF2.txt
SHA256SUMS_WINDOWS.txt
```

Yeni sürüm etiketi oluşturmak için:

```powershell
python scripts/set_version.py 0.4.0
git add VERSION desktop/pyproject.toml desktop/gt_super_controller/version.py
git commit -m "Release 0.4.0"
git tag v0.4.0
git push origin HEAD
git push origin v0.4.0
```

Etiket iş akışı tamamlandığında aynı dosyalar otomatik GitHub Release'e eklenir. Ayrıntı: [docs/GITHUB_UF2.md](docs/GITHUB_UF2.md)

## Yerel geliştirme

### Firmware

Gerekli araçlar: CMake, Ninja, Arm GNU toolchain ve Raspberry Pi Pico SDK.

```bash
export PICO_SDK_PATH=/opt/pico-sdk
./scripts/build_firmware.sh
```

Çıktılar `dist/firmware/` altında oluşur.

### Windows uygulaması

Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build_windows.ps1
```

Kaynak çalıştırma:

```powershell
cd desktop
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m gt_super_controller
```

## Kararlılık önlemleri

- GPIO girişlerinde yazılımsal debounce.
- HID ve seri haberleşme için sınırlı iş yükü; seri komut patlamaları mouse/klavye raporlarını aç bırakmaz.
- Firmware, taşan seri komutun kalanını satır sonuna kadar atar; biçimlendirme tamponuna sığmayan veya TX kuyruğuna bütünüyle sığmayan JSON parçalı gönderilmez.
- Windows istemcisi USB CDC paketlerine bölünen JSON satırlarını birleştirir, bozuk satırı sonraki geçerli satırdan yalıtır ve 10 saniye protokol sessizliğinde portu yeniden açar.
- Ayarlarda şema sürümü, sıra numarası ve CRC32. Şema 1 kayıtları kalibrasyon/röle ayarları korunarak şema 2 çalışma modeline taşınır.
- Şema geçişindeki ilk flash yazımı, eski CRC-geçerli kaydı karşı sektörde koruyacak hedef seçimi kullanır.
- Flash sonunda ayrılmış iki 4 KiB sektöre dönüşümlü kayıt; yazma sonrası byte-byte doğrulama.
- Firmware `.bin` boyutunun ayrılmış 8192 baytlık ayar alanına taşmadığını derleme sırasında denetleme.
- Geçersiz/bozuk ayarda güvenli varsayılanlara dönüş.
- Röle çıkışlarının açılışta, USB kopmasında ve reboot öncesinde kapatılması.
- Profesyonel dört köşe sihirbazı; merkez adımı yoktur, kararsız köşe otomatik yeniden istenir ve sonuç kalite puanıyla doğrulanır.
- Kalibrasyon sırasında mouse raporları ile Controller klavye/röle çıkışları kesilir; Controller bakım modu 180 saniye, Gun kalibrasyon oturumu 120 saniye süre aşımına sahiptir.
- Tetikler yalnız Controller Pico'dadır; kalibrasyon ölçümü Controller olayından ilgili silah Pico'ya yönlendirilir.
- Fiziksel Start 1 + Start 2 ve Windows genel 2 + 5 kısayolu aynı 10 saniyelik kalibrasyon isteğini kullanır; tek tuşlar normal Start darbesi olarak yeniden gönderilir, başarısız ortak basış oyun Start'ı üretmez.
- Kalibrasyon isteği hareket aç/kapat geçişi değildir: her başarılı uzun basış bakım modunu ve pasif hareketi zorlar, uygulamayı öne getirir.
- Controller'ın tek seferlik `calibration_request` olayı kaybolursa periyodik `maintenance=true` ve `motion_enabled=false` durumu uygulama tarafından kurtarma sinyali olarak kullanılır.
- Kenar payı ve eksen yönleri Gun Pico'ya tek atomik `APPLY` komutuyla yazılır; uygulama flash kayıt onayını almadan oturumu başarılı saymaz.
- Controller ve iki Gun Pico için 180 saniyelik hareket fail-safe'i vardır. Uygulama canlı oturumda 60 saniyede bir bakım/hareket kilidini yeniler; çökme veya USB kaybında kilit kendiliğinden kalkar.
- Hareket durumu çalışma belleğindedir ve her normal açılışta aktif başlar; bağlantısı yenilenen silah Pico mevcut oturum durumuyla otomatik eşitlenir.
- Windows yapılandırmasının atomik kaydı ve bozuk dosyanın `.invalid.json` olarak karantinaya alınması.
- Dönen günlük dosyaları ve sınırlı seri komut/UI kuyrukları.
- Servis makrosu hata verse bile çalışan oyun işlemi izlenmeye devam eder; işlem tutamacı kaybolmaz ve ikinci oyun kopyası başlatılmaz.

## Belgeler

- [Bağlantı ve elektrik güvenliği](docs/BAGLANTI.md)
- [Kalibrasyon](docs/KALIBRASYON.md)
- [GitHub Actions / UF2](docs/GITHUB_UF2.md)
- [Paradise Lost ve 1 kredi](docs/PARADISE_LOST_1_KREDI.md)
- [Seri protokol](docs/PROTOKOL.md)
- [Kurulum ve kabul testleri](docs/TEST_PLANI.md)
- [Doğrulama ve derleme durumu](docs/BUILD_STATUS.md)

## Desteklenen ortam

- Firmware hedefi: Raspberry Pi Pico / RP2040, Pico SDK `2.3.0`.
- Masaüstü: Windows 10/11, Python 3.11+ kaynak çalıştırma veya GitHub'da üretilen tek EXE.
- Oyun başlatıcı: TeknoParrot profil tabanlı komut satırı.

## Lisans

MIT. Arcade oyununun, TeknoParrot'un ve ilgili ROM/oyun dosyalarının lisansları bu depoya dahil değildir.
