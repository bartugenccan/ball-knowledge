# Ball Knowledge

EuroLeague oyuncuları için 1–20 ölçeğinde özellik puanları, maç ve aylık form takibi, takımların oyun stili, hücum hücum maç simülasyonu ve koçlar için set simülatörü. Ticari olmayan bir prototip.

```
engine/   Python: veri çekme, tablolar, puanlama, simülatörler, takım stili, FastAPI
web/      Next.js 16: arayüz (oyuncular, takımlar, maçlar, karşılaştırma, koç paneli, yöntem)
scripts/  npm run dev için kurulum kontrolü ve başlatma yardımcıları
data/     raw/ (ham JSON önbelleği) ve tables/ (Parquet), git'e girmez
```

## Çalıştırma

Gerekenler: [uv](https://docs.astral.sh/uv/) (Python 3.13'ü kendisi kurar) ve Node.js 20+.

### Hızlı başlangıç: hazır tablolarla

Veri repoda yok. Hazır `data/tables` klasörü (~13 MB) ayrıca paylaşılır. Kod güncellenince klasörü de güncel haliyle değiştirin: eski tablolar yeni API ile çalışmaz.

1. Klasörü repo köküne koyun. Doğru yerdeyse `data/tables/ratings_season.parquet` ve `data/tables/sim_calibration.json` dosyaları bulunur (`engine/` ve `web/` ile aynı seviyede bir `data/` klasörü).
2. Repo kökünde tek komut:

   ```bash
   npm run dev
   ```

   İlk çalıştırmada eksik bağımlılıkları kendisi kurar (npm paketleri ve Python ortamı, yaklaşık 1 dakika). Sonra API'yi ve web'i aynı terminalde başlatır. `git pull` sonrası bağımlılıklar değiştiyse yeniden kurar. Durdurmak için Ctrl+C.

   - Site: http://localhost:3000
   - API dokümanı: http://127.0.0.1:8000/docs

Ayrı terminallerde çalıştırmak isterseniz: `cd engine && uv run uvicorn bk.api.app:app --port 8000 --reload` ve `cd web && npm run dev`.

Bu yolla API, web, puan formülleri ve simülatör üzerinde çalışılabilir. Ham veri yalnızca tabloları yeniden üretmek için gerekir; bu, örneğin parse mantığı değiştiğinde olur.

### Veriyi baştan üretmek

```bash
cd engine
uv sync
uv run python -m bk.ingest E2024 E2025 E2026   # ham veriyi indirir; önbellekteki dosyaları tekrar çekmez
uv run python -m bk.model.build                # olaylar, şutlar, possession'lar, stint'ler
uv run python -m bk.ratings.build              # sezon, ay ve maç puanları
uv run python -m bk.sim.calibrate              # simülatör parametreleri (yorgunluk, clutch, ORB...)
uv run python scripts/audit/team_style_reliability.py   # hangi takım eğilimi gerçek? (E2024-E2025)
uv run python -m bk.team.style                 # takım sayfasındaki oyun stili
uv run python -m bk.match.calibrate            # maç simülasyonu lig sabitleri (E2024-E2025)
uv run python scripts/match/scorecard.py --rebuild     # tüm maçların karnesi (E2025 ve E2026)
uv run python scripts/match/misses.py          # büyük ıskaların maç maç incelemesi
uv run python scripts/match/fixtures.py        # gelecek maçların raporları ve kilitli tahminler
uv run uvicorn bk.api.app:app --port 8000

cd ../web
npm install
npm run dev                                    # http://localhost:3000, /api/* isteklerini 8000'e yönlendirir
```

Kaynak hız sınırı uyguluyor (~60 hızlı istekten sonra 429). İstemci 1,2 sn aralıkla istek atıyor; üç sezonu indirmek yaklaşık bir saat sürer. Yeni maçlar için aynı komutu tekrar çalıştırmak yeterli.

## Yayın

Site iki ücretsiz Vercel projesinde durur: `ball-knowledge-api` (FastAPI ve sunulan tablolar) ve `ball-knowledge-web` (Next.js, ortak şifreli). Veri GitHub'a gitmez, CLI ile yüklenir. Depoya gönderim otomatik yayın başlatmaz.

```bash
npx vercel login      # bir kez
npm run deploy        # ikisini de yayınlar
npm run deploy:api    # yalnızca veri ve motor
```

Ortam değişkenleri: API'de `BK_API_KEY`; web'de `API_URL`, `BK_API_KEY`, `SITE_PASSWORD`, `SITE_COOKIE_SECRET`. Yerelde bunlar tanımlı değilse site şifresiz, API anahtarsız çalışır.

Maçlar oynandıkça sonuçları eklemek için `engine` içinde `bk.ingest E2026`, `bk.model.build`, `bk.ratings.build`, `bk.team.style`, `scripts/match/fixtures.py` zincirini çalıştırın, sonra `npm run deploy:api`. Web'i yeniden yayınlamak gerekmez.

## Kontroller

```bash
cd engine
uv run pytest                          # parse, puan, simülatör, ingest, API
uv run python scripts/check_tables.py  # tablo doğrulaması; sorun varsa hata koduyla çıkar
uv run python scripts/audit/foundation.py  # veri temeli denetim raporu (data/audit/foundation.md)
uv run python scripts/audit/method.py      # küçültme, ölçek ve aralık denetimi (data/audit/method.md)
uv run python scripts/audit/stage3.py      # yeni özellik formülleri, eski puanlarla yan yana (data/audit/stage3.md)
uv run python scripts/audit/stage4.py      # şut özellikleri, eski puanlarla yan yana (data/audit/stage4.md)
uv run python scripts/audit/stage5.py      # savunma modelleri, eski puanlarla yan yana (data/audit/stage5.md)
uv run python scripts/audit/stage6.py      # clutch, oyun yükü, istikrar, maç puanı (data/audit/stage6.md)
uv run python scripts/audit/final_check.py # parametre seçiminde kullanılmayan sezonla son kontrol (data/audit/final_check.md)
uv run python scripts/audit/sim_compare.py # simülatör: eski ve yeni puanlar (data/audit/sim_compare.md)
uv run python scripts/audit/finishing_volume.py # Bitiricilik: hacim ve kendi yaratılan isabet (data/audit/finishing_volume.md)
uv run python scripts/audit/position_cards.py # mevki kartları: ham istatistik ve puan karşılaştırması (data/audit/position_cards.md)
uv run python -m bk.ratings.legacy_build   # denetim karşılaştırmaları için eski yöntemin tabloları (*_v1); ürün bunları okumaz
uv run python scripts/backtest.py E2025  # küçük örneklem düzeltmesi tahmin gücü
```

## Maç simülasyonu

Kod `engine/bk/match/` içinde. Ayarlar `Tuning` sınıfında (`sim.py`). E2025 ve E2026'nın ilk 9 haftasında seçildi, her değişiklik önceden yazılmış bir kuralla tek tek denendi. Yeni sınav, 10. haftadan sonra oynanan maçlar: tahminler maçtan önce kilitlenir ve `data/audit/match_predictions.csv` dosyasına eklenir.

- `data/audit/match_scorecard.md`, `match_scorecard_likely.md`: tüm maçlar, bilinen ve tahmini kadroyla
- `data/audit/match_misses.md`: büyük ıskalar tek tek, maçtan önce işaret var mıydı
- `data/audit/match_candidates.md`, `match_candidate_signals.md`: denenen her fikir, tutulan ve elenen
- `data/audit/match_story_card.md`: maçı kim bitiriyor, takım kendisi gibi mi oynuyor
- `data/audit/match_claim_card.md`: maç önü iddialarının tutma oranı, metnin dili buna göre
- `data/audit/match_rating_overlap.md`: simüle edilen oyuncular puanlarıyla örtüşüyor mu
- `data/audit/team_style_reliability.md`: hangi takım eğilimi cümle hakkı kazanıyor
- `scripts/match/score_effects.py`: skorun oyuna etkisinin ölçümü

Simülasyon kazanan tahmininde basit takım net reytingiyle başa baş: asıl katkısı maçın akışı ve oyuncu rakamları. Oyuncu çıkarıldığında şutlar diğerlerine verim kaybı olmadan geçtiği için "oyuncu olmasaydı" sorusu yanıtlanmaz.

## Veri ve sınırlar

- Kaynak: `live.euroleague.net/api` (PlaybyPlay, Points, Boxscore) ve `api-live.euroleague.net/v2` (fikstür).
- Açık veride savunmacı eşleşmesi, contest mesafesi ve play-type yok. "Pota Koruma" ve "Çevre Savunması" dolaylı tahmindir. Simülatördeki boş/contest farkı önsel değerdir. Hepsi arayüzde etiketli.
- FASTBREAK / SECOND_CHANCE bayrakları yalnızca isabetlerde bulunur. Şut bağlamı (yarı saha, geçiş, putback) bu yüzden possession zamanlamasından çıkarılır.
- EuroLeague'in resmi veri ve bahis hakları Sportradar'dadır. Yayına çıkmadan önce kullanım şartları kontrol edilmeli.
