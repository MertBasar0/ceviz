# Ceviz — yayın durumu ve devir notu

Son güncelleme: **5 Eylül 2026**

## Hazırlanan paket — Beta 4

Kullanıcı, güvenilir bilek akışı geliştirmelerini ve testlerden sonra commit,
TestFlight upload, dış Beta grubuna dağıtım, widget kimliği/imzalama profilini
onayladı. Yerel Ceviz ve bildirim servislerinin güncellenmesi de onaylandı;
OpenClaw gateway/model/bağlantı yapılandırması değiştirilmeyecek.

- Ortak iş-sonuç anlamı, Watch sonuç kartı, kadran düğmesi ve daha güvenli
  teslim/bekleyen sonuç akışı uygulandı; aday doğrulamaları devam ediyor.
- Uygulama kaynak commit'i: `311ae907b2be15081ef094389f4d5f3a08045682`.
- Yerel Python **49/49** ve gerçek relay handler **3/3** kontrolleri geçti.
  Apple ortamında aynı testler, Ruby imzalama sınırı testi, iki Swift regresyon
  programı ve iPhone + Watch + gömülü WidgetKit eklentisinin imzasız Release
  derlemesi geçti. İmzalı arşiv/yükleme henüz doğrulanmadı.
- İlk Apple doğrulama çalışması (imza/yükleme başlamadı):
  <https://github.com/MertBasar0/ceviz/actions/runs/33929890858>.
  Gerçek Watch açılışı başarılı; dışarıdan `simctl openurl` çağrısı
  `LSApplicationWorkspaceErrorDomain 115` ile başarısız. Kadran gezinmesi
  doğrulanmış sayılmadı. Watch URL kaydına `Editor` rolü eklendi; SDK ile eşleşen
  simülatör seçimi ve ek tanı kontrolü hazır. Ek 9 kontrolle yerel Python toplamı
  **58/58** geçti.
- İkinci Apple kontrolü (`b8b636c6d6acfe72062e43be24187f4b33151223`):
  <https://github.com/MertBasar0/ceviz/actions/runs/33931103215>.
  Testler ve native derleme yeniden geçti; SDK/runtime 26.4, 40 mm Watch
  simülatörü, kurulu URL scheme + `Editor` kaydı doğrulandı. Dış `openurl`
  yine 115 ile başarısız; günlüklerde uygulama kimliği uyuşmazlığı ve scheme
  handler bulunamadığı görüldü. Dağıtım imzası/yükleme yine başlamadı.
  Bu komut gerçek WidgetKit komplikasyon tıklamasının kanıtı değildir.
  Simülatörün normal, sertifikasız yerel imzasıyla kimlik doğrulaması hazır;
  üretilen üç paket ve kurulu Watch kimliği kontrol edilecek. Yerel Python
  toplamı **62/62** geçti; hatanın nedeni henüz kesinleşmedi.
  40 mm ekranda boş footer'ın alan tüketmesi de düzeltildi; yeni görsel kanıt bekliyor.
- iPhone İngilizce demo ekran kontrolü **5/5 görsel incelendi**:
  <https://github.com/MertBasar0/ceviz/actions/runs/33929929029>.
  `[NEEDS INPUT]` liste/raporda tutarlı, diğer raporlarda `[DONE]`; bu kanıt
  örnek veriyle düzen/durum sunumunu kapsar, gerçek görev teslimini değil.
- Türkçe iPhone simülatör ekranları da **5/5 incelendi**:
  <https://github.com/MertBasar0/ceviz/actions/runs/33931213126>.
  iPhone 17 Pro Max simülatöründe 1320×2868 JPEG; `[GİRDİ BEKLİYOR]` / `[TAMAM]`
  ayrımı ve ajan-bildirimli sonuç başlığı tutarlı. Fiziksel cihaz testi değildir.
