# Ball Knowledge

EuroLeague oyuncuları için 1–20 ölçeğinde özellik puanları, maç ve aylık form takibi, ve koçlar için set simülatörü. Ticari olmayan bir prototip.

```
engine/   Python: veri çekme, tablolar, puanlama, simülatör, FastAPI
web/      Next.js 16: arayüz (oyuncular, takımlar, karşılaştırma, koç paneli, yöntem)
data/     raw/ (ham JSON önbelleği) ve tables/ (Parquet), git'e girmez
```

## Çalıştırma

```bash
cd engine
uv sync
uv run python -m bk.ingest E2024 E2025 E2026   # ham veriyi indirir; önbellekteki dosyaları tekrar çekmez
uv run python -m bk.model.build                # olaylar, şutlar, possession'lar, stint'ler
uv run python -m bk.ratings.build              # sezon, ay ve maç puanları
uv run python -m bk.sim.calibrate              # simülatör parametreleri (yorgunluk, clutch, ORB...)
uv run uvicorn bk.api.app:app --port 8000

cd ../web
npm install
npm run dev                                    # http://localhost:3000, /api/* isteklerini 8000'e yönlendirir
```

Kaynak hız sınırı uyguluyor (~60 hızlı istekten sonra 429). İstemci 1,2 sn aralıkla istek atıyor; üç sezonu indirmek yaklaşık bir saat sürer. Yeni maçlar için aynı komutu tekrar çalıştırmak yeterli.

## Kontroller

```bash
cd engine
uv run pytest                          # parse, puan, simülatör, ingest, API
uv run python scripts/check_tables.py  # tablolar resmi kutu skorlarıyla tutarlı mı
uv run python scripts/backtest.py E2025  # küçük örneklem düzeltmesi tahmin gücü
```

## Veri ve sınırlar

- Kaynak: `live.euroleague.net/api` (PlaybyPlay, Points, Boxscore) ve `api-live.euroleague.net/v2` (fikstür).
- Açık veride savunmacı eşleşmesi, contest mesafesi ve play-type yok. "Pota Koruma" ve "Çevre Savunması" dolaylı tahmindir. Simülatördeki boş/contest farkı önsel değerdir. Hepsi arayüzde etiketli.
- FASTBREAK / SECOND_CHANCE bayrakları yalnızca isabetlerde bulunur. Şut bağlamı (yarı saha, geçiş, putback) bu yüzden possession zamanlamasından çıkarılır.
- EuroLeague'in resmi veri ve bahis hakları Sportradar'dadır. Yayına çıkmadan önce kullanım şartları kontrol edilmeli.
