# Watch Ceviz — STT (Konuşma→Metin) Kurulumu

Backend artık **key gerektirmeyen, lokal, gizli** STT kullanıyor: **faster-whisper**.
OpenAI artık zorunlu değil; yalnızca opsiyonel fallback.

## Nasıl çalışıyor
`backend/stt.py` → motor seçimi `WATCH_CEVIZ_STT_ENGINE` (default **auto**):
1. İstemci `transcript` gönderdiyse → onu kullan (STT atlanır).
2. **phone:** bu makine Whisper çalıştırmaz; iPhone her komutu Apple'ın cihaz üstü konuşma tanımasıyla
   metne çevirip sesle birlikte gönderir. Kurulum, large-v3'e yer yoksa ya da ölçümde yavaşsa bunu seçer.
3. **auto/local:** lokal Whisper (`backend/local_whisper.py`, faster-whisper). CUDA varsa GPU, yoksa CPU'ya düşer (warmup ile doğrulanır).
4. **auto/openai:** lokal başarısızsa ve `OPENAI_API_KEY` varsa OpenAI'ye düşer.

Kurulum yalnızca large-v3 kurar: günlük kullanımda küçük modeller komutları fazla yanlış duydu.
Ayrıntı: [deploy/README.md](deploy/README.md#speech-recognition).

## Env ayarları
| Değişken | Default | Açıklama |
|---|---|---|
| `WATCH_CEVIZ_STT_ENGINE` | `auto` | `auto` \| `local` \| `openai` \| `phone` |
| `WATCH_CEVIZ_STT_COMPARE` | boş | `whisper`: telefon modunda aynı sesi arka planda Whisper ile de çözer ve işe `stt_compare` olarak yazar (karşılaştırma için; kullanılan metin telefonunki) |
| `WATCH_CEVIZ_WHISPER_HOTWORDS` | Ceviz'in özel adları | Virgülle ayrılmış özel adlar; Whisper'a ve telefon modunda iPhone'a ipucu olarak gider |
| `WATCH_CEVIZ_WHISPER_MODEL` | `small` (kurulum `large-v3` yazar) | `large-v3` önerilir; elle başka model de verilebilir |
| `WATCH_CEVIZ_WHISPER_DEVICE` | `auto` | `auto` \| `cuda` \| `cpu` |
| `WATCH_CEVIZ_WHISPER_LANGUAGE` | `tr` | |

## Doğrulanan durum (2026-06-04)
- CPU `small`: jfk klibi 0.8s'de doğru transkript (~14x realtime). İlk çağrı model yükleme + cuda-warmup nedeniyle ~3.7s.
- CUDA şu an kapalı: `libcublas.so.12` eksik (sm_120 mimari değil, sadece runtime lib). GPU için:
  `./.venv/bin/pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` + `LD_LIBRARY_PATH`'e ekle, sonra `WATCH_CEVIZ_WHISPER_MODEL=large-v3` ile RTX 5070 Ti'de anlık çalışır.
- Türkçe sesli komutlar için öneri: GPU açılınca `large-v3`; CPU'da kalınırsa `small`/`medium`.

## Servis

`bash deploy/install.sh`, mevcut repo yolu, token ve STT ayarlarıyla
`watch-ceviz-backend.service` dosyasını otomatik üretir ve `systemd --user`
altında başlatır. `deploy/watch-ceviz-backend.service` yalnızca elle kurulum
için düzenlenmesi gereken bir şablondur; kişisel yollar veya gerçek token
içermez.
