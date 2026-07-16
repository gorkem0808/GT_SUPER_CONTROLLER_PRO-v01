# GitHub Actions ile UF2 ve EXE Üretme

## 1. Depoyu oluşturma

GitHub'da boş bir depo oluşturun. Bu proje klasörünün içeriğini deponun köküne gönderin:

```powershell
git init
git add .
git commit -m "Initial GT SUPER CONTROLLER"
git branch -M main
git remote add origin <GITHUB_REPO_ADRESI>
git push -u origin main
```

`.github/workflows/build.yml` otomatik algılanır.

## 2. Otomatik derleme

İş akışı şu olaylarda çalışır:

- `main` dalına push,
- pull request,
- Actions ekranından elle çalıştırma,
- `v*` sürüm etiketi.

Firmware işi `ubuntu-24.04` üzerinde Pico SDK `2.3.0` etiketini indirir ve HEAD kısa commit kimliğinin `98a542c` olduğunu ayrıca doğrular. Ardından CMake, Ninja ve Arm GNU toolchain ile gerçek RP2040 ARM derlemesinde üç ELF/BIN/UF2 oluşturur, `.bin` boyutlarını kontrol eder ve UF2 checksum'larını üretir. ARM derlemesinden önce çift sektörlü flash şema geçişi ayrıca çalıştırılabilir host C testiyle denetlenir. Masaüstü işi `windows-2025` üzerinde Python `3.13`, `pytest 9.1.1` ve `PyInstaller 6.21.0` ile kaynakları `compileall` denetiminden geçirir, testleri çalıştırır ve tek EXE üretir.

## 3. Flash ayar alanı boyut koruması

Firmware, Pico flash belleğinin son iki 4 KiB sektörünü kalıcı ayarlar için ayırır. Toplam ayrılmış alan `8192` bayttır. İş akışındaki şu denetim her `.bin` dosyasının bu alana taşmadığını doğrular:

```text
python3 scripts/check_firmware_size.py \
  build/firmware/controller/gt_controller.bin \
  build/firmware/gun/gt_gun_p1.bin \
  build/firmware/gun/gt_gun_p2.bin
```

Dosya boyutu `2 MiB - 8192 bayt` sınırını aşarsa firmware işi hata verir ve UF2 yayınlanmaz. Farklı flash boyutlu bir kart hedeflenecekse hem `PICO_BOARD` hem bu denetimin `--flash-size` değeri birlikte ve donanım testiyle değiştirilmelidir.

## 4. Elle yeni UF2 üretme

GitHub'da:

1. **Actions** sekmesini açın.
2. **Build UF2 and Windows App** iş akışını seçin.
3. **Run workflow** düğmesine basın.
4. İsteğe bağlı sürüm alanına `0.4.0` gibi bir değer girin.
5. İş akışı tamamlanınca sayfanın **Artifacts** bölümünden indirin.

Firmware artifact içeriği:

```text
gt_controller.uf2
gt_gun_p1.uf2
gt_gun_p2.uf2
SHA256SUMS_UF2.txt
```

Windows artifact içeriği:

```text
GT_SUPER_CONTROLLER_0.4.0.exe
SHA256SUMS_WINDOWS.txt
```

Elle verilen sürüm numarası artifact adına ve firmware/uygulama sürüm bilgisine yazılır. Kaynak depodaki `VERSION` dosyası yalnız release hazırlarken kalıcı değiştirilir.

## 5. GitHub Release oluşturma

Sürüm numarasını üç dosyada güvenli biçimde güncelleyin:

```powershell
python scripts/set_version.py 0.4.0
python scripts/set_version.py --check
```

Sonra etiket gönderin:

```powershell
git add VERSION desktop/pyproject.toml desktop/gt_super_controller/version.py
git commit -m "Release 0.4.0"
git tag v0.4.0
git push origin HEAD
git push origin v0.4.0
```

Etiket iş akışı, iki artifact'i indirir ve tüm UF2/EXE/checksum dosyalarını aynı GitHub Release'e yükler. İş tekrar çalıştırılırsa mevcut release dosyaları `--clobber` ile güncellenir.

Alternatif yardımcı komut:

```powershell
.\scripts\new_release.ps1 -Version 0.4.0 -Push
```

Bu komut yalnız çalışma ağacı temizse sürümü günceller, commit ve tag oluşturur; `-Push` verilirse origin'e gönderir.

## 6. UF2'yi Pico'ya yükleme

1. Pico USB kablosunu çıkarın.
2. Pico üzerindeki `BOOTSEL` düğmesini basılı tutun.
3. USB kablosunu takın ve BOOTSEL'i bırakın.
4. Açılan `RPI-RP2` sürücüsüne doğru UF2'yi kopyalayın.
5. Pico yeniden başlar ve sürücü kapanır.

Çalışan firmware'de Windows uygulamasındaki **BOOTSEL** düğmesi de ilgili Pico'yu yükleme moduna alır.

## 7. Checksum doğrulama

PowerShell örneği:

```powershell
Get-FileHash .\gt_controller.uf2 -Algorithm SHA256
Get-Content .\SHA256SUMS_UF2.txt
```

Değerler aynı olmalıdır. Fark varsa dosyayı Pico'ya yüklemeyin.

## 8. İş akışı güvenliği

- Üçüncü taraf release action'ı kullanılmaz; GitHub runner içindeki `gh` CLI aracı kullanılır.
- `contents: write` izni yalnız release işine verilir.
- Pull request işlerinde release oluşturulmaz.
- Pico SDK tag ve commit kimliği birlikte sabitlenmiştir.
- `checkout 7.0.0`, `setup-python 6.3.0`, `upload-artifact 7.0.1` ve `download-artifact 8.0.1` release etiketleri açıkça sabitlenmiştir.
- Windows test/EXE araçları `requirements-dev.txt` içinde tam sürüme sabitlenmiştir; sürüm yükseltmesi ayrı değişiklik ve kabul testiyle yapılmalıdır.
- GitHub'ın ürettiği gerçek ARM UF2 işi başarılı olmadan sürüm kabul edilmez.
