# Ceviz — yayın durumu ve devir notu

Son güncelleme: **23 Ağustos 2026**

## Güncel sürüm

- Sürüm: **Ceviz 2026.6.5 Beta 2**
- TestFlight build: **1787435232**
- Dış TestFlight grubu: **Beta**
- Public link: <https://testflight.apple.com/join/nEdn2Np2>
- App Store Connect durumu: **VALID / BETA_APPROVED**
- Build ve upload doğrulaması:
  <https://github.com/MertBasar0/openclaw/actions/runs/32600537529>
- Dış grup dağıtım doğrulaması:
  <https://github.com/MertBasar0/openclaw/actions/runs/32605320929>
- GitHub prerelease:
  <https://github.com/MertBasar0/ceviz/releases/tag/ceviz-watch-v2026.6.5-beta.2>

Build yalnızca App Store Connect'e yüklenmiş değildir; dış `Beta` grubuna
atanmış ve public TestFlight linkinden erişilebilir olduğu doğrulanmıştır.

## Bağımsız repo geçişi

- Aktif repo: <https://github.com/MertBasar0/ceviz>
- Görünürlük: **PRIVATE** — Apple signing secret'ları yeniden girilip yeni
  repodan imzalı build doğrulanana kadar public yapılmayacak.
- Varsayılan branch: `main`
- Ceviz'e ait sekiz ürün commit'i, OpenClaw geçmişi taşınmadan korundu ve
  `watch-ceviz/` içeriği yeni repo köküne düzleştirildi.
- Beta 1 ve Beta 2 tag/prerelease kayıtları yeni repoda yeniden yayımlandı.
- Build ve screenshot workflow'ları yeni kök yollarına ve `main` branch'ine
  uyarlandı; GitHub tarafından aktif workflow olarak tanındı.
- Yeni kök düzende backend/contract testleri yerelde **34/34** geçti.

GitHub mevcut Actions secret değerlerini dışarı vermediği için aşağıdaki
secret'lar yeni repoya güvenli kaynaklarından yeniden girildi:

- `APPLE_API_ISSUER_ID`
- `APPLE_API_KEY_ID`
- `APPLE_API_KEY_P8`
- `APPLE_CERTIFICATE_P12`
- `APPLE_CERTIFICATE_PASSWORD`
- `APPLE_TEAM_ID`

Yeni Apple Distribution sertifikası için iPhone ve Watch provisioning
profilleri yenilendi. Bağımsız repodaki ilk imzalı build ve TestFlight upload
başarıyla tamamlandı:

- Build: **2026.6.5 (1787509178)**
- App Store Connect işlenme durumu: **VALID**
- Workflow: <https://github.com/MertBasar0/ceviz/actions/runs/32657599799>

Bu build repo/secret/signing migration doğrulaması içindir; kullanıcıya dönük
kod değişikliği içermediğinden public external gruba eklenmedi. Public Beta 2
build `1787435232` dış testerlar için aktif kalmaktadır.

## Tamamlananlar

- Apple Watch'taki terminal bildiriminin sonucuna dokunulduğunda ana ekranın
  “sonuç hazırlanıyor” durumunda kalması düzeltildi. Bildirimin taşıdığı
  yetkili terminal sonucu artık bekleyen poll kaydı temizlenmiş olsa bile
  uygulanıyor.
- Düzeltme fiziksel iPhone + Apple Watch akışında kullanıcı tarafından
  doğrulandı: bildirim saate uygulama açılmadan ulaştı, bildirime dokunuldu ve
  ana ekran tamamlanan sonucu doğru gösterdi.
- Backend ve contract testleri **34/34** geçti; iOS Release build, gömülü watchOS
  uygulaması, imzalama ve TestFlight upload aynı zorunlu CI bariyerinden geçti.
- TestFlight build `1787435232`, public `Beta` grubuna eklendi ve dış beta
  durumu `BETA_APPROVED` olarak tekrar okunarak doğrulandı.
- Temiz Ubuntu 24.04 WSL2 dağıtımında sıfırdan teknik onboarding; kurulum,
  servis, QR eşleşme, token korumalı erişim, komut polling ve yeniden başlatma
  kalıcılığı doğrulandı.
- Tailscale ile farklı ağlardan özel erişim ve yerel WSL2 relay seçenekleri
  dokümante edildi.
- Beş adet App Store 6.9 inç portre screenshot'ı (1320×2868 JPEG), privacy ve
  marketing sayfaları ile App Store metadata kaynak metinleri hazırlandı.
- Beta 1'deki eski “smoke test” lansman ifadesi, Beta 2'de gerçekten doğrulanan
  bildirimden sonuca geçişi açıklayacak biçimde güncellendi.
- `ceviz-watch-v2026.6.5-beta.2` etiketi ve **Ceviz 2026.6.5 Beta 2** GitHub
  prerelease'i yayımlandı.
- Ceviz kaynakları OpenClaw fork'undaki kalıcı ürün branch'inden bağımsız
  `MertBasar0/ceviz` reposuna, ürün geçmişi korunarak taşındı.

## Açık beta için kabul edilen doğrulama riski

Bağımsız bir dış kullanıcının dokümantasyonu hiç yardım almadan tamamladığı
onboarding testi **gerçekte yapılmış sayılmıyor**. Elde uygun cihaz ve test
kullanıcısı olmadığı için bu, sürümü durduran bir kapı olmaktan çıkarıldı.
İzole temiz ortamda aynı cihaz üzerinde yapılan teknik onboarding, açık betaya
çıkmak için proxy doğrulama olarak kabul edildi. İlk gerçek dış kullanıcı akışı
lansman sonrası izlenecek, sorun çıkarsa hızlı düzeltme yapılacak.

Benzer şekilde macOS ve bare Linux yolları gerçek donanımda doğrulanmadı.
Bunlar “geçti” olarak raporlanmıyor; açık beta geri bildirimiyle kapatılacak
bilinen kapsam boşluklarıdır. WSL2 şu an en güçlü doğrulanmış kurulum yoludur.

## Sıradaki işler

1. Repo görünürlüğünü public'a döndürme kararını ver.
2. Discord, X ve LinkedIn için açık beta duyurularını yayımla.
3. Public TestFlight linki, ilk dış kurulumlar ve bildirim-sonuç akışı için
   geri bildirimleri izle.
4. Uygun donanım erişilebilir olduğunda macOS ve bare Linux kurulumlarını ayrıca
   doğrula; sonuçları bu dosyaya ekle.

## Güvenlik ve yerel artefaktlar

- Eşleşme token'ı içeren yerel QR dosyaları repoya alınmaz;
  `.gitignore` içindeki `ceviz-*-pairing.png` kuralı bunu engeller.
- Eski Sideloadly kurulum hatası artık güncel yayın akışının parçası değildir;
  dağıtım imzalı TestFlight build'leri üzerinden yapılmaktadır.