- Bildirim relay'i güncellendi: canlı sürüm
  `5b72fe99-6bad-4df8-84f1-56cbf60c3153` (%100), `/healthz` HTTP 200.
  Yayımlanan kaynak SHA256:
  `26030c112c65f734690539c69147272654ec078b6301d8752637d43089130ca5`.
  Wrangler `4.129.0`; testler ve dry-run geçti, mevcut KV/sırlar korundu.
  Bu kayıt kaynak hash'i + canlı sürüm kimliği kanıtıdır; uzak derlenmiş
  bundle ile byte eşitliği veya gerçek cihaz APNs teslim testi değildir.
- Yerel `watch-ceviz-backend.service` aynı kaynak commit'indeki 10 kod/contract
  dosyasıyla güncellendi. Başarılı geçişin stop → API hazır üst sınırı **0,654 sn**.
  HTTP sağlık/auth API **200**, yetkisiz API **401**; 50 geçmiş işin ID/durumları
  (44 completed, 6 failed) ve `jobs.json` byte içeriği değişmedi; aktif iş yoktu.
  Ayarlar, servis yapılandırması, anahtarlar ve Python ortamı korundu.
  Liste/rapor/report_meta outcome eşleşmesi okuma istekleriyle doğrulandı.
  İlk denemedeki yanlış kontrol adresi kod-only rollback'e yol açtı; kontrol
  adresi düzeltildi, veri geri yükleme/sıfırlama yapılmadı.
  OpenClaw yapılandırması veya servisi değiştirilmedi; yalnız mevcut gateway
  systemd durumunun aynı kaldığı ölçüldü, gateway çalışma sağlığı iddiası yok.
- Sürüm notları ve fiziksel kabul listesi:
  [Beta 4 aday notları](docs/release-notes-2026.6.5-beta.4.md).
- Bu bölüm yeni build'in yayımlandığı anlamına gelmez. Aşağıdaki Beta 3,
  yeni dağıtım API ile doğrulanana kadar geçerli yayımlanmış sürümdür.
- Sonraki dilim: açık devam bağlamı, kişisel kısa yollar ve uygulama içi Doctor.
- Mevcut iş dosyası eşzamanlı yazma ve cihaz bazlı bildirim yeniden denemesi
  ayrıca ele alınmalı; garantili teslimat/uzak işte exactly-once iddiası yok.

## Güncel sürüm

- Sürüm: **Ceviz 2026.6.5 Beta 3**
- TestFlight build: **1788552567**
- Dış TestFlight grubu: **Beta**
- Public link: <https://testflight.apple.com/join/nEdn2Np2>
- App Store Connect durumu: **VALID / IN_BETA_TESTING**
- Build ve upload doğrulaması:
  <https://github.com/MertBasar0/ceviz/actions/runs/33914678643>
- Dış grup dağıtım doğrulaması:
  <https://github.com/MertBasar0/ceviz/actions/runs/33915265798>
- GitHub prerelease:
  <https://github.com/MertBasar0/ceviz/releases/tag/ceviz-watch-v2026.6.5-beta.3>

Beta 3 imzalı iOS/watchOS arşivi üretildi, App Store Connect tarafından `VALID`
olarak işlendi ve public `Beta` grubuna atandı. Internal ve external durumları
`IN_BETA_TESTING` olarak API üzerinden yeniden okunarak doğrulandı.

## Bağımsız repo geçişi

- Aktif repo: <https://github.com/MertBasar0/ceviz>
- Görünürlük: **PUBLIC** — signing migration sonrasında kullanıcı onayıyla
  yeniden public yapıldı.
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
kod değişikliği içermediğinden public external gruba eklenmedi. Güncel public
Beta 2 build'i `1787684689` olmuştur.

## Tamamlananlar

- Apple Watch komut kuyruğu `UserDefaults` üzerinde kalıcı hale getirildi.
  Komutlar tek tek gönderiliyor, yalnızca geçerli backend yanıtıyla teslim
  onayı alındığında kuyruktan siliniyor ve geçici hata/timeout durumunda yeniden
  denemek üzere korunuyor. Geç gelen onaylar da kalıcı kopyayı temizleyerek çift
  çalıştırmayı engelliyor; 15 dakikadan eski sesli komutlar sürpriz biçimde
  çalıştırılmıyor.
