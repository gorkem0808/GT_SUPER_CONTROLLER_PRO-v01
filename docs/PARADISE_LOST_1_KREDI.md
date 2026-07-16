# Paradise Lost / TeknoParrot ve 1 Kredi

## Güvenilir yöntem

En güvenilir yöntem oyunun test/service menüsünde coinage değerini bir kez **1 coin = 1 credit** olarak ayarlayıp oyunun kendi NVRAM/yapılandırmasına kaydetmektir. Coin butonu ortak kontrol Pico üzerinden klavye `1` tuşunu gönderir; kredi sayacını oyun tutar.

Varsayılan girişler:

| İşlev | Tuş |
|---|---|
| Coin | `1` |
| P1 Start | `2` |
| P1 Bomba | `4` |
| P2 Start | `5` |
| P2 Bomba | `7` |
| P1/P2 Tetik | Ayrı HID mouse sol butonu |

Tetik klavye tuşları `3` ve `6` firmware'de tanımlıdır fakat çift giriş oluşmaması için varsayılan kapalıdır. Coin, start ve bomba girişleri fiziksel basış başına tek, varsayılan 80 ms'lik HID tuş darbesi gönderir; butonu basılı tutmak ilave kredi üretmez.

## TeknoParrot başlatma

Uygulamada:

- Çalıştırılabilir dosya: `TeknoParrotUi.exe`
- Profil: Paradise Lost kullanıcı profili XML dosyası
- `Başlangıçta küçült`: açık
- `Tüm Pico'ları bekle`: açık

Komut şu biçimde kurulur:

```text
TeknoParrotUi.exe --profile=C:\...\ParadiseLost.xml --startMinimized
```

`Tüm Pico'ları bekle` açık olduğunda yalnız COM portlarının görünmesi yeterli değildir. Controller, P1 Gun ve P2 Gun aygıtlarının kimlik bilgisiyle birlikte son 5 saniye içinde canlı durum mesajı göndermesi gerekir. Otomatik başlatma denemesi başarısız olursa uygulama 30 saniye sonra yeniden dener.

Oyun profilinde RawInput/lightgun yapılandırması açılır ve P1/P2 için ayrı fiziksel GT Gun aygıtı seçilir.

## İsteğe bağlı servis makrosu

Bazı kurulumlarda test menüsü ayarı kalıcı olmayabilir. Uygulama, oyun başlatıldıktan sonra Windows `SendInput` ile sınırlı bir tuş makrosu çalıştırabilir. Desteklenen adımlar:

```json
[
  {"type": "wait", "ms": 1000},
  {"type": "key", "key": "F2", "hold_ms": 80}
]
```

Bu yalnızca **biçim örneğidir**; Paradise Lost için gerçek servis tuşu sırası olduğu anlamına gelmez. Doğru sıra kabindeki TeknoParrot profili, oyun sürümü ve test tuşu eşlemesine göre ölçülmelidir.

Desteklenen tuşlar:

- `0–9`, `A–Z`
- `F1–F24`
- `ENTER`, `ESC`, `SPACE`, `TAB`, `BACKSPACE`
- `UP`, `DOWN`, `LEFT`, `RIGHT`
- `HOME`, `END`, `PAGEUP`, `PAGEDOWN`, `INSERT`, `DELETE`
- `SHIFT`, `CTRL`, `ALT`

Makro sınırları:

- en fazla 100 adım,
- tek bekleme en fazla 300 saniye,
- tuş basılı tutma 20–5000 ms,
- toplam makro süresi en fazla 15 dakika,
- makro etkinse en az bir adım zorunlu,
- durdurma isteği veya oyun işleminin kapanması en geç yaklaşık 50 ms içinde algılanır,
- iptal olsa bile basılmış tuş `finally` bloğunda bırakılır.

## Doğrulama yöntemi

1. Otomatik makroyu kapalı tutun.
2. Oyunu uygulamadan başlatın.
3. Service/test menüsüne elle girip 1 coin/1 credit ayarını yapın.
4. Oyunu normal biçimde kapatıp yeniden açın.
5. Ayar korunuyorsa makro kullanmayın.
6. Korunmuyorsa yalnız doğrulanmış tuş ve bekleme sırasını JSON'a girin.
7. Kabini en az 10 soğuk açılışta deneyin; servis menüsünde takılı kalma veya yanlış ayar olmadığını doğrulayın.
8. Oyun beklenenden erken kapanırken makronun devam etmediğini günlükten doğrulayın.

## Önemli sınırlama

Makro ekran görüntüsünü okumaz ve menü durumunu algılamaz. Bu nedenle oyun yükleme süresi değişirse yanlış menüye tuş gönderme riski vardır. Kalıcı oyun/NVRAM ayarı her zaman makrodan daha güvenilirdir. Gerçek servis tuşları doğrulanmadan örnek JSON etkinleştirilmemelidir.
