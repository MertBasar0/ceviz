# Ceviz — yayın durumu ve devir notu

Son güncelleme: **13 Eylül 2026**

## Güvenilirlik onarımı — 13 Eylül, kod doğrulandı; Watch URL kapısı açık

Kullanıcı tam onarıma başlanmasını onayladı. Aşağıdaki değişiklikler yalnız
geliştirme dalında; **canlı kurulum veya yeni TestFlight build'i değildir**.
Mevcut Gateway, kimlik bilgileri, işler ve TestFlight dağıtımı değiştirilmedi.

- HTTP alımının sahibi artık bağlantı/başlık/gövde sınırlarını ve sınırlı
  eşzamanlılığı yönetiyor. Yarım yükleme diğer sağlık/iş sorgularını kilitlemiyor;
  iş anlık görüntüsü, aynı ses/hedefin eşzamanlı kabulü ve bildirim kaydı
  birleştirmesi aynı sahiplik sınırında düzeltildi. İzole gerçek TCP ve sözleşme
  paketi bağımsız tekrar çalıştırıldı: **81/81 geçti (53,204 saniye)**;
  geçici durum temizlendi. Gerçek Whisper veya Gateway komutu çalıştırılmadı.
  Geniş Windows tekrarında **207 test: 189 geçti, 18 platform testi atlandı
  (71,396 saniye)**; temizleme doğrulandı. Bildirim sınırı Node paketi **3/3**
  geçti. Bunlar gerçek telefon/saat veya model yürütme kanıtı değildir.
- Watch tarafında belirsiz teslimin görünürlüğü, uyanma/zaman aşımı takibi,
  geç gelen alındı bildiriminin eski “gönderiliyor” metnini bırakmaması ve
  iş listesinin yükleniyor/hata/yenileme durumları hazırlandı. Telefon daha
  küçük, ölçülmüş üst sınırı olan özet liste gönderiyor; saat yeni işleri önce
  gösteriyor. Aynı bağlantıyı yenileme, bekleyen kayıtları temizleyen gerçek
  eşleştirme değişiminden ayrıldı. Swift kontrolleri geçti; tam Apple
  uygulama/ekran ve gerçek cihaz kanıtı aşağıdaki kapılara bağlı.
- Windows/WSL ömür yönetimi LAN relay'den ayrıldı: görev, aracı PowerShell
  süreci olmadan doğrudan seçilen dağıtımın WSL istemcisini izliyor. Windows
  Tailscale yolu kimliği doğrulanmış localhost hedefini kullanıyor; bozuk DNS
  veya ağ adımında başarılı kurulum/QR bildirilmiyor. Yeni görev canlı
  Windows'a kurulmadı; WSL başlatılmadı. Gerçek görev durdurma/yeniden başlatma,
  konsol görünürlüğü ve terminal kapandıktan sonraki süreklilik açık kanıt
  kapılarıdır. Eski LAN ve ortam-token Doctor sınırları deploy rehberinde.
  Son ek düzeltme: LAN kurucusunda `-Distro` zorunlu; belirtilmezse ilk
  dağıtımı seçmiyor. Eski kaynakta beş alt senaryoda kırmızı olan regresyon
  düzeldi; son Windows paketi bağımsız tekrarında **10/10 geçti (15,108 sn)**.
- Bağlantı yenilemesinde önceki URLSession'ların sahipliği korunuyor; gerçek
  bağlantı değişikliği mevcut ve önceki oturumları birlikte iptal ediyor.
  Görev yaratımı/sıfırlama yarışı aynı kilit altında; capability kontrolündeki
  eski oturum yeni bağlantıya komut taşıyamıyor. Kaynaklar bağımsız incelendi;
  yeni native oturum/iptal/temizleme regresyonları Apple CI'da geçti.
  Swift bulunmayan Windows ortamında native test çalıştırılmadı.
- **13 Eylül ek onayı alındı:** Watch sesli gönderimlerinin telefon/backend
  SQLite kimlik kaydı, yalnız geliştirme dalına commit/push ve Apple doğrulaması
  ile bulunmayan özel inceleme araçları yerine bağımsız kaynak incelemesi ve
  regresyon testi kullanımı onaylandı. Canlı servis veya TestFlight dağıtımı bu
  onayın kapsamında değil.
- Telefon ve yardımcı serviste yeni teslimat kaydı yalnız kimlik/hedef/durum
  içeriyor; ses, transkript ve erişim anahtarı içermiyor. Telefon kaydı HTTP'den,
  backend rezervasyonu STT/iş başlatmadan önce yazılıyor. Kaybolmuş yanıt önce
  aynı kimlikle sorgulanıyor; belirsiz kayıt otomatik tekrar yetkisi vermiyor.
  Her iki tarafın veritabanı kaybolsa bile gecikmiş WC dosyası yeniden kabul
  edilmesin diye Watch, telefon kayıt kimliğini ilk aktarım öncesi sabitliyor;
  telefon da backend kayıt kimliğini ilk POST öncesi sabitliyor. Önceki sürümün
  kayıtları bu protokole sessizce yükseltilmiyor. 15 dakikalık ses saklama sınırı
  korunuyor. Güncelleyici belirsiz Watch rezervasyonu varken kurulumu durduruyor.
- Son geniş izole Windows tekrarında **224 test: 206 geçti, 18 platform testi
  atlandı (84,348 saniye)**; tüm geçici durum temizlendi. Node bildirim sınırı
  **3/3** ve Git Bash kurucu/Doctor sözdizimi geçti. Ek backend paketi gerçek
  SQLite, TCP yanıt kaybı, yarışan iki yardımcı süreç ve iş başlatmadan önce/
  sonra süreç ölümü içeriyor; gerçek kullanıcı komutu/Whisper/Gateway yok.
  Bağımsız telefon incelemesinde bulunan çift depo kaybı/yeniden bağlama açığı
  kayıt kimliği sabitlemesiyle kapatıldı ve native regresyona eklendi.
- **Tamamlanma kapısı:** Swift kayıt/taşıma testleri, üç uygulamanın derlemesi
  ve iPhone UI **9/9** geçti; 25 iPhone görüntüsü incelendi. Tam Apple koşusu
  Watch simülatörünün URL açılışında **115** ile başarısız bitti. Sonraki Watch
  ekran testleri çalışmadı; test kapısı gevşetilmedi ve dağıtıma hazır sayılmıyor.
  Gerçek telefon/saat ağ kesintisi ve kadran dokunuşu denemesi ayrıca gerekli.
- **Ayrı açık takip:** HTTP'nin 10 saniyelik süresi yalnız istek alımını
  kapsar. Süresiz takılan yerel STT işlemini durdurma/izole etme henüz
  çözülmedi; mevcut testler bekleyen STT sırasında diğer yolların yanıtını ve
  test STT'si serbest bırakılınca temiz kapanışı kanıtlıyor.
- Bağımsız backend incelemesinde yeni sürümlü kabul yolunda engel bulunmadı.
  Süreçler arası test iki **yeni protokol** gönderimini kapsar; eski endpoint
  ile yeni endpoint'in aynı durum klasörünü paylaşan farklı helper süreçlerinde
  eşzamanlı çalışması atomik kabul garantisinin dışında. Mevcut tek-helper
  kurulumu korunmalı; evrensel “exactly once” veya fiziksel güç kesintisi kanıtı
  iddia edilmemeli.

Onarım başlangıcı `afc79c71a8aaa564edf39529aa98d6568cb26c71` karşısında
değişiklik hesabı (`git diff --numstat`):
üretim **+2105/-453, net +1652**, test **+2241/-6, net +2235**, CI **+58/-19**.
Test/CI hesabında 26 satırlık Swift komut listesinin ortak betiğe taşınması var;
bu bir yeni test paketi değil. Son üretim artışı oluşturulmuş fakat henüz
başlatılmamış ağ görevlerinin aynı sahipte iptal/temizleme takibine ait.
Üretim artışı tek HTTP alım/eşzamanlılık sahibi, açık Watch teslim/liste durumları,
iptal edilebilir oturum sahipliği ve ağdan bağımsız Windows görev sınırına ait.
Ek artış metadata-only SQLite kabul/durum sahipleri ve Watch kuyruk/odak
ayrımına ait; mevcut SQLite bootstrap ortaklaştırıldı, telefonun doğrudan eski
ses POST yolu kaldırıldı. Eski kayıtlar için sessiz protokol geçişi yok.
Seri HTTP yolu, LAN relay'nin WSL gözeticiliği ve aynı bağlantıyı sıfırlama
davranışı kaldırıldı/ayrıldı; taslak PowerShell yaşam-süresi sarmalayıcısı da
doğrudan görev eylemiyle tamamen kaldırıldı. Yeni paket bağımlılığı yok.

### İlk uzak doğrulama ve macOS test temizliği