- Kuyruk düzeltmesi backend ve contract testlerinde **34/34** geçti; gerçek
  Xcode watchOS/iOS Release arşivi, imzalama, IPA üretimi ve TestFlight upload
  macOS CI'da doğrulandı. Build `1787684689`, public `Beta` grubuna atanarak
  internal ve external `IN_BETA_TESTING` durumuna getirildi.
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
- Public repo README'sine gereksinimler, clone/install, bağlantı seçimi, QR
  eşleşme ve credential güvenliği dahil uçtan uca onboarding eklendi.
- Kaynak kod ve dokümantasyon Apache-2.0 ile lisanslandı; Ceviz adı, logo,
  uygulama ikonları ve marka kimliği ayrı marka/brand-asset koşullarıyla tüm
  hakları saklı tutuldu. GitHub lisansı `Apache-2.0` olarak tanıdı.
- `.github/SECURITY.md` özel bildirim kanalı, desteklenen sürümler, kapsam ve
  operasyonel güvenlik uyarılarıyla yayımlandı.
- Canlı Ceviz ürün sayfasına public repo bağlantısı, doğrudan clone/install
  komutları, Tailscale önerisi ve QR eşleştirme adımları eklendi:
  <https://basarlabs.com.tr/ceviz/>. GitHub Pages dağıtımı başarıyla doğrulandı:
  <https://github.com/MertBasar0/basarlabs-site/actions/runs/32663945841>.

## Açık beta için kabul edilen doğrulama riski

İlk gerçek dış kullanıcı Ceviz'i kurup yerel Whisper transkripsiyonu ve Watch
yanıtı dahil gerçek akışa ulaştı. Böylece dış kurulumun çalışabildiği artık
gerçek kullanıcıyla doğrulandı. Ancak kullanıcının dokümantasyonu baştan sona
hiç yardım almadan nasıl izlediği gözlemlenmediği için süre ve sürtünme noktaları
henüz ölçülmüş sayılmıyor. Bir sonraki onboarding bu dört noktada izlenecek:
kurulum, eşleşme, ilk komut ve ilk tamamlanan sonuç.

Benzer şekilde macOS ve bare Linux yolları gerçek donanımda doğrulanmadı.
Bunlar “geçti” olarak raporlanmıyor; açık beta geri bildirimiyle kapatılacak
bilinen kapsam boşluklarıdır. WSL2 şu an en güçlü doğrulanmış kurulum yoludur.

## İlk dış kullanıcı geri bildirimi

OpenClaw Discord `showcase` paylaşımından sonra ilk dış kullanıcı uygulamayı
denedi. Yerel Whisper transkripsiyonu, yanıtların Watch'a dönmesi ve görsel
tasarım olumlu bulundu. Dört ürün sinyali kaydedildi:

- Saat kadranından erişilecek ek bir düğme/komplikasyon isteniyor.
- Ayrı backend kurulumu güven ve bakım riski gibi algılanıyor.
- İngilizce kullanım sırasında Türkçe metin sızıntıları görülüyor.
- Resmî OpenClaw iOS/Watch uygulamasıyla ürün sınırının daha açık anlatılması
  gerekiyor.

Bu geri bildirim sonucunda Ceviz'in konumu netleştirildi: Ceviz genel amaçlı
bir OpenClaw mobil istemcisi değil, **local-first ve Watch-first sesli görev ve
sonuç katmanıdır**. Ürün ilkeleri ve ölçülebilir büyüme döngüsü
[`STRATEGY.md`](STRATEGY.md) içinde tutuluyor.

## Beta 3 çalışma durumu

- Strateji manifesti ve resmî OpenClaw mobil istemcisinden ayrışan ürün sınırı
  yazıldı.
- İngilizce cihazlarda raporu yanlışlıkla Türkçeye zorlayan backend talimatı,
  Türkçe fallback metinleri, push başlıkları ve sabit izin açıklamaları
  locale-aware hale getirildi.
- İngilizce/Türkçe katalog anahtar eşitliği ve temel backend fallback'leri için
  otomatik testler eklendi. Yerel backend/contract/localization paketi
  **40/40** geçti.
- Secretsız, salt okunur `bash deploy/doctor.sh` tanılaması eklendi; kurulum ve
  CI akışına bağlandı. Bash sözdizimi doğrulandı.
- Ayrı backend'in gerekçesi, yetki sınırı, kaldırma adımları ve gerçek veri
  akışı `docs/security-model.md` içinde açıklandı.
- Gizlilik incelemesinde tamamlanma başlığı ve kısa Watch özetinin varsayılan
  Cloudflare relay üzerinden APNs'e geçtiği doğrulandı. Önceki “hiçbir sunucu
  içerik almaz” ifadesi doğru değildi; repo ve ürün sitesi metinleri gerçek
  akışı açıklayacak biçimde düzeltildi. Ürün ve gizlilik sayfaları canlıda
  doğrulandı:
  <https://github.com/MertBasar0/basarlabs-site/actions/runs/33914727508>.
- Beta 3 build `1788552567`, macOS CI'da imzalı iOS/watchOS arşivi olarak
  üretildi ve TestFlight'a başarıyla yüklendi:
  <https://github.com/MertBasar0/ceviz/actions/runs/33914678643>.

- Apple'ın build işlemesi tamamlandı; build public dış `Beta` grubuna atanarak
  internal ve external `IN_BETA_TESTING` durumunda doğrulandı:
  <https://github.com/MertBasar0/ceviz/actions/runs/33915265798>.

- App Store gizlilik beyanı yayımlandı: `Device ID`, `App Functionality`,
  kullanıcı/cihaz kimliğiyle bağlantılı, takip amacıyla kullanılmıyor. Privacy
  Policy URL ve User Privacy Choices URL olarak canlı Ceviz gizlilik sayfası
  kaydedildi.

## Sıradaki işler

### Beta 3 — güven ve onboarding

1. İngilizce arayüzde kalan Türkçe metinleri ve backend fallback çıktılarını
   temizle; iki dilin anahtar eşitliğini otomatik testle koru.
2. OpenClaw, yerel Whisper, servis, kimlik doğrulama, ağ ve eşleşme
   gereksinimlerini secretsız raporlayan `Ceviz Doctor` komutunu ekle.
3. Backend'in neden gerekli olduğunu, veri akışını, yetki sınırını ve tamamen
   kaldırma adımlarını kurulum sayfası ile README'de açıkça anlat.
4. Bu üç değişikliği test edip Beta 3 TestFlight build'i olarak yayımla ve ilk
   dış kullanıcıdan yeniden doğrulama iste.

### Beta 4 adayı — bilekten en hızlı erişim

5. Doğrudan ses yakalama ekranını açan Watch komplikasyonu/widget'ı geliştir.
6. Farklı Watch boyutunda ve bağımsız kurulumda ilk komut akışını doğrula.

### Büyüme ve kapsam doğrulaması

7. Public TestFlight linkinde kurulum, eşleşme, ilk komut ve ilk tamamlanan
   sonuç noktalarını ayrı ayrı izle.
8. X hesabı olmadığı için kısa vadede OpenClaw Discord, ilgili geliştirici
   toplulukları ve kişisel LinkedIn üzerinden odaklı duyuru yap.
9. Uygun donanım erişilebilir olduğunda macOS ve bare Linux kurulumlarını ayrıca
   doğrula; sonuçları bu dosyaya ekle.

## Güvenlik ve yerel artefaktlar

- Eşleşme token'ı içeren yerel QR dosyaları repoya alınmaz;
  `.gitignore` içindeki `ceviz-*-pairing.png` kuralı bunu engeller.
- Eski Sideloadly kurulum hatası artık güncel yayın akışının parçası değildir;
  dağıtım imzalı TestFlight build'leri üzerinden yapılmaktadır.