Onarım `1c745e2acce3ec15c164dab9fb56b27f9bfb399e` olarak yalnız geliştirme
dalına gönderildi. [Helper koşusunda](https://github.com/MertBasar0/ceviz/actions/runs/34725991834)
Linux ve Windows işleri geçti. macOS'taki tek hata, dokuzuncu bağlantının 503
ile reddedilip sunucu tarafından kapatılmasından sonra testin ona da `shutdown`
uygulamasıydı (`ENOTCONN`). [Apple koşusu](https://github.com/MertBasar0/ceviz/actions/runs/34726003616)
aynı Python testinde durdu; Swift/Watch derleme adımlarına ulaşmadı. iPhone
ekran işi ayrı çalışıyor; tamamlandı sayılmıyor. `validation_only=true`;
TestFlight yükleme/dağıtımı yok.

Test, yalnız reddedilmiş soketi doğrudan kapatıp sahipliğinden çıkaracak şekilde
düzeltildi. Sekiz açık bağlantının kapanması, sekiz iznin geri dönmesi ve
sağlık yanıtı doğrulamaları aynen duruyor; bağımsız inceleme bunu doğruladı.
Düzeltme sonrası yerel geniş tekrar **224 test / 206 geçti / 18 atlandı,
84,603 saniye**, temizleme başarılı. Üretim kodu değişmedi. Yeni uzak doğrulama
henüz bu düzeltmeyi çalıştırmadı; macOS hatası gizlenmiş/geçmiş sayılmıyor.

### macOS düzeltmesi geçti; native oturum testinin bağlantı kurulumu

`f58693b7c59215d5e071fe98292497e31aa177a0` için
[helper doğrulaması](https://github.com/MertBasar0/ceviz/actions/runs/34726219694)
tamamen başarılı: Linux **224 / 214 geçti / 10 atlandı (61,346 sn)**,
macOS **224 / 214 geçti / 10 atlandı (97,466 sn)**, Windows yaşam-süresi
**10/10 (14,603 sn)**; iki Unix platformunda Node **3/3**. Eski Apple koşusu
yeni kaynak doğrulamasına yer açmak için durduruldu; eski iPhone işi geçti sayılmıyor.

[İkinci Apple koşusunda](https://github.com/MertBasar0/ceviz/actions/runs/34726219752)
Python/Node/Ruby ve Swift durum, Watch odak/kayıt, iki modelde taşıma,
telefon komutu, Conversation SQLite, **WatchDelivery SQLite** ve capability
paketleri geçti. `BackendTransportTests` ise ilk test isteği başlamadığı için
durdu. Global `URLProtocol.registerClass` yerine belirli oturumun
`configuration.protocolClasses` bağımlılığı kullanılmalı. Oturum sahibi,
başlangıç yapılandırmasının özel kopyasını alacak şekilde düzeltildi; test
gerçek URLSession/task/reset yollarını kendi yapılandırmasıyla kullanıyor.
Her kuşak hâlâ yeni ephemeral çerez/credential deposu alıyor; bir önceki
kuşağın özel verisi taşınmıyor. Native test bunu da denetliyor. Mevcut ve
drenajdaki isteklerin birlikte iptali ve normal tamamlanması ayrı kontroller.
Timeout ve iptal/drenaj doğrulamaları gevşetilmedi. Bu son düzeltmenin native
tekrarı aşağıda; üçlü uygulama build'i/ekran kanıtı tamamlanmış değil.

### Gerçek URLSession sıfırlama regresyonu ve kuyruk odağı

`12930dd47db7f1c21194af52506986177abce045` için
[Apple doğrulamasında](https://github.com/MertBasar0/ceviz/actions/runs/34726806021)
Python **224 / 214 geçti / 10 atlandı (98,945 sn)**, Node **3/3**, Ruby ve
önceki Swift paketleri geçti. Native oturum testi bu kez gerçek A ve B
isteklerini başlattı; fakat A tamamlanmaya bırakıldıktan sonraki tam sıfırlamada
iki isteğin birlikte iptali başarısız oldu. Bu test hatası düzelmiş sayılmıyor.
Oturum sahibi, zaten kapanmakta olan oturumları ikinci kez geçersizleştirmek
yerine `getAllTasks` ile kalan görevlerini doğrudan iptal edecek şekilde
düzeltildi. Mevcut oturum bir kez `invalidateAndCancel` alıyor. Aynı başarısız
A/B testi korunuyor; eski oturumda henüz başlatılmamış görevin de iptali eklendi.
Bu düzeltmenin native sonucu bekleniyor; süreler veya kapılar gevşetilmedi.

Bağımsız ek inceleme, çevrimdışıyken B kaydı kuyruktayken A'nın geç alındı
yanıtının B ekranını değiştirebildiğini gösterdi. Odak artık ilk ağ denemesinde
değil, kuyruk kaydı anında B'ye geçiyor. Yeni regresyon A yanıtını `begin(B)`
öncesinde veriyor; B'nin ilk gönderim hakkını ve A'nın yeniden gönderilmemesini
ayrıca koruyor. Bu son regresyon Windows'ta Swift olmadığı için henüz
çalıştırılmadı. Canlı servis, eşleştirme, ana dal ve TestFlight değişmedi.

`c3edf91dfaf60078c370e74d63c72074f0d9512f` için
[sonraki Apple koşusunda](https://github.com/MertBasar0/ceviz/actions/runs/34727343006)
yeni kuyruk-odağı regresyonu ve önceki Swift paketleri geçti. Native ağ testi
artık A/B iptalini, normal tamamlanmayı, kuşaklar arasında çerez/credential
ayrımını ve eski oturumdaki askıda görevin normal çalışmasını geçti; yeni
**hiç başlatılmamış görevin iptali** kontrolünde durdu. Bu, yerel görev
enumerasyonu üzerinden sıfırlamanın bu durumu kapatmadığını kanıtlıyor;
Darwin'in dahili görev listesinin içeriği ayrıca gözlemlenmedi.

Son düzeltmede tüm görevler tek oluşturma sınırında, aynı kilit altında
sahipleniliyor; tamamlanınca tüketici callback'inden önce kayıttan çıkıyor.
Tam sıfırlama bu görevleri iptal ediyor, her oturum yalnız bir kez kapanmaya
alınıyor. İkinci invalidation ve sonradan görev enumerasyonu kaldırıldı.
Hiç başlatılmamış görev testi değiştirilmedi; görev kaydı temizliği de
denetleniyor. Native tekrar henüz sonuçlanmadı. Hızlı Apple sözleşme kontrolü,
tam build ile aynı Swift komut listesini kullanacak; tam build/ekran kapısı
yerinde duruyor ve bu kontrol TestFlight yüklemiyor.

### Swift onarımı Apple ortamında doğrulandı

`3fd8195bb750896de2d813590b2c67eb55112f31` için
[hızlı Apple doğrulaması](https://github.com/MertBasar0/ceviz/actions/runs/34727749386)
başarılı. Xcode **26.6 / 17F113** üzerinde ortak listedeki **12 derleme/test
çifti** çalıştı: A/B ve hiç başlatılmamış görev iptali, graceful tamamlama,
görev/oturum temizliği, iptal-tamamlama yarışları, kayıt kimliği/restart
sınırları, kuyruk odağı ve iki modelde sınırlı Watch iş listesi geçti.
Bu sonuç simülatör ekranı veya gerçek cihaz ağ kesintisi testi değildir.

Aynı SHA için [tam Apple koşusu](https://github.com/MertBasar0/ceviz/actions/runs/34727830269)
`validation_only=true`, `candidate_for_device_check=false` ile tamamlandı;
Watch URL adımı nedeniyle genel sonucu başarısız.
Önceki başarısız koşuların kalan iPhone işleri yeni kaynak doğrulamasına yer
açmak için iptal edildi; iPhone başarısı sayılmıyor. Helper/runtime/test
kaynaklarının tamamı üç platformda geçen `f58693b` ile birebir aynı kaldı.
Ana dal, canlı WSL/servisler, eşleştirme ve TestFlight hâlâ değiştirilmedi.

Tam koşuda **iPhone + Watch + komplikasyon Release simülatör derlemesi geçti**.
Watch'ın 42 mm normal soğuk açılış görüntüsü elle incelendi: “Ready to listen”,
“Up to 15 s”, “Offline” ve mikrofon düğmesi görünür, düğme ekran içinde.
Bu yalnız yapılandırılmamış açılış/layout kanıtı; ses, ağ kurtarma veya gerçek
komplikasyon dokunuşu kanıtı değil.

Watch URL kapısı yine **115** ile durdu. Doğru kurulu şema/imza ve uygulama
sahnesi doğrulandı; `lsd` 00:35:16 UTC'de `ceviz-watch` için kayıtlı handler
bulamadığını bildirdi. Bu, geçmiş `34707041887` ile aynı native yönlendirme
sınırı; uygulamanın URL handler'ına ulaşılmadı. Simülatör boot sırasında exit0
ile “Data Migration Failed” da bildirdi; bu başarı sayılmadı, sonraki kurulum,
açılış ve görüntü ayrı kontrol edildi. Hatanın Darwin kök nedeni veya gerçek
WidgetKit dokunuşu sonucu kanıtlanmadı. **Watch capture/larger-text UI adımları
bu kapıdan sonra çalışmadı; geçilmiş sayılmıyor.** Ham artefakt ve görsel
inceleme notu özel yerel audit klasöründe korunuyor.

iPhone UI işi aynı kod SHA'sında **9/9 geçti (520,334 sn)**: kuyrukta çift
gönderimin önlenmesi, EN/TR liste/geçmiş, doğru oturuma gönderim, başarısız
işin başarı görünmemesi, eski hedefin reset sonrası reddi, belirsiz teslimde
yeniden göndermeme ve uygulama/helper yeniden açılışında bu korumanın sürmesi.
Son iki upload/distribution işi **skipped**; TestFlight build'i üretilmedi.
Görüntü arşivi seçmeli olarak alındı: 25 PNG, manifest, context ve build/test
günlükleri. **25/25 PNG tek tek açılıp manifest ile eşleştirildi**; görünür
uygulama alanında kesik kontrol, okunmaz metin, yanlış teslimat durumu veya
boş kare bulunmadı. Liste/geçmiş, EN/TR metinler, belirsiz teslimin restart
sonrasında korunması ve inceleme seçeneği doğrulandı. Normal QWERTY klavyeli
iki tam ekranda yazma alanı ve Gönder düğmesi klavyenin üstünde görünür.
Altı kasıtlı ölçüm kırpımı tam ekran kanıtı sayılmadı. Reset uyarısı karesinin
altındaki iOS kaydırarak yazma tanıtımı normal klavye kanıtı sayılmadı;
o karede uygulamanın reset uyarısı ve korunmuş taslağı görünür.
Bu kayıt güncellemesi yalnız belgedir; doğrulanan üretim kodu SHA'sı yukarıdaki
`3fd8195` olarak kaldı. Canlı kurulum ve gerçek cihaz denemesi için ayrı onay
gerekli; dış beta açılmadı.

### Onarım öncesi teşhis — tarihsel kayıt

Kullanıcı aşağıdaki teşhis sırasında onarımları sonraya bırakmıştı; o aşamada
yeni build, dağıtım, kod/ayar değişikliği veya komut tekrarı yapılmadı.

- **Yeni Watch gönderim olayı:** 13 Eylül 00:05'te WSL ve Ceviz kapanmış;
  01:03'teki kontrolde o gün için kabul edilmiş Watch POST'u veya yeni iş yoktu.
  Tanı komutunun WSL'yi açması servisi otomatik başlattı, yerel/Tailscale
  kontrolleri geçti. Ancak WSL tekrar kapandı; 01:06'daki Windows tarafından
  yapılan pasif kontrol `Ubuntu-E: Stopped` ve Ceviz adresinde HTTP 502 verdi.
  `Ceviz Backend Relay` Windows görevi çalışmıyor (`Ready`, son sonuç `1`);
  son çalışması 9 Eylül. Kesin çıkış nedeni henüz kanıtlanmadı. WSL ömür
  yönetimi ile LAN relay/Tailscale erişimini ayrı sorumluluklar olarak incele.
- **Watch teslim/kurtarma:** belirsiz teslimi görünür yap, aynı kimliği
  uzlaştırmadan yeniden gönderme; bağlantı geri dönüşü, FIFO ve uyanmayı sına.
  Kullanıcının 15 dakikalık ekranı için cihaz kanıtı hâlâ gerekli; backend'in
  kapalı olması tek başına yerel 30 saniyelik watchdog davranışını açıklamaz.
  Kullanıcı alt açıklamayı da doğruladı: kayıtlı bir isteğin süresi dolmuş,
  tekrar gönderilmemiş. Kaynakta bu mesaj, 15 dakikadan eski en az bir bekleyen
  Watch kaydının kuyruktan kaldırılmasıyla üretiliyor. Bu, 15 dakikalık kayıt
  saklama sınırıdır; tek ağ isteğinin zaman aşımı değil. Mesaj kayıt kimliğini
  belirtmez ve backend'de daha önce çalışmadığını tek başına kanıtlamaz.
- **HTTP alımı:** kabul edilmiş yarım başlık/gövdenin seri sunucuyu
  kilitlemesi izole testte doğrulandı; bu yeni olayın nedeni olduğu gösterilmedi.
- **Watch iş listesi:** tam raporlar yerine sınırlı özet veri, yeni işlerin
  önce gösterimi ve görünür yükleniyor/hata/yenileme durumları. Büyük gerçek
  yanıt ölçüldü; cihazda `payloadTooLarge` oluştuğu kanıtlanmadı.
- **Eşleştirme:** aynı bağlantıyı yenileme ile gerçek yeniden eşleştirmeyi ayır;
  mevcut sıfırlama bekleyen saat seslerini silebildiği için kurtarma önerisi değil.

Özel yerel ayrıntılı kanıt: dış çalışma alanındaki
`.artifacts/network-recovery-audit/incident-summary.md`. Aynı klasördeki QR
mevcut özel erişim anahtarını içerir; repoya veya duyuruya eklenmemelidir.

## Yardımcı servis güncellemesi — 12 Eylül yayımlandı

Yardımcı servis etiketi **ceviz-helper-v2026.9.12-beta.1** yayımlandı. Uygulama
**2026.6.5 (1789005793)** değişmiyor; yeni TestFlight paketi veya kişisel
Ceviz/Gateway güncellemesi yapılmıyor. Kod kaynağı `b117f2e` için
[Ubuntu/macOS kontrolleri](https://github.com/MertBasar0/ceviz/actions/runs/34706593707)
iki ortamda **180/180 Python + 3/3 Node** ile geçti. Son yayın kaynağı
**3bb022c17af737cb6f679442e221a14c6008fb18**, aynı tam SHA için
[son CI](https://github.com/MertBasar0/ceviz/actions/runs/34706866940) da yeşil.
Ana dal bu kaynağa ilerletildi; [helper beta yayını](https://github.com/MertBasar0/ceviz/releases/tag/ceviz-helper-v2026.9.12-beta.1)
ve etiketin tam commit karşılığı ayrı ayrı geri okundu.

### Son kullanıcı yolu ve yayın sonrası kanıt

- Gerçek HTTPS etiket bağlantısından indirilen güncelleyici, **varsayılan
  uzak repo ve varsayılan etiketle**, yerel `--source` geçişi olmadan çalıştı.
  Gerçek servis yenilendi; tüm korunan dosyalar/ortam/venv aynı kaldı,
  kimlik doğrulama, yetenekler, oturum ve geçmiş geçti. Aynı komut ikinci kez
  `UP TO DATE` verdi ve süreci yeniden başlatmadı; yeni Gateway gönderimi **0**.
- Genel etiket klonu tam **3bb022c** ve daha önce test edilen **c3404f1**
  backend/contract baytlarıyla eşleşti. Güncelleyici SHA-256
  `dc4b03531ecf6c92dfbf9cba755bcf70133e89ad006c55e170aad797ee62162e`;
  kurucu LF SHA-256
  `d58187c18c35f47714f775b8a217c442b99503803a5ff88dd83ac8f2438761b7`.
- [Kurulum sayfası](https://basarlabs.com.tr/ceviz/#install) sürüme sabitlenmiş
  **yeni kurulum** ile **mevcut backend güncelleme** bağlantısını ayırıyor.
  Site commit'i **6162201**, [Pages dağıtımı](https://github.com/MertBasar0/basarlabs-site/actions/runs/34707077310)
  başarılı; önce/sonra gerçek tarayıcı görüntüsü incelendi ve canlı sayfadaki
  bağlantıdan İngilizce güncelleme bölümüne geçiş doğrulandı.
- Mevcut **1789005793** build'inin yalnız EN/TR “What to Test” metinleri
  yeni helper sürümüne/rehbere yönlendirildi: **200 + 200**, birebir son geri
  okuma başarılı, bekleyen değişiklik **0**. Build **VALID**, iç/dış
  **IN_BETA_TESTING**, inceleme **APPROVED**, Mert/Beta üyeliği ve açık
  TestFlight bağlantısı kontroller boyunca korundu. Yeni build, yeniden
  dağıtım veya manuel bildirim yapılmadı.
- İzole geçici kullanıcı/servis/işaretli home temizlendi; kullanıcı, linger,
  süreçler ve test portunun kalmadığı doğrulandı. Yerel kanıt/loglar saklandı.
  Kampanyanın tamamında sahte CLI sınırında **29 RPC / yalnız 1 chat.send**
  gözlendi. Kişisel Ceviz ve OpenClaw kurulumları test hedefi olmadı.
- Ana dal geçişi ayrıca uygulama doğrulamasını yeniden tetikledi
  ([34707041887](https://github.com/MertBasar0/ceviz/actions/runs/34707041887)).
  Watch/shared işi **başarısız**: backend/Node/Ruby/Swift kontrolleri ve üç
  simülatör paketi derlendi, normal Watch açılışı geçti; kurulu URL scheme'i
  doğrulandığı halde `simctl openurl ceviz-watch://capture` **115 /
  LSApplicationWorkspaceErrorDomain** döndürdü. Kaynak tanı JSON'u ve gerçek
  42 mm açılış görüntüsü incelendi; hazır başlığı, süre ve mikrofon görünür.
  Katı varsayılan kapı hatayı fatal tuttu; kayıt/büyük yazı adımına ulaşılmadı.
  13 Eylül salt okunur son kontrolde iPhone işi **başarılı** doğrulandı
  (iş `103588858831`, bitiş 12 Eylül 17:22:56 UTC). Bu eski SHA kanıtı yeni
  onarım kaynaklarının native kanıtı değildir. Push olayında Apple imzalama/yükleme yapılamaz;
  mevcut build dağıtım işi de atlandı.
- **Açık takip — Watch simülatör URL açılışı:** önceki native doğrulamalarda da
  kaydedilen 115 hâlâ çözülmüş değil; yeni koşu tüm native kontrollerin geçtiği
  şeklinde sunulamaz. `c3404f1` → `3bb022c` uygulama/backend/contract ve native
  test kaynak farkı boş. Bu kanıt gerçek WidgetKit dokunuşunu sınamıyor veya
  yeni uygulama regresyonunu göstermiyor. Helper güncellemesinin ayrı başarılı
  kanıtları yukarıda; yeni native yayın öncesinde bu takip yeniden ele alınmalı.
  Kontrol gevşetilmedi, tekrar koşuyla gizlenmedi ve yeni TestFlight paketi yok.

### Düzeltme ve test kapsamı

- Değişiklik sahipliği: kurucu artık yalnız yeni kurulumu, güncelleyici mevcut
  servisin kod yaşam döngüsünü yönetiyor. Eski yeniden-kurulum/restart fallback'i
  ve geniş `pkill` yolu kaldırıldı. İlk kod paketinde üretim betikleri/manifest
  net **+557 satır**, yerel artifact ignore **+2**, CI **+97**, testler **+1629**.
  Artış yeni, bağımlılıksız tam-kopya doğrulama/atomik etkinleştirme/kod-only
  kurtarma sınırına ait; uygulama veya backend çalışma kodunda değişiklik yok.
- Güncellemenin sahibi `deploy/update.py`: Linux/WSL kalıcı systemd kullanıcı
  servisi, açık bakım onayı, boşta ve teslimi belirsiz iş yokluğu kontrolü.
  Tam backend/contract kopyası doğrulanıyor; tek giriş dosyası atomik olarak
  değişiyor. Geri dönüş yalnız kodu kapsıyor; iş/SQLite kayıtları silinmiyor
  veya eski bir kopyaya sarılmıyor.
- Eski kurucunun tekrar çalıştırılması gerçek izole serviste özel ajan/dil
  ayarlarını değiştirdi ve çalışan süreci yenilemedi. Yeni kurucu mevcut
  servis/token (bozuk sembolik bağlantı dahil) bulursa değişiklik yapmadan duruyor.
  Yeni kurulum Python 3.11+ kontrolü yapıyor ve OpenClaw için gerekli shell
  PATH'ini systemd servisine doğru tırnaklayarak aktarıyor.
- Son kaynak için Windows tam Python paketi **180 test, 162 geçti / 18 platform
  atlandı**; Linux odaklı kurucu/güncelleme paketi **27/27**, bildirim sınırı
  Node paketi **3/3** geçti. Bağımsız kaynak/test incelemesinin bulguları aynı
  kırmızıdan yeşile testlerle kapatıldı; hazır autoreview/test-audit araçları
  bu ortamda bulunmadığından bağımsız elle inceleme kullanıldı.
- Gerçek WSL/systemd, ayrı geçici kullanıcı ve sahte OpenClaw CLI sınırında:
  eski `040d1df` kurulumu → güncel yardımcı servis; kayıtları olan ve henüz
  konuşma SQLite dosyası olmayan iki kohort; özel unit/drop-in/ortam, token,
  bağımlılıklar ve geçmiş korunması; 401/200 erişim; oturum/geçmiş; bakım onayı,
  yanlış kurulum ve aktif/belirsiz teslimde durma; ikinci güncellemede yeniden
  başlatmama doğrulandı. Gerçek servis yeniden başlatılıp aynı gönderim kimliği
  tekrarlandığında sahte Gateway sınırına yalnız bir `chat.send` ulaştı.
- Bilerek bozuk başlangıç gerçek süreçte hata verdi ve otomatik eski-kod
  kurtarma geçti. Güncelleyici etkinleştirme sonrasında gerçekten SIGKILL ile
  kesildi; bekleyen kayıt korundu, yeni güncelleme reddedildi ve `--recover`
  ayar/veriyi değiştirmeden önceki kodu geri getirdi.
- Aynı izole kullanıcı/işletim sisteminde ikinci, yeni venv/token ile sıfır
  uygulama kurulumu geçti. Boşluk, yüzde ve tırnak içeren CLI PATH'i gerçek
  serviste ve yeniden başlatma sonrasında korundu. Bu, ikinci temiz işletim
  sistemi veya gerçek telefon/mikrofon/Whisper model kalitesi testi değildir.
- Sınırlar: otomatik güncelleme macOS/nohup/özel başlatıcıyı veya bağımlılık
  değişikliğini kapsamıyor. Yeni kurucuda özel karakterli kurulum dizinlerinin
  systemd yolu ayrı takip işi; rehber normal Linux home yolunu kullanıyor.
  Eski checkout'un deploy betikleri/Git kimliği değiştirilmediği için yeni
  sürümlerde yayımlanan güncelleyici indirilir; eski kurucu tekrar çalıştırılmaz.

Yayın ve son kullanıcı yolu: [yardımcı servis notları](docs/release-notes-helper-2026.9.12-beta.1.md),
[İngilizce kurulum/güncelleme/kurtarma rehberi](deploy/README.md#update-existing-installation).

## Güncel dış Beta — güvenli devam ve telefon konuşmaları

**2026.6.5 (1789005793)** dış **Beta** ve iç **Mert** gruplarında hazır.
Apple yüklemesi **COMPLETE**, build **VALID**, iç ve dış durum
**IN_BETA_TESTING**, beta incelemesi **APPROVED**. Mevcut
[TestFlight bağlantısı](https://testflight.apple.com/join/nEdn2Np2) korundu.

Kullanıcı 11 Eylül'de testlerini tamamladığını, bir sorun görmediğini bildirdi
ve dış Beta dağıtımını açıkça onayladı. Bu, kullanıcı kabul bildirimidir;
her ayrıntılı cihaz/yeniden başlatma senaryosu bağımsız gözlenmiş sayılmıyor.
Test edilen aynı imzalı paket dağıtıldı; yeniden derleme yapılmadı.

### 11 Eylül dış dağıtım kanıtı

- Tam kaynak `c3404f14e9b23b61cf8addcdcd24a4638cb02603`; Apple build kimliği
  `24e7721c-4b81-4ea9-acc2-122f5d4c7d9c`. Sürüm **2026.6.5**, build
  **1789005793**, **APP_STORE_ELIGIBLE**, süresi dolmamış. Ayrı yükleme
  kaydı **COMPLETE**; hata, uyarı ve bilgi listeleri boş.
- Yalnız bu build'in EN/TR “What to Test” metinleri dış beta için güncellendi
  (**200 + 200**) ve birebir geri okundu. Yeni Konuşmalar/devam özelliklerinin
  eşleşen yardımcı servis gerektirdiği, mevcut ana daldaki serviste bulunmadığı
  ve mevcut kurulum güncellemesi için yardım istenmesi gerektiği açıklandı.
- Mevcut dış **Beta** grubuna tek build ekleme **204**, beta inceleme başvurusu
  **201** döndü. Başvuru sonrası ayrı GET'ler **APPROVED**, dış
  **IN_BETA_TESTING** ve doğru Beta üyeliğini doğruladı. Yalnız grup üyeliği
  dağıtım başarısı sayılmadı. Sonuç **11 Eylül 03:53 Türkiye saati** civarında
  gözlendi; Apple'ın `submittedDate` alanı boş, bu alandan zaman türetilmedi.
- Otomatik TestFlight bildirimi açık bırakıldı; ayrıca manuel bildirim
  gönderilmedi. İç Mert erişimi, önceki dış build **1788715054**, grup ayarları
  ve açık bağlantı korundu. Test kullanıcıları, genel App Store metadata'sı,
  Gateway/Ceviz servisleri veya bağlantı ayarları değiştirilmedi. `main`'e
  birleştirme, GitHub release/tag ve sosyal duyuru yapılmadı.
- **11 Eylül anındaki kurulum takibi — 12 Eylül helper yayınıyla kapandı:**
  O gün README ve ürün sayfasındaki standart
  kurulum hâlâ `main` dalını klonluyor; yeni yardımcı servis yalnız açık
  `codex/phone-conversations` dalında, test edilen kaynak **c3404f1**.
  Eski yardımcı serviste telefon açık bir güncelleme gereksinimi gösteriyor.
  Yapılandırma/iş/SQLite kayıtlarını koruyan, boşta yalnız Ceviz'i yeniden
  başlatan ve yetenekleri doğrulayan standart güncelleme yönergesi hazırlanmalı;
  yalnız kurulum betiğini yeniden çalıştırmak güvenli güncelleme kanıtı değil.
  Bu dağıtım sırasında ana dala geçiş veya kurulum betiği onarımı yapılmadı.

## Güvenli devam ve konuşmalar — geliştirme ve iç test geçmişi

10 Eylül'deki ilk dağıtımda **2026.6.5 (1789005793)** yalnız **Mert** iç grubunda hazırdı. Apple yüklemesi
**COMPLETE**, build **VALID**, iç durum **IN_BETA_TESTING**; EN/TR test notları
birebir geri okunarak doğrulandı. Ceviz yardımcı servisi de onayla güncellendi.
O aşamada yeni build dış **Beta** grubuna eklenmedi; dış sürüm **1788715054** korundu.
Fiziksel cihaz kabulü kullanıcı testine bırakıldı; 11 Eylül kabulü ve dış dağıtımı yukarıda.

- Devam mesajı ile öneri onayı ayrıldı; açık iş/eylem kimliği kullanılıyor.
  Saat kayıt başlangıcında seçili bağlamı sabitliyor; son gelen ilgisiz işe
  otomatik bağlanma kaldırıldı. Eski yardımcı servis/telefon için yetenek
  kontrolü var; destek yoksa metin veya ses korunuyor.
- Telefonda gerçek OpenClaw konuşmaları, asistan filtresi, arama, eski kayıtlar,
  geçmiş ve açık hedefli gönderim eklendi. Ceviz iş zincirinden ayrı; saat hedefini
  değiştirmiyor. Ayrıntı ve sınırlar: [konuşmalar](docs/conversations.md).
- Yeni katmanla canlı Gateway'de yalnız okuma doğrulandı: varsayılan son-yedi-gün
  listesinde 6 oturum, 4 yapılandırılmış asistan; iki asistanın geçmişinde ilk
  sayfalar 51/49 okunabilir mesaj ve gönderim için oturum/mesaj-dalı bilgisi var.
  Bu kontrolde canlı komut veya model çağrısı yapılmadı.
- İlk WSL test kabuğunun PATH'i yanlışlıkla Windows npm CLI'ını seçti ve zaman
  aşımına uğradı. Çalışan kurulumun Linux OCM CLI yoluyla aynı kontrol geçti;
  üretim yapılandırması veya zaman aşımı büyütülmedi.
- İlk yerel pakette 139 Python testi ve 3 bildirim sınırı testi geçti. Konuşma gönderiminin
  ekranlar arasında korunması, kontrol metni normalizasyonu, terminal durumun
  gerilememesi ve izole test temizliği bağımsız son incelemeden geçti.
  Yalnız geliştirme dalına commit/push ve `validation_only` çalışma izniyle
  Apple derlemesi ve otomatik ekran kontrolleri de geçti. O aşamadaki görsel
  incelemede bulunan telefon kusurları sonraki onarımlarla giderildi;
  son adayın görsel kabul ve iç dağıtım kanıtı aşağıda.
- 10 Eylül'de kullanıcı telefon ve Ceviz yardımcı servisinde yalnız gönderim/
  hedef kimliği ve durum tutan yerel SQLite kayıtlarını açıkça onayladı.
  Uygulandı; konuşma metni/erişim anahtarı kaydedilmiyor ve OpenClaw
  veritabanına dokunulmuyor. Güncel native sonuç ve kalan işler aşağıda.
- Bu aşamada yeni TestFlight build'i yalnız iç test için onaylandı; dış Beta açılmadı.
  Ceviz yardımcı servisi ayrıca alınan yeniden başlatma onayıyla güncellendi;
  canlı doğrulama aşağıda. Gateway ayarları, `main`, mevcut dış TestFlight dağıtımı
  ve sosyal yayınlar değiştirilmedi. Özel `autoreview` / `test-audit` becerileri bu oturumda yok;
  bağımsız ajan incelemesi ve kaynak/sözleşme/regresyon kontrolleri kullanılıyor.

### İlk Apple doğrulaması ve taşınabilirlik düzeltmesi

- Geliştirme dalı `codex/phone-conversations`; ilk commit `21c8a5f`.
  [İlk doğrulama](https://github.com/MertBasar0/ceviz/actions/runs/34297909715)
  Python aşamasında durdu: izole telefon servisi hazır olamadı; aşırı büyük
  istek gövdesinde bağlantı sıfırlanması görüldü. Native testler çalışmadı;
  imza/anahtar/TestFlight ve dağıtım adımları **skipped**.
- Konuşma HTTP yanıtlarına açık bayt uzunluğu eklendi. Reddedilen gövdenin
  tüketimi hem bayt hem toplam süreyle sınırlandı; eksik/yavaş veri gönderimi
  sonrasında servisin başka isteği karşılayabildiği gerçek soketle test edildi.
- Yalnız izole test servisi için ters DNS gereksinimi kaldırıldı. DNS yokluğu
  regresyonu önce üretildi; başlangıç aşaması ve takılma günlüğü eklendi.
  İlk macOS gecikmesinin kesin nedeni eski günlükten kanıtlanamadı; yeniden
  doğrulama gerekli. 10/15 saniyelik test-hazırlık sınırları büyütülmedi.
- İlk özellik commit'i: üretim kodu **+1.554 / -110**, testler **+1.489**;
  doğrulama tanımları **+52**, dokümantasyon **+128 / -1** satır. Bu ölçüm
  sonraki taşınabilirlik düzeltmesini içermez.

### İkinci Apple doğrulaması — testler geçti, görsel düzeltme kaldı

- Kod commit'i `110dca837bb1650d0f8f971715efdfec14d988c4`;
  [yalnız doğrulama çalışması](https://github.com/MertBasar0/ceviz/actions/runs/34298580583).
  Python/sözleşme, bildirim, Ruby, sekiz Swift regresyon programı ve
  iPhone/Watch/widget simülatör derlemesi geçti. `validation_only=true`;
  TestFlight dağıtımı istenmedi.
- Xcode **26.6**, iOS/watchOS SDK **26.5**. 42 mm Watch normal açılış görüntüsü
  incelendi: hazır başlığı, 15 saniye bilgisi ve mikrofon düğmesi görünür.
  Üç uygulama paketinin yerel ad-hoc kimlik/imza kontrolü geçti.
- Genel simülatör URL yoklaması yine **115** döndü; kaynak artefaktında
  `capture_url.status=failed` ve `widget_tap.status=not_tested` korunuyor.
  Bu kadran dokunuşu başarısı veya dağıtım onayı değildir.
- Çalışma **9 Eylül 05:04 Türkiye saati** civarında başarıyla tamamlandı;
  önceki oturumda sonuç takibi ve son görsel inceleme yarım kalmıştı.
  Sertifika içe aktarma, ASC anahtarı, TestFlight yüklemesi ve dağıtım **skipped**.
- **7 Watch XCTest / 5 koşu**, 40 mm ve 49 mm, sıfır hata; **6 telefon XCTest**,
  sıfır hata. 10 Eylül'de 36 Watch görüntüsü bağımsız incelendi; 10 telefon
  görüntüsü ana incelemede açıldı. Watch kontrolleri görünür; 40 mm en büyük
  yazıda Türkçe Gönder düğmesinin iç boşluğu dar. İki cihazda yazı büyütme ve
  özgün ayara dönüş geometrisi doğrulandı.
- Gerçek kayıt dosyaları: manuel **9,788 sn / 25.196 bayt**, otomatik
  **14,908 sn / 25.516 bayt**, mono 16 kHz. Watch bitiş ekranındaki Deploy #8841
  sonucu eşleşmemiş telefonun demo içeriğidir; gerçek Gateway komut yürütme
  kanıtı değildir. Telefon senaryoları da izole Gateway test verisiyle çalıştı.
- **Görsel kabul tamamlanmış sayılmıyor:** telefon konuşma detayındaki sistem
  başlığı/durum çubuğu ve boş mesaj alanı yazısı koyu zeminde çok düşük
  kontrastlı. Liste ekranları EN/TR okunabilir; detayın açık/koyu görünüm
  tutarlılığı düzeltilip yeni ekran kanıtı alınmalı. Otomatik testlerin geçmesi
  bu kusuru kapatmıyor. 10 Eylül'deki yeni düzeltme kök uygulama görünümünü
  mevcut sabit koyu tasarımla eşledi; eski görüntü yeni başlık kontrast
  hesabında 1,0 ile 4,5 eşiğinin altında kaldı. Yeni native koşu bekleniyor.
- Kalıcılık onayı alındı. Yeni yardımcı servis testlerinde aynı kimliğin
  yeniden gönderilmesi ve terminal durumun restart'ta kaybolması önce
  üretildi, sonra düzeltmeyle geçti. Windows **146** Python testi, Linux
  **31** oturum + **5** fixture testi geçti. Telefonun disk/restart ve
  kullanıcı kontrollü belirsizlikten çıkış kanıtı henüz Apple'da çalışmadı.
- Kalıcı helper kaydının 512 kimlik sınırı görünür hata ile korunuyor;
  kimlik silerek yeniden gönderim açılmıyor. Sürdürülebilir kapasite yönetimi
  ayrı takip maddesi. Fiziksel cihaz kabulü de açık.
- Yeni kod için yerel tam test yeniden çalıştırıldı: **146 Python / 3 Node**
  testi geçti; iş akışı, installer ve Doctor kabuk sözdizimi temiz. Dokuz
  telefon ekranı testi yazıldı; Apple'da çalışmadan geçmiş sayılmıyor.
  Saat ve telefon kanıtları bağımsız paralel işlere ayrıldı; aynı kod
  kimliğindeki iki iş de başarılı olmadıkça imza/yükleme işi çalışamaz.

### Üçüncü Apple doğrulaması — kalıcılık geçti, ekran kabulü açık

- Kod `7aa54a6aeee393a4b3f079831927c378fd40f78e`;
  [doğrulama çalışması](https://github.com/MertBasar0/ceviz/actions/runs/34417538624)
  başarısız. İmza/yükleme ve dış dağıtım **skipped**; yeni TestFlight build'i yok.
- Python/sözleşme, bildirim, Ruby, sekiz Swift programı ve üç simülatör paketi
  geçti. Gerçek SQLite açma/kilitleme/bozuk kayıt regresyonları Apple'da çalıştı.
  Telefonun dokuz ekran testinden sekizi geçti; uygulama ve yardımcı servis
  yeniden açıldıktan sonra aynı gönderimin korunması ve yeniden gönderilmemesi
  geçti. Açık kullanıcı incelemesi senaryosu iptal düğmesinde durdu.
- Ana incelemede 22 telefon PNG'si açıldı: sistem başlığı, durum çubuğu ve
  klavye düzeldi; boş mesaj alanı hâlâ soluk. İki sistem görünümünde gerçek
  alanın ölçülen kontrastı **2,41:1**, hedef **4,5:1**. Yeni düzeltme mevcut
  `CVZ.textSub` rengini doğrudan alanın yönlendirme yazısına uyguluyor;
  test, odak/caret veya yazılmış metin olmadan bu alanı da ölçüyor.
- Aynı iPhone 17 Pro / iOS 26.5 görüntüsünde `confirmationDialog` popover'ı
  yalnız onay seçeneğini gösterdi; `Cancel` gerçekten yoktu. Kullanıcının
  kararını açık tutmak için dondurulmuş gönderim verisini alan `alert` ve
  görünür iptal seçeneği kullanılıyor. EN/TR iptal metni eklendi; taslağı ve
  takip kilidini koruyan iptal testi gevşetilmedi. Yeni native sonuç bekleniyor.
- Watch 40 mm normal EN/TR kayıt-silme ve büyük yazı/geri dönüş kontrolleri
  geçti. Ardından manuel bitiş senaryosunda görünür, etkin mikrofon düğmesine
  tek dokunuş kaydı başlatmadı: ekran hazır kaldı; ilk `primary_action` olayı
  bile yok. Koordinat **(81,149)** düğmenin içinde ve önceki başarılı
  dokunuşlarla aynı. Kayıt süresi/boyutu hatası kanıtlanmadı; 9/15 saniye ve
  49 mm aşamaları bu koşuda geçmedi. Kök neden hâlâ inceleniyor; kör yeniden
  dokunma, daha uzun bekleme veya test atlama eklenmedi.
- Kalıcılık/görünüm commit'inin üretim kodu **+430 / -84**, testleri
  **+554 / -47**, dokümanları **+86 / -15**, CI **+58 / -2** satırdır.
  Üretim büyümesi onaylanan yerel gönderim sahipliği, disk hatasında güvenli
  duruş ve açık inceleme yaşam döngüsünü kapsar; eski genel durum güncelleme
  yolu kaldırıldı. Yeni UI düzeltmesinin üretim etkisi çeviriler dahil **+1**
  net satır; yeniden doğrulama öncesi altı yerelleştirme testi geçti.

### Dördüncü Apple doğrulaması — telefon geçti, ortak HTTP yanıtı düzeltildi

- Kod `5dc2573ed22b04585d3b61051ec9609dabd1c89d`;
  [doğrulama çalışması](https://github.com/MertBasar0/ceviz/actions/runs/34419875188).
  Telefonun **9 XCTest'i sıfır hatayla** geçti (324,042 sn). Ana incelemede
  yeni iptal/onay penceresi, yeniden açılış ve açık/koyu sistemde boş mesaj
  alanı/klavye görüntüleri açıldı: iki karar düğmesi görünür, yazılar okunabilir.
  İptal taslağı/kilidi korudu; açık inceleme sonrası yeniden açılış eski mesajı
  göndermedi, yalnız yeni yazılan mesaj yeni kimlikle aynı konuşmaya gitti.
  Bağımsız incelemede 25 PNG'nin tamamı açıldı. İki görünümde mesaj alanının
  aynı piksel ölçümü **2,41:1 → 8,02:1**; yeni engelleyici görsel bulgu yok.
  Ortak Python işi başarısız olduğundan imza/yükleme **skipped**; yeni build yok.
- Yetkisiz POST gövdesi okunmadan verilen 401 yanıtında bayt uzunluğu yoktu.
  macOS istemcisi yanıt sonunu bağlantının kapanmasından beklerken TCP reset
  aldı. Tek ortak yetkilendirme kapısı artık tam JSON uzunluğunu ve bağlantı
  kapanışını bildiriyor; erişim kontrolü, gövde okumadan ret sırası ve bütün
  API girişleri korunuyor. İstemcide hata yutma/yeniden deneme eklenmedi.
- Gerçek soket regresyonu düzeltmeden önce başarısız üretildi; tam küçük/büyük
  gövde ile hiç veya yalnız bir baytı gönderilen büyük gövdeye tam 401 dönmesi
  ve ardından başka isteğin karşılanması doğrulandı. 14 API yolu/yönteminde
  yetkisiz isteğin Gateway, STT, bildirim kaydı veya iş yazımı başlatmadığı test edildi.
- Son kaynakla Windows **147 Python / 3 Node**, Linux **32 oturum** testi
  geçti; bağımsız taze incelemede engelleyici bulgu yok. Üretim değişikliği
  **+7 / -1**: yanıtı üreten mevcut sahibinde eksik HTTP çerçevelemesi eklendi;
  yeni katman veya seçenek yok. Test değişikliği **+46 / -11** satır.
  macOS'ta bu düzeltmenin ve tüm Watch kontrollerinin yeniden doğrulanması açık.
- Saatin önceki başarısız dokunuşu için test çalıştırıcısına hata anında
  sınırlı native olay özeti eklendi; ham mesajlar/anahtarlar yayımlanmıyor.
  Gerçek test hatası, dokunuş ve süre kontrolleri değişmedi. Tanılama eki
  üretim koduna **0**, test desteğine **+80**, testlere **+119** satır ekler.
  Son kaynak sabitlendikten sonra **152 Python testi** geçti (21,297 sn);
  bağımsız inceleme 50 saat testini de çalıştırdı. Native tanılama komutları
  henüz yürütülmüş sayılmıyor; yalnız olası test hatasında çağrılacak.
- Yerel test takibi: kaynak sabitlenmeden başlayan ara koşuda test beklentisi
  düzenlenirken eski beklenti çalıştı; ayrıca HTTP durum satırından önce bir
  Windows **10053** bağlantı kesilmesi görüldü. İkinci hatanın nedeni eldeki
  kırpılmış çıktıdan belirlenemedi; aşağıdaki ayrı araştırmada yeniden üretildi.
  Sonraki yeşil koşu tek başına açıklama sayılmadı.

### Ortak bağlantı kapanışı — asıl taşıma onarımı

- Sabit `cfa4b01` kaynakla sınırlı tekrarlı araştırma, üçüncü döngüde iki
  baytlık yetkisiz POST'ta **HTTP durum satırından önce Windows 10053** üretti.
  Ayrıca commit'ten yüklenen gerçek eski handler, gecikmeli iki baytlık yeni
  regresyonda başarısız oldu. Tam izler ve araştırma kodu yerel artefaktlarda.
- Yanıtın uzunluğunu belirtmek tek başına yeterli değildi: okunmamış istek
  verisiyle kapanış, yanıt başlıklarının alınmasını bile kesebiliyordu.
  Mevcut reddedilen-gövde tüketimi tek `http_transport.py` sahibine taşındı;
  hem ortak yetkilendirme reddi hem konuşmanın aşırı büyük isteği bunu kullanıyor.
  Sınır **96.001 bayt / toplam 0,5 sn**, her okumada yenilenmiyor. Veri
  ayrıştırılmıyor/yazılmıyor; sonrasında bağlantı kapatılıyor. Sınırsız veya
  yanlış bildirilmiş yüklerde her koşulda yanıt teslimi garantisi verilmez.
- Aynı tekrarlı kontrol yeni kaynakta **80 döngü / 1.280 gerçek HTTP isteği**
  geçti: 1.120 yetkisiz, 80 aşırı büyük, 80 sonraki istek. İstemci yeniden
  denemesi veya hata yutma yok. Son kaynakla **153 Python / 3 Node** geçti;
  Windows/Linux **33 oturum** testi ve taze bağımsız inceleme de geçti.
- Üretim farkı **+37 / -22, net +15**; eski gövde döngüsü silindi ve iki
  mevcut ret noktasına tek taşıma sahibi getirildi. Test farkı **+59 / -31**.
  O aşamada canlı servis değişmedi; sonraki onaylı dağıtım dört dosyayı kapsadı.
  `cfa4b01` Apple koşusu son onarımı içermediği için dağıtım adayı değil;
  aşağıdaki başarılı saat kanıtını sağladı. Son onarımla doğrulama da tamamlandı.

### Beşinci Apple doğrulaması — ekran ve kayıt kanıtı kabul edildi

- `cfa4b01134a9d67c2cf6018d8c2281d6fdede63f` için
  [doğrulama](https://github.com/MertBasar0/ceviz/actions/runs/34421523936)
  başarılı: 152 Python, bildirim/Ruby/Swift ve üç simülatör paketi; telefonun
  dokuz senaryolu işi ve **7 Watch XCTest / 5 koşu** geçti. İmza/yükleme yapılmadı.
- 40/49 mm normal ve büyük yazıda 58 PNG bağımsız incelemede açıldı:
  26 Ceviz, 32 Settings görüntüsü. EN/TR kayıt ve silme kontrolleri görünür;
  iki cihazda dokuzar ayar/geometri geri-dönüş kontrolü geçti. Kaynak piksellerde
  düğme çerçevesi kesilmiyor; önizlemedeki kesilme şüphesi geri çekildi.
- Ana incelemede manuel/otomatik kayıt akışının altı PNG'si ve kayıt günlüğü
  incelendi. Gerçek dosyalar **10,172 sn / 25.220 bayt** ve
  **14,908 sn / 25.516 bayt**, mono 16 kHz. İki sonuç da saat üzerinde
  **Queued / Waiting for iPhone**: kaydın korunması kanıtı, Gateway teslimi değil.
  Önceki tek dokunuş sorunu tekrarlanmadı; üretimde varsayımsal dokunuş değişikliği
  veya testte tekrar deneme eklenmedi. Hata tanılaması bu başarılı koşuda çalışmadı.
- Son onarımı içeren `c3404f14e9b23b61cf8addcdcd24a4638cb02603` için
  [iç TestFlight çalışması](https://github.com/MertBasar0/ceviz/actions/runs/34424690769)
  10 Eylül 04:14 Türkiye saati civarı başlatıldı ve başarılı tamamlandı.
  Aynı SHA'nın telefon ve saat işleri yeniden geçtikten sonra imza/yükleme
  çalıştı. Yeni adayın dış Beta dağıtımı yapılmadı; Apple kabulü aşağıda.
  Yardımcı servis ayrıca alınan onayla aşağıdaki şekilde güncellendi.
- Son `c3404f1` adayının iPhone işi geçti: **9 test, 0 hata, 475,841 sn**,
  iPhone 17 Pro / iOS 26.5. Ana incelemede sekiz kritik PNG, bağımsız
  incelemede **25 PNG'nin tamamı** açıldı; iptal/onay, boş alan, klavye ve
  yeniden açılış görünümleri kabul edildi. Yerel test servisine ait 17 durum
  kaydı, belirsiz teslimde aynı kimliğin tek gönderim olarak kaldığını ve
  yalnız açık inceleme sonrası yeni metnin ikinci kimlikle gönderildiğini
  doğruladı. Boş alan kontrastı kaynak piksellerde yine **8,02:1**.
  Son adayın saat açılış PNG'si de incelendi; normal açılış geçti. Genel URL
  yoklaması 115 / gerçek kadran dokunuşu doğrulanmamış durumu korunuyor.

### Son aday — imza, Apple kabulü ve iç dağıtım tamamlandı

- Tam `c3404f1` kaynakla Apple'da **153 Python** testi (55,308 sn), bildirim,
  Ruby, sekiz Swift programı, üç simülatör paketi ve **7 Watch XCTest / 5 koşu**
  geçti. Son 40/49 mm normal/büyük yazı **58 PNG** bağımsız kabulden geçti;
  iki cihazda dokuzar geri-dönüş kontrolü doğru. Ana incelemede altı kayıt PNG'si
  ve ses günlüğü açıldı: manuel **10,364 sn / 25.232 bayt**, otomatik
  **14,908 sn / 25.516 bayt**, mono 16 kHz; ikisi de saatte korunmuş **Queued**.
  Bu, canlı Gateway'e teslim veya fiziksel mikrofon kalitesi kanıtı değildir.
- İmzalı **2026.6.5 (1789005793)**, 10 Eylül **05:06:41 Türkiye saati**
  Apple'a yüklendi. Build kimliği `24e7721c-4b81-4ea9-acc2-122f5d4c7d9c`.
  Ayrı yükleme kaydı **COMPLETE**, hata/uyarı listeleri boş; build **VALID**,
  iç durum **IN_BETA_TESTING**, atanmış tek grup **Mert** olarak geri okundu.
  Dış durum **READY_FOR_BETA_SUBMISSION**; yeni build **Beta** grubunda yok.
- İndirilmiş IPA'nın SHA-256 değeri
  `ff312e30eb2a01fe983eea63d62e0b5e91140a260903a538e18e2be4b7cc8390`.
  Telefon, Watch ve widget kimlikleri, sürüm/build eşitliği ve üç profil/imza
  kaynağı kontrol edildi. Minimum iOS 16 / watchOS 9 ve WidgetKit uzantı
  kimliği doğru. Yerel ZIP denetimi kriptografik imza doğrulaması değildir;
  imzalama Apple ortamında, yükleme kabulü Apple servisinde doğrulandı.
- Yalnız bu yeni build'in EN/TR test notlarına iki güncelleme yapıldı;
  ayrı salt-okunur denetim iki metni birebir eşledi ve kalan yazma sayısı **0**.
  Grup ayarı değişikliği, dış inceleme başvurusu, genel App Store metadata değişikliği,
  GitHub release/tag, `main` değişikliği veya duyuru yapılmadı.
- İç cihaz testi: iPhone ve Watch'u birlikte güncelle; Konuşmalar'da hedef seç,
  geçmişi aç ve metin gönder; belirsiz teslim/yeniden açılış takibini kontrol et.
  Saatte sonuca devam etme ile iPhone'da öneri onayını ayrı dene; kadran düğmesini
  gerçek cihazda kontrol et. Dış Beta ancak bu kabul ve yeni onaydan sonra açılmalı.

### Yerel Ceviz yardımcı servisi — onaylı güncelleme tamamlandı

- Kullanıcı bakım boyunca yeni komut göndermeyeceğini ve yalnız Ceviz
  yardımcı servisinin kısa süre yeniden başlatılmasını açıkça onayladı.
  Hemen durdurma öncesinde **50 iş: 44 tamamlandı, 6 başarısız, 0 aktif**
  doğrulandı. Kontrol tek başına yeni isteği engellemediği için kullanıcı
  tarafından sağlanan bu bakım aralığı kullanıldı.
- Eski iki kod dosyası ayrı, üzerine yazılmayan yerel geri dönüş kopyasına
  alındı. Tam `c3404f1` kaynak kimliğine sabitlenmiş **dört** dosya kuruldu;
  her dosya kopyalama öncesi/sonrası hash ile doğrulandı. Kod geri alma yolu
  iş kayıtlarını veya SQLite verisini geri sarmıyor/silmiyor; çalıştırılmadı.
- Yeniden başlatma ve salt-okunur kabul kontrolleri **3,013 sn** sürdü.
  Eski iş verisi baytları, yapılandırma/ortam, Python ortamı ve Gateway'in
  süreç/başlangıç kimliği değişmedi. Kimlik doğrulamasız API **401**, kök sağlık
  rotası **200**; eski rapor durumu ve yeni üç yetenek doğrulandı.
- Canlı liste **6 konuşma / 4 asistan** döndürdü; seçilen konuşmanın geçmişi
  aynı kimlikle okundu. Bu kontrolde komut/model çağrısı gönderilmedi.
  Kullanıcıya bakımın bittiği ve yeniden Ceviz komutu gönderebileceği bildirildi.
- Bağımsız salt-okunur son kontrolde dört canlı dosya, servis kimliği,
  yedekler ve korunan Gateway/ayar parmak izleri tekrar eşleşti. Yardımcı
  SQLite dosyası ilgili ilk işlemde oluşturuluyor; kontrolde henüz yoktu.
  Bu yüzden kalıcılığın canlı kullanıcı gönderimiyle doğrulandığı iddia edilmiyor;
  yeniden açılış kanıtı izole gerçek SQLite/telefon testlerine dayanıyor.

## Önceki dış Beta — kayıt ve mikrofon ekranı dağıtım geçmişi

**8 Eylül dış Beta: 2026.6.5 (1788715054).** Apple yüklemesi **COMPLETE**,
build **VALID**, iç ve dış durum **IN_BETA_TESTING**; **Mert** ve **Beta**
gruplarına atanmış. İnceleme **APPROVED**, otomatik test bildirimi açık.
Mevcut [TestFlight bağlantısı](https://testflight.apple.com/join/nEdn2Np2) korundu.
Apple yüklemesinde hata/uyarı yok; EN/TR test notları eklendi ve birebir geri
okunarak doğrulandı. Kullanıcı 8 Eylül'de sürüm testlerinde sorun görmediğini
bildirdi ve yeni build'in dış Beta'ya açılmasını açıkça onayladı. Bu, kullanıcı
bildirimidir; her ayrıntılı cihaz kabul maddesi bağımsız gözlenmiş sayılmıyor.
Dağıtım için yeniden build alınmadı; test edilen aynı imzalı paket kullanıldı.
`main`, canlı gateway/servis yapılandırması, test kullanıcıları, eski build'ler
ve grubun mevcut açık bağlantı ayarları değiştirilmedi.

### 8 Eylül dış dağıtım kanıtı

- Hedef Apple build kimliği: `8a10c8ae-6b2f-4740-ac03-95a52bc05079`;
  sürüm **2026.6.5**, build **1788715054**, **APP_STORE_ELIGIBLE**, süresi dolmamış.
- EN/TR “What to Test” alanları **200**, mevcut dış **Beta** grubuna tek build
  ekleme **204**, beta incelemesine gönderme **201** döndü. İlk inceleme yanıtı
  **WAITING_FOR_REVIEW** idi; ardından ayrı GET'ler **APPROVED** ve dış
  **IN_BETA_TESTING** döndürdü. Yalnız grup üyeliği başarı kanıtı sayılmadı.
- Son durum **8 Eylül 02:47 Türkiye saati** civarında doğrulandı; Apple'ın
  `submittedDate` alanı boş, başvuru zamanı bu alandan uydurulmuyor.
- Mevcut iç **Mert** erişimi ve dış **Beta** bağlantısı korundu. Yeni kullanıcı
  daveti, genel App Store yayını, GitHub release/tag veya sosyal paylaşım yapılmadı.
- İlk test-notu isteğinde yazma yöntemine eklenen isteğe bağlı JWT `scope`
  Apple tarafından **405** ile reddedildi; notların değişmediği okundu.
  Apple'ın [token belgesi](https://developer.apple.com/documentation/appstoreconnectapi/generating-tokens-for-api-requests)
  bu kapsam biçimini GET için tanımlıyor. Belgeli standart yazma tokenıyla,
  mevcut anahtar rolü ve 60 saniyelik yalnız-bellek yetkilendirmesiyle işlem
  tamamlandı; hesap/anahtar yetkisi değiştirilmedi. Anahtar/token loglanmadı.
- Yayın aracı takip işi: `fastlane/testflight-distribution.json` eski
  **1788552567** hedefini içeriyor; Ruby yardımcı yalnız grup üyeliğini
  `DISTRIBUTION_VERIFIED` sayıyor. Bu koşuda çalıştırılmadı. Gelecekte otomatik
  dağıtım kullanılmadan önce hedef seçimi ve gerçek dış Testing doğrulaması
  tek yayın akışında düzeltilmeli. Bu dağıtım doğrudan Apple API ile doğrulandı.

### Kayıt düzeltmesinin geliştirme ve iç dağıtım geçmişi

Kullanıcı, önceki **1788570416** iç adayında kadrandan uygulamayı açıp komut göndermeyi hatasız
tamamladığını bildirdi. Bu, bildirilen kısa akışın fiziksel cihaz kontrolüdür;
tüm kabul listesinin tamamlandığı anlamına gelmez. Aynı denemede 15 saniye
dolmadan “kayıt çok uzun” hatası, küçük yazı ve ekran dışına taşan eylem bildirildi.
Kullanıcı netleştirdi: sayaçta **6 saniye kalırken Gönder'e kendisi bastı**;
bu bildirim kendiliğinden 9 saniyede duran bir kayıt değildir.

- Kullanıcı, kayıt güvenilirliği ve sade mikrofon ekranı düzeltmesini onayladı.
- Hata mesajının kaynağı Watch'taki 60.000 bayt JSON kontrolüydü; süre kontrolü
  değildi. Bu dal teslim alınmayan kaydı kuyruktan siliyordu. Gerçek sorunlu
  ses dosyası elimizde olmadığından gerçekleşen codec/boyut nedeni doğrulanmadı.
- Kayıt bitişi ve monoton sayaç tek yaşam döngüsüne alındı; gerçek dosyanın
  yalnız sayısal süre/boyut/format tanısı eklendi, ses içeriği loglanmıyor.
- Büyük istekler için Apple'ın dosya aktarımı ve eşleşen iş makbuzu; gönderim
  hatasında sesin korunması; küçük isteklerde mevcut hızlı aktarım uygulandı.
- Kayıt ekranında okunur sayaç ve görünür Sil/Gönder düğmeleri için ayrı alt
  alan ayrıldı. Önceki sonuç ve yardımcı başlıklar kayıt alanını sıkıştırmıyor.
- Önceki tam başarılı, yalnız doğrulama koşusu: `4ca09062de9dfa7c5f4cf4aae71bf29abe267975`,
  <https://github.com/MertBasar0/ceviz/actions/runs/34021753131>.
  Python **94/94**, relay **3/3**, beş Swift regresyon programı, imzalama
  sözleşmeleri, iPhone/Watch/widget Release derlemesi ve gerçek açılış geçti.
  Beş native senaryonun tamamı geçti: **40 ve 49 mm**, normal ve gerçek
  maksimum sistem yazısında EN/TR hazır/kayıt/silme; iki cihazda varsayılana
  dönüşün **9/9** kontrolü; manuel ve otomatik kayıt bitişi.
  Son iki dosya **9,724 sn** ve **14,908 sn**; her bitişin ardından ekran
  saklanan istek için `Queued` gösterdi. Fiziksel teslim ayrıca doğrulanacak.
  Ekran görüntüleri ayrıca incelendi. Simülatör, fiziksel mikrofon kalitesini
  veya iPhone'a dosya teslimini kanıtlamaz.
- Kullanıcının iç dağıtım onayıyla `f29baf52eca5e3f73af90c4f640df47a690667cc`
  kaynağından imzalı aday çalışması başlatıldı:
  <https://github.com/MertBasar0/ceviz/actions/runs/34029580846>.
  Önceki başarılı kaynağa göre yalnız belge değişikliği vardı. Bu çalışma
  **başarısız**: 40 mm normal/büyük yazı/kayıt bitişi ve 49 mm normal geçti;
  49 mm büyük yazı hazırlığında gerçek Ayarlar listesinin ilk kaydırması
  ilerlemedi. Yazı boyutu değiştirilmeden testin ilerleme denetimi durdu.
  İmzalama ve Apple yüklemesi atlandı; **yeni IPA veya TestFlight build'i yok**.
  Aynı hareket önceki başarılı çalışmada listeyi ilerletmişti; bu koşudaki
  değişmeyen görüntü ve satır konumları kök nedenin kendisini açıklamıyor.
  Koordinat değiştirme, yeniden deneme veya test gevşetme uygulanmadı.
  Tam native hata paketi ve ekran/ses kanıtları yerelde saklandı.
  Native oturum günlüğünde Ayarlar PID 49098 için `TouchEventsCompleted`
  ve 0,830 sn'de başarılı sentez tamamlanması var; “hareket hiç iletilmedi”
  denemez. Bu bildirim listenin kaydırmayı kabul ettiğini kanıtlamaz.
  Bu koşunun iki dosyası **9,468 sn / 25.176 bayt** ve **14,908 sn / 25.516 bayt**,
  AAC, 16 kHz, mono. Manuel bitiş `Queued`, otomatik bitiş uygulamanın
  **demo sonucu** gösterdi; gerçek gateway teslimi kanıtı değildir.
  40 mm varsayılana dönüş **9/9** geçti; 49 mm büyük yazı bu koşuda doğrulanmadı.
- Kullanıcının engeli çözerek iç dağıtımı tamamlama onayıyla testin Ayarlar
  gezinme sahibi sadeleştirildi: koordinat sürüklemesi kaldırıldı, yerine
  Apple'ın belgeli `rotateDigitalCrown(delta:velocity:)` yöntemi kullanılıyor.
  İlk Crown denemesinde yön **-0,25 tur**, hız açıkça **0,5 tur/sn**.
  Bu açık hız birimi, Apple'ın desteklediği hazır hız sabitlerinin hatalı
  olduğunu göstermez. Öndeki Ayarlar ve tek gerçek liste doğrulanıyor;
  her adımın önce/sonra satırları kaydediliyor. İlk ilerlemesizlikte durma,
  sekiz adım sınırı, beş senaryonun sırası ve gerçek yazı/geri yükleme
  kontrolleri değişmedi. **45 yerel altyapı testi geçti**; bu, Crown hareketinin
  veya gerçek ekranların native başarı kanıtı değildir. Kaynak `76ca45e69f9e59a5632db2b0d70f26d6d803c330`,
  <https://github.com/MertBasar0/ceviz/actions/runs/34040939355>:
  derleme ve 40 mm normal ekran geçti; 40 mm büyük yazı hazırlığında ilk Crown
  hareketinden sonra dört satırın konumu birebir aynı kaldı. Test durdu;
  imzalama/yükleme başlamadı. Bu koşuda büyük yazı ve ses bitişi doğrulanmadı.
  Üretim uygulaması ve workflow değişmedi.
  Önceki dokunmanın Apple içinde neden kaydırmadığı çözülmüş gösterilmiyor.
- Crown yönü için önceki “negatif = listede ilerleme” yorumu yeterli değildi:
  Apple'ın [WWDC21 örneği](https://developer.apple.com/videos/play/wwdc2021/10208/)
  özel hava durumu ekranında pozitif dönüşü ileri, negatifi geri gösteriyor;
  bu, Ayarlar listesinin yönünü tek başına kanıtlamaz. Tek gezinme yolu
  **+0,25 tur / 0,5 tur/sn** olarak aday düzeltmeye alındı; ilk ilerlemesizlik
  hatası, adım sınırı ve tüm kabul kontrolleri korunuyor. Ayarlar'da gerçekten
  ilerleme sağladığı aşağıdaki yeni native koşunun satır/görüntü kanıtıyla doğrulandı;
  yalnız yön değişikliği başarı veya kesin kök neden kanıtı değildir.
- Kaynak `c1d85bb8098b17a8b37cc0f661d5ffd0e2276ff4` ile
  <https://github.com/MertBasar0/ceviz/actions/runs/34042776769> ekran testine
  ulaşamadı: normal Ceviz açılışı ve görüntüsü doğrulandı; genel `simctl openurl`
  çağrısı **60 saniyede, boş çıktı ile zaman aşımına uğradı**. Bu, izin verilen
  115 istisnası değildir; kapı fatal kaldı, imzalama/yükleme başlamadı.
  Kaynak/kapılar değiştirilmeden tek yeni ortam karşılaştırması başlatıldı:
  <https://github.com/MertBasar0/ceviz/actions/runs/34043752041>.
  Aynı SHA doğrulandı; bu kez açılış aşaması tamamlandı, yalnız bilinen 115
  tanısı adayda korundu ve beşli UI kontrolüne geçildi. Ancak 40 mm normal
  hazır ekranın ardından ilk mikrofon dokunuşu kayıt başlatmadı; test durdu.
  Ayarlar'ın pozitif Crown hareketine ulaşılmadı; imzalama/yükleme yok.
  Önceki URL zaman aşımının kök nedeni çözülmüş gösterilmiyor.
- Başarısız `34043752041` koşusunun native OS arşivinde **16:08:52 UTC** için somut hata zinciri var:
  Recap sanal dokunma aygıtını kaldırıyor; BackBoard hâlâ basılı teması Ceviz'in
  gerçek pencere kimliğine (`0x795D6FE4`, PID 26173) **soft cancel** ile iptal
  ediyor. XCTest yine de `TouchEventsCompleted` bildiriyor. Aynı aygıtın iki
  temas durumu ve atlanan `pathIndex:2` olayları kaydedilmiş. Uygulama aktif,
  düğme erişilebilir; `view_appeared` var, `primary_action` yok. İptal sonrası
  UIKit olayı normal parmak kaldırma kanıtı değildir. İzin, kayıt süresi veya
  `contentShape` kök neden diye sunulmuyor; bu gerekçeyle üretim kodu değişmedi.
  Arşiv yalnız yerelde çözüldü; ayrıştırıcı bir firehose EOF uyarısı verdiği
  için tüm kayıtların eksiksiz olduğu iddia edilmiyor.
- Native olay üreticisini farklı desteklenen sürümde karşılaştırmak için
  workflow **Xcode 26.6 (17F113)** üzerine sabitlendi; belirsiz en-son-sürüm
  fallback'i kaldırıldı. Aynı runner imajının resmî envanterinde Xcode 26.6 ve
  iOS/watchOS 26.5 simülatörleri mevcut. Uygulama, beş senaryo, dokunma API'leri,
  süreler ve ses ölçüm eşikleri değişmedi. Apple sürüm notları bu özel Recap
  hatasının giderildiğini söylemiyor; bu bir kontrollü ortam karşılaştırmasıdır,
  tüm önceki aralıklı hataların kök nedeninin giderildiği iddia edilmiyor.
  Yerel **45/45** test, workflow YAML ayrıştırması ve **21** komut bloğunun
  Bash sözdizimi kontrolü geçti. Üretim kodu farkı **0**; workflow **+5/-9**.
  Kaynaklar: [tam runner imajı](https://github.com/actions/runner-images/blob/macos-26-arm64/20260831.0337/images/macos/macos-26-arm64-Readme.md),
  [Apple Xcode 26.6](https://developer.apple.com/documentation/xcode-release-notes/xcode-26_6-release-notes).
  Bağımsız kaynak incelemesinde engelleyici bulgu yok. Kaynak
  `e156d252b25d57d9638edc820596718bc903ad70` ile yeni tam kapılı iç aday:
  <https://github.com/MertBasar0/ceviz/actions/runs/34046167349>.
  Çalışma **başarılı**: gerçek Xcode **26.6 / 17F113**, SDK ile eşleşen
  iOS/watchOS **26.5**. Python **94/94**, relay **3/3**, beş Swift programı,
  imzalama sözleşmeleri, üç hedefin Release derlemesi ve normal açılış geçti.
  **Beş native senaryo** geçti: 40/49 mm normal ve gerçek maksimum sistem
  yazısında EN/TR hazır/kayıt/silme, iki cihazda varsayılana dönüş **9/9**,
  manuel/otomatik kayıt bitişi. Pozitif Crown hareketi gerçek Ayarlar
  satırlarını ilerletti; maksimum değer **100%** ve uygulama yazı geometrisi
  doğrulandı. Senaryo atlama, yeniden deneme veya süre artırımı uygulanmadı.
  Genel dış URL yoklamasının bilinen **115** tanısı iç aday sınırında kaldı;
  bu, fiziksel WidgetKit dokunuşunun kanıtı değildir.
  Gerçek iki ses dosyası **9,916 sn / 25.204 bayt** ve
  **14,908 sn / 25.516 bayt**, **AAC / 16 kHz / mono**.
  Manuel sonuç `Queued`, otomatik sonuç uygulamanın **demo Completed** kartı;
  bunlar gerçek gateway teslimi veya fiziksel mikrofon kalitesi kanıtı değildir.
  Ekranlar ana ajan ve bağımsız incelemeyle kontrol edildi. Çoklu görsel
  sunumunda şüpheli görünen manuel-sonuç ve 49 mm ilk-hazır PNG'leri tekil
  yeniden açıldı; gerçek dosyalarda `Queued`/mikrofon ve hazır ekran/mikrofon
  tam görünüyor. Eksik veya siyah artefakt bulgusu doğrulanmadı. Kayıt sayacı
  ve EN/TR Sil/Gönder düğmeleri normal ve maksimum yazıda görünür; 49 mm
  maksimum hazır ekranda son açıklama ile mikrofon arasında **28,75 pt** var.
  Geri yüklenen 49 mm karede bağlantı satırı yok; bu kare Offline kanıtı olarak
  kullanılmıyor. Tam soğuk-açılış Default ve gerçek **9/9** geri yükleme
  ölçümleri sistem yazısının geri döndüğünü doğruluyor.
  İmzalı IPA **17:18:59 UTC**, başarılı Apple yüklemesi **17:20:39 UTC**.
  Paket denetiminde iPhone/Watch/widget kimlikleri ve sürümleri eşleşti;
  üç hedefte de profil ve imza kaynakları var. Bu ZIP denetimi kriptografik
  doğrulama değildir; Apple ayrıca build'i **VALID** kabul etti.
  IPA SHA-256: `b46bd2dda99787cd164dcaf944e8002543fd895f60cf5325d30c7eb12693a390`.
  Yeni build **1788715054**, Apple kimliği `8a10c8ae-6b2f-4740-ac03-95a52bc05079`;
  6 Eylül'deki yükleme **COMPLETE**, hata/uyarı yok; o aşamada yalnız iç
  **Mert / IN_BETA_TESTING**. Dış dağıtım işi atlandı; o tarihte **Beta**
  üyeliği yoktu. 8 Eylül dış dağıtımı en üst bölümde kayıtlıdır.
- Düzeltme yalnız `codex/watch-capture-repair` dalında; **main değişmedi**.
  İç dağıtım sonrası kullanıcı kendi sürüm testlerinde sorun görmediğini
  bildirdi; açık onayıyla dış dağıtım tamamlandı. Dış testlerde iPhone ve Watch
  birlikte güncellenmeli. Manuel/otomatik kayıt, büyük yazı, bağlantı kesilmesinde
  sesin korunması ve eşleşen teslim makbuzu geri bildirimde izlenecek konular.
- Repo yönergesinde adı geçen `autoreview` / `test-audit` becerileri bu oturumda
  mevcut değil; bağımsız ajan incelemesi ve doğrudan kaynak/test kontrolleri
  kullanılıyor. Bu araçların çalıştırıldığı iddia edilmiyor.
- Recorder/UI/transport bağımsız kaynak incelemesi tamamlandı; reset sonrası
  gecikmiş dosya/makbuz ve farklı telefon-saat sürümü bulguları kapatıldı.
  Native dosya aktarımı ve monoton kayıt sahibi için gereken üretim kodu eklendi;
  küçük mesajların hızlı yolu ve mevcut backend kimliği korunuyor.

### Doğrulama geçmişi

- Kaynak `f01c17f9b8446e6275468e71f434a5071c90979e`, yalnız
  `codex/watch-capture-repair` doğrulama dalına gönderildi; `main` değişmedi.
  İlk doğrulama: <https://github.com/MertBasar0/ceviz/actions/runs/33991428373>.
  SDK ile eşleşen iPhone Air simülatörü `Data Migration Failed` bildirdi;
  uzayan çalışma durduruldu. Sonradan alınan tam günlük/artefakt, Watch normal
  açılışına ulaşıldığını ve dış URL çağrısının yine 115 verdiğini gösterdi.
  40 mm hazır ekranı incelendi: 15 saniye açıklaması ve mikrofon görünür;
  ekranın altındaki ikincil çevrimdışı satırı kısmen kırpılıyor. Kayıt ekranı
  ve ses süre testleri çalışmadı, imzalama veya yükleme başlamadı. Önce bu
  sıfır çıkış kodlu tanıyı durdurucu sayan test kontrolü eklendi; ancak önceki
  başarılı `33934521351` çalışmasının tam günlüklerinde de aynı tanı ve ardından
  çalışan uygulama görüldü. Tek başına host migration metnini uygulama hatası
  sayan bu kontrol geri düzeltildi: tanı uyarı olarak korunur; kurulum, gerçek
  açılış ve UI/ses ölçümü geçmeden başarı verilmez. Açılış beklemeleri sınırlı.
  Sayısal ses ölçümleri yalnız ilgili test sırasında canlı toplanacak;
  kalıcılığı garanti olmayan geçmiş info günlükleri kanıt sayılmayacak.
  Test altyapısı adayı `7db1d6adb5d1ae288dd0b09a8fe61ec8b02804e7` ile başlayan
  <https://github.com/MertBasar0/ceviz/actions/runs/33992244824>, bu yeni
  karşı kanıt üzerine durduruldu; üretim kodu değişmeden düzeltilmiş kontrolle
  tekrar doğrulanacak. Durdurulan çalışmaların hiçbiri UI/ses başarısı sayılmaz.
- Üçüncü doğrulama, `0bd3377d660d918e8a0440b042511a1e2bb73a35`:
  <https://github.com/MertBasar0/ceviz/actions/runs/33992504192>.
  83 Python, relay/Ruby/beş Swift programı, iPhone/Watch/widget derlemesi,
  gerçek Watch açılışı ve yerel imzalar geçti. 40 mm hazır ekranı incelendi;
  eski sürümün native XCTest paketi de `TEST BUILD SUCCEEDED` ile derlendi.
  Ardından watchOS 26.4, `simctl ui ... content_size` çağrısını
  `Runtime does not support dynamic text` / 45 ile reddetti. Bu bir beklenen
  UI regresyonu değil, test hazırlama hatasıdır; XCTest dokunuşları ve ses
  ölçümleri hiç başlamadı. Desteklenmeyen komutun yerine gerçek Watch Ayarlar
  akışı hazırlanıyor. Aynı simülatör çifti ardışık testlerde açık tutulacak;
  her denemede Ceviz test kurulumu yine temizlenecek, hiçbir senaryo atlanmayacak.
- Hazır ekranda boş takip rozeti alanı çevrimdışı satırını aşağı itiyordu;
  bu alanı kaldıran ContentView düzeltmesi dördüncü doğrulamada native
  derleme ve yeni normal-yazı görüntüsüyle doğrulandı.
- Kullanıcı 6 Eylül'de açıkça **önce otomatik ekran kontrollerinin tamamlanmasını**
  seçti. UI/süre testlerini atlayarak iç TestFlight adayı çıkarılmayacak.
  Testlerdeki font değişikliği gerçek `com.apple.NanoSettings` kontrollerinden
  yapılacak; gerçek ayar değeri, Ceviz metin geometrisi ve geri yükleme okunacak.
  Bu test hazırlığı üretim uygulamasına görünüm/durum enjeksiyonu eklemiyor.
- Dördüncü doğrulama için gerçek Ayarlar testi, cihaz çifti sahipliği ve boş
  takip rozeti düzeltmesi hazır; 89 yerel Python testi geçti. Bu son değişiklikler
  `5afca665104c104ed052d792997d9a02bdef187b` ile yalnız doğrulama dalına gönderildi:
  <https://github.com/MertBasar0/ceviz/actions/runs/33994445810>.
  Apple ortamında kod testleri, iPhone/Watch/widget Release derlemesi ve gerçek
  Watch açılışı geçti. Yeni 40 mm açılış görüntüsü incelendi: süre açıklaması,
  çevrimdışı satırı ve mikrofon düğmesi kırpılmadan görünür. Bu, normal hazır
  ekran kanıtıdır. Önceki sürümün 15 saniye açıklaması için özgül görünürlük
  hatası gerçek XCTest ile yeniden üretildi. Yeni 40 mm varsayılan yazıda
  hazır ekran ve EN/TR kayıt/silme testleri **2/2** geçti; kayıt görüntüleri
  incelendi. Sağ eylem düğmesinde ilk bakışta şüphelenilen kırpılma, bağımsız
  görsel inceleme ve özgün dosyanın piksel ölçümüyle doğrulanmadı: 324 piksel
  görüntüde kontur en sağda x=313, sağ kenarda 10 piksel boşluk var. Bu nedenle
  üretim yerleşimine ek düzeltme yapılmıyor.
  Büyük yazı testi `Display & Brightness` satırını bulamadı ve koşu durdu.
  Kaydedilen gerçek Settings videosu satırın mevcut olduğunu, tam ekran hızlı
  kaydırmasının üzerinden atladığını gösteriyor. Yazı boyutu değiştirilmedi;
  9/15 saniye dosya ölçümleri ve 49 mm senaryoları bu koşuda çalışmadı.
- Sonraki dar düzeltme testin gerçek Ayarlar listesinde kısa/yavaş sürükleme
  kullanmasıdır; hedef erişimi ve görünür satır ilerlemesi doğrulanacak. Eski
  hazır ekran regresyonunun gerçek kanıtı artık mevcut, sonraki koşu yeni
  sürümün beş senaryosunu koruyarak yalnız bu matrisi yeniden çalıştıracak.
  Silme sonrası İngilizce görüntüde yalnız “Recording” görünmesi üzerine
  onay “Discarded” olarak kısaltıldı; Türkçe “Kayıt silindi” düzeltildi.
  Onayın bütünüyle görünmesi native kabul kontrolüne eklendi.
- Beşinci doğrulama `a49ba377f4a95e960c1d05d581f54e1046e69b59`:
  <https://github.com/MertBasar0/ceviz/actions/runs/33996017849>.
  Kod/derleme/açılış geçti; 40 mm hazır ekran ve İngilizce kayıt/silme ile
  kısa “Discarded” onayı doğrulandı. Türkçe kayıt görüntüsünde 7 saniye kaldı;
  ardından ek AX tanısı 18 saniyeyi aşınca kayıt doğal süre sınırında sona
  erdi ve test Sil düğmesini bulamadı. Son AX ağacı korunmuş kuyruk sonucunu
  gösterdi. Bu, 15 saniyelik dosya süresi ölçümü yerine geçmez. Süre sınırlı
  adımda ayrıntılı AX tanısı kaldırılacak; görüntü ve tüm görünürlük kontrolleri
  kalacak, tanı hazır/silme sonrası alınacak. Büyük yazı ve 49 mm çalışmadı.
- Altıncı doğrulama yalnız bu tanı sırası düzeltmesiyle başladı:
  `9db2c07e24019b7045c7b02bbd21e3e47d108f36`,
  <https://github.com/MertBasar0/ceviz/actions/runs/33996874347>.
  40 yerel Watch yardımcı testi ve bağımsız inceleme geçti. Apple kod testleri,
  derleme ve normal Watch açılışı geçti. 40 mm normal yazıdaki EN/TR kayıt/silme
  ve tam onay görünürlüğü **2/2** geçti. Gerçek Ayarlar'da `Display & Brightness`
  → `Text Size` bulundu; kaydırma düzeltmesi native olarak doğrulandı.
  Slider %29'dan %100'e çıktı, Ayarlar örnek yazısı büyüdü; fakat test runner'ın
  `WKInterfaceDevice` kategori değeri değişmediği için test durdu. Geri alma
  sürüklemesi de hedef %29 yerine %14'e indi; bu ayar geri yükleme başarısı
  sayılmıyor. Kontrol yalnız test sürecindeki kategoriye dayanmayacak; gerçek
  ayar değeri ve Ceviz'in gerçek metin geometrisi ölçülecek. Özel yazı boyutu
  denetimi harf düğmelerine basıp her basamağı okuyarak hedefe ulaştırılacak;
  geri yükleme de okunarak doğrulanacak. Büyük yazıdaki Ceviz testleri,
  9/15 saniye dosya ölçümleri ve 49 mm henüz çalışmadı; yükleme yok.
- Yedinci doğrulama: `dbfe9c1abe770f1035595ec28b88f6beff7f5380`,
  <https://github.com/MertBasar0/ceviz/actions/runs/33998346812>.
  Kod testleri, Apple derlemesi ve Watch açılışı geçti; 40 mm normal yazıdaki
  iki native test de geçti; beş normal-yazı görüntüsü incelendi.
  Ayarlar harf düğmeleriyle %100'e ulaşıldı ve Ceviz'in büyük yazı görüntüsü
  alındı. Bu kez gerçek yerleşim hatası doğrulandı: süre y=73,5…122,5 pt,
  mikrofon y=116,25…171,75 pt; çevrimdışı satırı y=130,5…152 pt ile mikrofonun
  altında kalıyor. Native görünürlük kontrolü koşuyu durdurdu; büyük yazı
  kayıt/silme, 9/15 saniye dosya ölçümü ve 49 mm yine çalışmadı.
  Geri alma %29 değerine ulaştı; fakat Settings'in canlı örnek metni başlangıç
  89,5 pt yerine 67,5 pt kaldı. Bu, sorgunun bulunamaması değil gerçek görüntü
  farkıdır; geri yükleme başarısı sayılmadı. Yeni kontrol canlı farkı saklayıp
  başlangıçtaki gibi yeni açılmış Settings ve Ceviz'i ölçüyor; tüm görüntüler
  toplandıktan sonra aynı sıkı eşitlikler uygulanıyor. Test runner'ın font
  kategorisi yalnız tanı olarak saklanıyor.
  Paralel incelemede dosya ölçüm kapısı da güçlendirildi: yalnız son iki doğru
  ölçümü seçmek yerine tam iki finalizasyon zorunlu; ek veya ölçülemeyen
  finalizasyon kanıtta saklanıp reddediliyor. Önce eski kodda yanlış başarı
  yeniden üretildi; düzeltmede **42/42** Watch yardımcı testi ve **91/91**
  tüm Python testleri geçti, bağımsız incelemede açık bulgu kalmadı.
  Bu son ölçüm-kapısı değişikliği `8b29476053092b583ccb2acfdd99067d459db39c`
  ile doğrulama dalında; yedinci koşunun dondurulmuş kaynağında yok,
  sonraki koşuya girecek. Süre kanıtı simülatörde oluşan dosyaya aittir;
  sonuç kartının görünmesi yeni komutun kimlikli, kalıcı teslim kanıtı değildir.
  Eşleşen yeni komut/makbuz ve kesinti sonrası teslim fiziksel kabul adımıdır.
- Gerçek maksimum-yazı hatasının düzeltmesi hazır: içerik ve alt düğmeler
  tek dikey yerleşimde ayrı kardeşler. Kısa hazır içerik doğrudan yerleştiriliyor;
  uzun takip/sonuç içeriği kaydırılabilir kalıyor. Süre görselde kısaltıldı,
  ekran okuyucunun tam cümlesi korundu. Silme onayı ek satır yerine hazır
  başlığının yerini alıyor. Dinamik fontlar ve 54 pt düğme alanı değiştirilmedi.
  Süre metni/düğme çakışması için ek native kontroller kondu. Yerel **91/91**
  test ve taze bağımsız inceleme geçti.
- Sekizinci doğrulama: `d3a9ef08c9ff8e425678a3e014f97788eefe6b60`,
  <https://github.com/MertBasar0/ceviz/actions/runs/33999904091>.
  Apple derlemesi/kod testleri ve 40 mm normal yazıdaki iki native test geçti;
  beş yeni görüntü incelendi. Kısaltılmış süre ve başlığın yerini alan silme
  onayı, çevrimdışı satırı ve mikrofonla birlikte görünür. Büyük yazıya geçişte
  test doğru Ayarlar satırına dokundu; fakat sayfa varlığını erken kontrol etti.
  t=35,56 sn kontrolü olumsuzken t=35,99 sn görüntüsü ve sonraki AX ağacı
  gerçek `Display & Brightness` sayfasını gösteriyor. Bu koşuda font değişmedi;
  büyük yazı/geri yükleme, 9/15 saniye ve 49 mm doğrulanmadı. Üretim koduna
  dokunmadan yalnız bu sayfaya varış kontrolü mevcut 8 saniyelik bekleme
  sözleşmesine alındı; tekrar dokunma veya sabit uyku eklenmedi. **42/42** Watch
  yardımcı testi, **91/91** tüm Python testleri ve bağımsız inceleme geçti.
  Yeni native koşu yine beş senaryoyu ve sıkı görünürlük/süre kapılarını koruyacak.
- Dokuzuncu doğrulama: `1033af0fa44810ef0074f0eea3508454cce31e11`,
  <https://github.com/MertBasar0/ceviz/actions/runs/34000969048>.
  Apple derlemesi/açılışı ve 40 mm normal yazı **2/2** geçti; açılış ve beş
  normal ekran görüntüsü incelendi. Ayarlar'a varış düzeltmesi çalıştı.
  Büyük yazıda süre tamamen görünür, ancak çevrimdışı satırı y=99…120,5 pt
  iken kaydırma alanı 111 pt'de bitiyor, mikrofon 116,25 pt'de başlıyor.
  Görüntü ve AX ağacı bu kalan kırpılmayı doğruladı. Aynı yerleşimde üç eylemin
  minimum yüksekliği 54 → 44 pt yapılarak 10 pt alan geri kazanılıyor; dinamik
  font, eşit düğme yüksekliği ve 12 pt yatay boşluk korunuyor. Bu, Apple'ın
  en az 44×44 pt dokunma alanı rehberiyle uyumlu; yeni native kanıt bekleniyor.
  Geri yükleme **geçmedi**: %29 değeri aynı olsa da Settings metni 89,5 → 67,5 pt,
  Ceviz başlığı 19,5 → 18 pt oldu. Tek test-hatası özeti başarı kanıtı değil;
  `text-size-restore-measurements` eki gerçek farkı gösteriyor. Video, gerçek
  `Default` etiketinin ilk %29 konumunda değil sonraki basamakta olduğunu
  gösterdi. İlk açılış seçimi ile çizilen boyut uyumsuz; iç nedeni bilinmiyor.
  Büyük-yazı testinin başlangıcı gerçek Ayarlar'ın `Default` etiketiyle
  kuruldu; boyuta göre yüzde varsayılmıyor. Yeni açılmış Settings/Ceviz
  ölçümleri başlangıç; maksimum boyut ve sıkı geri yükleme kontrolleri
  korunuyor. İlk ham seçim/görüntü ayrıca saklanıyor. Silme sonrası çevrimdışı
  satırının görünürlüğü EN/TR'de de aynı kontrolü kullanıyor. **42/42** Watch
  yardımcı testi ve **91/91** tüm Python testleri geçti; yeni native kanıt
  bekleniyor. Tek geri alma sahibi ilk ayar değişikliğinden önce kaydoluyor;
  başlangıç hazırlığı yarıda kalırsa da son doğrulanmış seçime dönüş denenip
  kaydediliyor, bu yol yazı geometrisi başarısı sayılmıyor. Dokunulmamış normal
  cihaz testi ayrıca kalıyor. 9/15 saniye ve
  49 mm senaryolarına yine ulaşılmadı; yükleme yapılmadı.
- Onuncu doğrulama: `d0d4b3d79bc6c2a89ecf85c4ff07715d2ca5b07e`,
  <https://github.com/MertBasar0/ceviz/actions/runs/34002617659>.
  Kod testleri, Apple derlemesi/açılışı ve 40 mm normal yazı **2/2** geçti;
  yeni 44 pt düğmeli açılış ve beş EN/TR ekran görüntüsü incelendi.
  Büyük yazı hazırlığı gerçek `Default` seçimine ulaşmadan durdu: ilk küçük
  harf dokunuşu %29 → %14, ikincisi %14'te kaldı. Görüntü/AX ve günlük,
  denetimde beklenen sıfır basamağının bulunmadığını gösteriyor. Sayısal
  geri alma %29'a döndü; geometri doğrulanmadığı açıkça kanıta yazıldı.
  Yalnız gereksiz sıfıra gitme ön koşulu kaldırılıyor. Gerçek `Default`
  etiketini arayan sınırlı, her basamağı okuyan akış; maksimum boyut,
  yeni açılmış Settings/Ceviz ölçümü ve sıkı geri yükleme kapıları korunuyor.
  %14 veya başka bir yüzde varsayımı eklenmiyor. Bu koşuda maksimum yazı,
  9/15 saniye ve 49 mm senaryoları çalışmadı; yükleme yapılmadı.
- On birinci doğrulama: `c66b2b41b5e0aa8dc1ef1641f600df38370f2c38`,
  <https://github.com/MertBasar0/ceviz/actions/runs/34004091583>.
  Kod/Apple derlemesi/açılışı ve 40 mm normal yazı **2/2** geçti. Gerçek
  `Default` seçimi ve maksimum yazıya geçiş bu kez çalıştı. İngilizce büyük
  hazır/silme ve EN/TR kayıt ekranlarına ulaşıldı. Türkçe silme sonrası
  `Telefon çevrimdışı` iki satır: y=99…141 pt; kaydırma alanı 121 pt'de biterken
  mikrofon y=126,25…171,75 pt. Görüntü ve AX aynı kırpılmayı gösterdi;
  native test bunu reddetti. Bağlantı satırı mevcut telefon simgesi ile kısa
  `Offline` / `Çevrimdışı` metnini kullanıyor; ekran okuyucuda tam telefon
  açıklaması korunuyor. Dinamik font, görünür durum bilgisi ve eylem alanı
  küçültülmüyor. Native kontrol yeni sabit kimlikle tam erişilebilirlik
  etiketini de doğrulayacak; eski etikete dayalı regresyon kapsamı korunuyor.
  Geri yükleme bu kez **doğrulandı**: dokuz sayısal kontrol true; Default/live/cold
  seçim 0,428571, Settings önizlemesi 143×89,5, Ceviz başlığı 113×19,5 ve süre
  71,5×19,5 pt ile başlangıca eşit. Bu yalnız geri yükleme alt akışının kanıtı;
  test bütünü başarısız. Yeni kısa bağlantı metni native kontrol bekliyor;
  9/15 saniye ve 49 mm henüz çalışmadı. İmza/yükleme adımı atlandı.
- On ikinci doğrulama: `0a281fe0e16d5648ea424bd93584b30fab99eb32`,
  <https://github.com/MertBasar0/ceviz/actions/runs/34005199330>.
  Kod/Apple derlemesi/açılışı ve 40 mm normal yazı **2/2**, gerçek maksimum
  yazı **1/1** geçti. Türkçe büyük silme sonrası kısa bağlantı metni
  y=99…120,5 pt, mikrofon y=126,25…171,75 pt; arada 5,75 pt var. Görüntüde
  `Çevrimdışı`, AX'te `capture.connection` / `Telefon çevrimdışı` doğrulandı.
  Büyük Türkçe sayaç/Sil/Gönder görünür; geri yüklemenin dokuz kontrolü geçti.
  Ardından ilk kez ulaşılan süre senaryosu, ilk dokunuş sonrası sayaç
  bulunamadığı için 18,771 sn'de durdu. Gerçek olay kaydı uygulama PID'sine
  (81,149) pt merkez dokunuşu; son AX hâlâ `Ready to listen` / `Start recording`.
  Canlı ses günlüğünde finalizasyon yok, dosya ölçümleri boş. Video yalnız
  6,952 sn açılış görüntüsünü içeriyor; dokunuş sonrasını göstermiyor.
  Bu, erken kayıt bitişi veya codec hatası kanıtı değil; başlangıcın neden
  gerçekleşmediği henüz bilinmiyor. Davranış değişikliği yapmadan aynı kayıt
  sahibine olay tanısı ekleniyor: gerçek düğme işleyicisi, guard/izin/başlangıç,
  iptal ve bitiş. Yalnız sabit olay adları, boolean/sayısal durum ve sahne;
  ses/kimlik/yol/transkript yok. Üretim net +14 satır, eksik başlangıç kanıtını
  toplamak için; durum geçişleri ve dosya ölçüm ön eki/kapısı değişmedi.
  Testte dokunuş öncesi PNG/AX ve foreground/etkin/görünür kontrolü, eksik
  öğede hata görüntüsü eklendi. Yeni deneme kök neden onarımı sayılmayacak;
  bu tanı hazırlığı dokunuş zamanını değiştirebilir. Tekrar dokunma, daha uzun
  bekleme veya daha gevşek süre eşiği yok. 9/15 saniye ve 49 mm halen
  doğrulanmadı; yükleme yapılmadı.
- On üçüncü doğrulama: `c5832591226f76bdf6c6fb2530b98e9125b46958`,
  <https://github.com/MertBasar0/ceviz/actions/runs/34006579916>.
  Apple derlemesi ve 40 mm normal **2/2**, büyük yazı **1/1** geçti.
  Canlı tanı bu kez gerçek düğme işleyicisini, boş kayıt sahibini, verilmiş
  mikrofon iznini ve native başlangıcı doğruladı. İlk denemedeki dokunuş
  sorununun kök nedeni yine bilinmiyor; tanı öncesi hazırlık zamanını değiştirdi.
  Bir gerçek dosya ölçüldü: **14,908 sn**, 25.516 bayt, AAC/16 kHz/mono.
  Native başlangıç ile callback günlüğü arasındaki 16,846 sn dosya süresi değil.
  Manuel gönderme testi geçmedi: t=26,98 ilk sayaç sorgusunu t=27,58…32,58
  arasında yaklaşık 5 sn ayrıntılı AX tanısı izledi. Aynı ekte ilk değer 10,
  son sorgu çıktısı 5; sonraki predicate değerlendirmesi 3 saniyeyi gördü.
  Böylece gerçek 4…6 aralığı kaçırıldı, `manual_stop` hiç çağrılmadı ve kayıt
  kendi sınırında tamamlandı. İkinci otomatik senaryo başlamadı. Bu tek dosya,
  zorunlu manuel + otomatik iki-kayıt kapısının başarısı sayılmaz.
  Dar test düzeltmesi: gerçek sayacı kendisi okuyan predicate bloğuna ayrıca
  UI nesnesi verilmemesi (`object: nil`). Apple'ın isteğe bağlı nesne sözleşmesi
  kullanılıyor; hedef aralık, 15 sn bekleme ve gerçek dosya sınırları aynı.
  Tanı yükünün kalkması sonraki native günlükle doğrulanacak; üretim değişmedi.
  49 mm çalışmadı; dağıtım/yükleme yok.
- On dördüncü doğrulama: `792f8f21e177635d7204f05e4ee6a74122a48ce4`,
  <https://github.com/MertBasar0/ceviz/actions/runs/34008239012>.
  Yerel **91/91**, Apple derlemesi ve üç yerel uygulama kimliği geçti.
  Açılış PNG'sinde Ready, süre sınırı, Offline ve mikrofon şahsen görüldü;
  native günlük de uygulamayı `ready` ve `running-active-Visible` gösterdi.
  Sonrasında testin açtığı Watch simülatörünü kapatma komutu **60 sn** içinde
  tamamlanmadı. UI testlerine hiç ulaşılmadı; sayaç beklemesi düzeltmesi henüz
  native doğrulanmadı. Bu, kayıt süresi testinin başarısızlığı değildir.
  Simülatörün neden kapanmadığı mevcut günlükte bulunmuyor. Ayrıca smoke
  temizliğinde doğrulanmış sahiplik/raporlama kusuru var: ilk kapanış hatası
  diğer sahip olunan cihazın temizliğini atlıyor ve sonuç dosyası temizliğin
  öncesinde yazıldığından bu hatayı içermiyor. Aynı sınırın UI koşucusunda
  mevcut olan ortak sahiplik akışıyla birleştirildi. Üç regresyon önce beklenen
  nedenlerle başarısız oldu, ardından **94/94** Python testi geçti. Kapanışta
  tüm sahip olunan cihazlar ele alınıyor, asıl hata korunuyor ve son rapora
  temizlik hataları da yazılıyor. Ortak kodun altı yaşam döngüsü testi kendi
  modülüne taşındı; net değişim test desteğinde +4, testlerde +56 satır,
  üretimde 0. Zaman aşımı halen 60 sn; kapanış hatası halen durdurucu.
  Bu düzeltme, işletim sisteminin kapanma takılmasının çözüldüğü iddiası değil.
  Kayıt ve 49 mm kontrolleri çalışmadı; TestFlight yükleme/dağıtım yapılmadı.
- On beşinci doğrulama: `000547d396c19c7a41d54c18d48efde2e6760a80`,
  <https://github.com/MertBasar0/ceviz/actions/runs/34009045391>.
  94 Python testi, Apple derlemesi, gerçek açılış ve doğrulanmış simülatör
  kapanışı geçti; açılış PNG'si şahsen incelendi. 40 mm normal UI **2/2** geçti.
  Büyük yazı senaryosu Türkçe kaydı silme adımında durdu. Gerçek maksimum
  sistem yazısı ve Ceviz'deki büyüme ölçüldü; EN hazır/kayıt/silme geçti.
  TR kayıt PNG'sinde Sil/Gönder görünürken **2 sn** kaldı: kayıt sırasında
  tekrarlanan AX boyut sorguları t=140,71…154,06 aralığını tüketti. İlk kayıt
  ve silme için üretilen dokunuş eklerinin zamanları arasında **19,677 sn** var;
  bu ek zamanı, gerçek touch teslim zamanı olarak sunulmuyor. Hata PNG'si daha
  sonra **7 sn** gösteriyor. Videoda şahsen görülen sıra: ilk kayıt biter,
  `Sırada` ve tam genişlik mikrofon görünür, ardından yeni **15 sn** kayıt başlar.
  Sil için üretilmiş (40,5;149) noktası genişleyen mikrofonun içinde kalıyor.
  Bu, geç dokunuşla yeniden başlatmayı destekliyor; kısa senaryoda canlı kayıt
  olayları toplanmadığından hangi Swift düğme işleyicisinin çağrıldığı doğrudan
  olay günlüğüyle kanıtlanmadı.
  Settings geri alındı, fakat kuyrukta istek kaldığı için Ceviz'in Ready
  karşılaştırması tamamlanmadı: bu koşuda dokuzlu tam geri-alma kapısı geçmedi.
  Kısa senaryo artık viewport'u kayıt öncesi, sayaç ve iki düğmenin çerçeve
  ve dokunulabilirlik değerlerini kayıt sırasında birer kez okuyor. Sayaç
  için 8 sn varlık beklemesi, üç kontrolün tam görünürlüğü, düğmelerin 44 pt
  alt sınırı, sayaçla çakışmaması ve silindi/hazır son durumu zorunlu kalıyor.
  Test değişimi net +11 satır; yeni bekleme/tekrar/fixture yok. Daha az sorgunun
  gerçek süre penceresini koruduğu sonraki native turda doğrulanacak. Üretim değişmedi;
  9/15 sn ve 49 mm çalışmadı.
  Sayaç predicate düzeltmesinin native kanıtı halen eksik; yükleme yok.
- On altıncı doğrulama: `2b0d75fe4c2236fface125eaf5d571b80ddba5b4`,
  <https://github.com/MertBasar0/ceviz/actions/runs/34010467856>.
  94 Python testi, Apple derlemesi ve açılış geçti. 40 mm normal **2/2**,
  gerçek maksimum yazı **1/1** ve varsayılan yazıya dönüş **9/9** geçti.
  EN/TR kayıt ve silindi ekranları şahsen incelendi; maksimum TR Çevrimdışı
  ile mikrofon arasında 5,75 pt boşluk var. Gönder okunuyor, kenarı dar.
  Geri dönüş ölçümleri ve AX eşleşiyor; `ready-restored` PNG'si siyah/saat
  içerdiğinden tek başına tam uygulama görsel kanıtı sayılmıyor.
  Manuel + otomatik kayıt testi **57,259 sn** içinde geçti: canlı olay günlüğü
  aynı süreçte manuel durdurmayı ve ikinci kaydın native bitişini doğruladı.
  Tam iki gerçek dosya: **9,788 sn / 25.196 bayt**, **14,908 sn / 25.516 bayt**;
  AAC, 16 kHz, mono. Sayaç sorguları artık 4…6 aralığını yakalıyor; önceki
  beş saniyelik ayrıntılı AX gecikmesi yok. İki bitiş PNG'sinde istek `Queued`
  olarak korunuyor. Bu, fiziksel mikrofon kalitesi veya iPhone'a teslim kanıtı değil.
  49 mm normal hazır testi geçti; EN/TR kayıt/silme/görünürlük kontrolleri de
  tamamlandı ve beş PNG incelendi. Fakat son `app.terminate()` çağrısı
  **60,91 sn** sonra hata verdi; normal senaryo bu yüzden başarısız sayıldı.
  49 mm maksimum yazı çalışmadı. Kapanış hatasının kök nedeni mevcut dışa
  aktarılmış günlükte yok; `:0` süreç eki, uygulamanın zaten kapalı olduğu
  kanıtı değil. Kapatma kaldırılmadı, hata yok sayılmadı veya süre uzatılmadı.
  İş akışına yalnız başarısızlıkta özgün `.xcresult` tanı paketlerini 7 gün
  saklama eklendi: test/ürün davranışı değişmeden eksik native kanıt korunacak.
  Aynı beşli sıra yeniden doğrulanacak; geçmesi tek başına kapanış kök nedeninin
  onarıldığı anlamına gelmeyecek. Üretim/test kodu net 0, CI metadata +9 satır.
  İlk dokunuş sorununun eski koşudaki kök nedeni de halen bilinmiyor.
  Main, TestFlight ve dış Beta değiştirilmedi.
- On yedinci doğrulama: `4ca09062de9dfa7c5f4cf4aae71bf29abe267975`,
  <https://github.com/MertBasar0/ceviz/actions/runs/34021753131> **başarılı**.
  Ürün ve test kodu bir önceki koşuyla aynı; yalnız başarısız koşunun ham
  Apple tanısını saklayan CI metadata düzenlemesi eklendi. Beşli sıra değişmedi.
  40 mm normal **2/2**, maksimum yazı **1/1**, iki-kayıt testi **1/1**;
  49 mm normal **2/2**, maksimum yazı **1/1** geçti. 49 mm son uygulama kapanışı
  bu kez tamamlandı; önceki kapanış hatasının kök nedeni halen bilinmiyor.
  49 mm gerçek Settings maksimumu %100, önizleme 178×125,5 pt; varsayılan
  konum 0,444444'e dönünce önizleme 178×76, Ceviz başlığı 119×20,5,
  süre 75×20,5 pt olarak eşleşti. Dokuz geri-yükleme kontrolü geçti ve
  geri dönmüş Ceviz ekranı şahsen görüldü. 40 mm geri-yükleme kapısı da geçti.
  Canlı kayıt günlüğü: manuel **9,724 sn / 25.192 bayt**, otomatik
  **14,908 sn / 25.516 bayt**, tam iki AAC/16 kHz/mono dosya. Manuel durdurma
  ve ayrı ikinci native bitiş gözlendi; iki sonuç da saklanan kuyruk durumuna
  ulaştı. Bu, gerçek cihaz ses kalitesi veya fiziksel teslim kanıtı değildir.
  `validation_only=true`: sertifika, ASC anahtarı, IPA üretimi/yüklemesi ve
  dış dağıtım atlandı. Başarısızlık tanı adımı da doğal olarak çalışmadı;
  yeni artifact yolunun gerçek başarısız koşudaki üretimi henüz görülmedi.
- Bu yalnız-doğrulama koşusu yeni build üretmedi. Daha sonra yüklenen güncel
  kayıt düzeltmesi **1788715054**, en üst bölümde kayıtlıdır.
  O aşamada dış Beta, kayıt ve ekran cihaz kontrolünü bekliyordu; sonraki
  8 Eylül dağıtımı en üst bölümde kayıtlıdır.
- OpenClaw gateway/model/ayarlar ve çalışan Ceviz servisleri bu düzeltmede
  değiştirilmedi; değişiklik Apple Watch/iPhone uygulama katmanında.

## Önceki iç test adayı — Beta 4, kayıt düzeltmesinden önce

**2026.6.5 (1788570416)**, Apple tarafından **VALID** olarak işlendi ve
**Mert** iç test grubunda **IN_BETA_TESTING** durumu API ile doğrulandı.
Dış **Beta** grubuna atanmadı; gerçek kadran açılışı cihazda doğrulanana kadar
dış dağıtım bekliyor. Kullanıcı iPhone ve Watch uygulamalarını birlikte güncellemeli.

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
  40 mm ekranda boş footer'ın alan tüketmesi de düzeltildi.
- Üçüncü Apple kontrolü (`98e145f48a272dd20bbf812afb9265448f92ff01`):
  <https://github.com/MertBasar0/ceviz/actions/runs/33932219345>.
  **62 Python**, relay/Ruby/Swift kontrolleri ve yerel imzalı native derleme
  geçti. Üretilen üç paket ve kurulu Watch için kimlik, ad hoc imza ve strict
  imza doğrulaması başarılı. Önceki kimlik uyuşmazlığı günlükte tekrarlanmadı;
  dış `openurl` yine kayıtlı scheme handler bulamayarak 115 ile durdu.
  Dağıtım imzası/yükleme başlamadı. 40 mm gerçek simülatör görüntüsünde kısa
  bağlantı başlığı, hazır başlığı ve mikrofon tamamen görünür; yardımcı ikinci
  açıklama bu boyutta görünmüyor. Gerçek WidgetKit dokunuşu halen doğrulanmadı.
- Cihaz doğrulaması için ayrı, açıkça seçilen bir aday build yolu hazır:
  normal CI'nin katı kontrolü korunuyor; yalnız bilinen dış URL 115 hatası
  aday modunda kanıtları ve uyarısıyla saklanıyor. İmza, kurulum, native derleme
  ve normal açılış hataları yine durdurucu. Bu izin bir kadran testi başarısı
  veya dış Beta dağıtım onayı değildir. Önce kullanıcının mevcut iç test
  grubunda fiziksel kadran kontrolü, ardından dış Beta dağıtımı yapılacak.
  Aday kalıcı Apple “Internal Only” niteliğinde değil; aynı imzalı paketin
  cihaz kontrolünden sonra dış gruba taşınabilmesi korunuyor. Otomatik dış
  dağıtım çalıştırılmıyor; gerçek grup üyeliği yükleme sonrasında okunacak.
  Güncel yerel Python **68/68**, relay **3/3** geçti. Gerçek Watch URL kararını
  kullanan 28 ek URL/kayıt-durumu birleşimi Swift testine eklendi; bunlar
  Apple ortamında çalıştırılmayı bekliyor, OS bağlantı teslimini kanıtlamıyor.
- İlk açık cihaz adayı (`820aa73b8d8d7ccc8145d582f360696e123a1e87`):
  <https://github.com/MertBasar0/ceviz/actions/runs/33933488909>.
  68 Python, relay/Ruby, iki Swift programı (28 URL/durum birleşimi dahil),
  native derleme ve normal Watch açılışı geçti. Aday bayrağı ve çözülemeyen
  dış URL 115 kanıtı artefaktta doğrulandı; gerçek kadran dokunuşu yapılmadı.
  Apple widget bundle ID oluşturuldu ve ayrı GET ile kaydı doğrulandı
  (`com.mertbasar.cevizwatch.watchkitapp.widget`, API platformu `UNIVERSAL`).
  Ardından Fastlane, `development:false`
  ve `adhoc:false` seçeneklerini birlikte verilmiş sayarak profil isteğinden
  önce durdu. **IPA/build numarası/upload yok.** App Store modunda her iki
  anahtarı da göndermeyen dar düzeltme ve gerçek Fastlane seçenek doğrulaması
  hazır; Apple hesabı veya sertifikalar değiştirilerek aşılmıyor. Yeni gerçek
  seçenek testi Apple ortamında çalıştırılmayı bekliyor.
- İmzalı cihaz adayı başarıyla üretildi ve yüklendi:
  **2026.6.5 (1788570416)**, kaynak
  `523cb988f9e3f9ed3258afbcd46a1609e0055471`.
  <https://github.com/MertBasar0/ceviz/actions/runs/33934521351>.
  **68 Python**, **3 relay**, Ruby sınır testi, **gerçek Fastlane seçenek
  doğrulaması** (üç mod + eski hatayı yeniden üreten negatif kontrol), iki Swift
  regresyon programı ve native derlemeler geçti. Watch normal açılışı ve yerel
  imzaları doğrulandı; 40 mm görüntüsü incelendi. Dış URL 115 hatası aday
  kanıtında başarısız olarak korunuyor; fiziksel WidgetKit dokunuşu yapılmadı.
  Mevcut iPhone profili kullanıldı, Watch profili yenilendi ve widget profili
  oluşturuldu. IPA export ve Apple upload **5 Eylül 01:09:33 UTC** başarılı.
  İndirilen IPA'nın üç gömülü bundle kimliği/sürümü, widget extension point'i
  ve profil/imza kaynaklarının varlığı kontrol edildi. Bu ZIP incelemesi tek
  başına kriptografik imza doğrulaması değildir.
  IPA SHA256: `76138c74cacc330300bdb66b2a96f6e6ee8c139655cb66f1a8f17fd101026cd5`.
  Apple upload/build kaydı `f0b61d35-1ff8-4e66-95a6-a297ce2f2d9d`, aynı
  sürüm/build için **COMPLETE**, hata/uyarı listeleri boş. Normal build API'si
  **VALID / internal IN_BETA_TESTING / external READY_FOR_BETA_SUBMISSION**
  döndürdü. Grup üyeliği yalnız **Mert**, otomatik bildirim açık; **Beta** üyeliği
  yok. İç test erişimi doğrulandı. Apple build kaydının işlemleme sonrası zamanı
  **5 Eylül 01:28:41 UTC**; upload kabul zamanı yukarıdaki **01:09:33 UTC**.
  Yeni `buildUploads` endpoint'i dar JWT scope eşleştirmesinde Apple'ın iç
  `/ac-gateway` yolu nedeniyle 403 verdi. Apple belgelerindeki standart,
  isteğe bağlı scope'suz 60 saniyelik JWT ile yalnız bu Ceviz build'ine sabit
  GET isteği yapılarak durum okundu; anahtar rolü/Apple yetkileri değişmedi.
  Dış dağıtım job'ı atlandı; dağıtım JSON'u yeni build'e çevrilmedi. Fiziksel
  kontrol öncesi dış Beta dağıtımı yapılmayacak.
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
- Bu önceki iç adayın ardından **1788715054** kayıt düzeltmesi test edildi;
  kullanıcı onayıyla **8 Eylül'de dış Beta** dağıtımı doğrulandı. Aşağıdaki
  Beta 3 bilgileri önceki dış sürümün tarihsel kaydıdır.
- Sonraki dilim: açık devam bağlamı, kişisel kısa yollar ve uygulama içi Doctor.
- Mevcut iş dosyası eşzamanlı yazma ve cihaz bazlı bildirim yeniden denemesi
  ayrıca ele alınmalı; garantili teslimat/uzak işte exactly-once iddiası yok.

## Önceki dış Beta sürümü — Beta 3 dağıtım geçmişi

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
kod değişikliği içermediğinden public external gruba eklenmedi. O dönemin public
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

## Ürün hedefleri ve sıradaki işler

### Önceki Beta 3 hedefleri — tarihsel plan

1. İngilizce arayüzde kalan Türkçe metinleri ve backend fallback çıktılarını
   temizle; iki dilin anahtar eşitliğini otomatik testle koru.
2. OpenClaw, yerel Whisper, servis, kimlik doğrulama, ağ ve eşleşme
   gereksinimlerini secretsız raporlayan `Ceviz Doctor` komutunu ekle.
3. Backend'in neden gerekli olduğunu, veri akışını, yetki sınırını ve tamamen
   kaldırma adımlarını kurulum sayfası ile README'de açıkça anlat.
4. Bu üç değişikliği test edip Beta 3 TestFlight build'i olarak yayımla ve ilk
   dış kullanıcıdan yeniden doğrulama iste.

### Beta 4 — yayımlanan dilim ve ek cihaz kapsamı

5. Doğrudan ses yakalama ekranını açan Watch komplikasyonu/widget'ı ve kayıt
   düzeltmesi, **1788715054** ile dış Beta'da; dağıtım kanıtı en üst bölümde.
6. 40/49 mm simülatör kontrolleri ve kullanıcının sorun görmediği cihaz testi
   mevcut. Başka cihazlar ve bağımsız kurulumlarda ilk komut geri bildirimini topla.

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
