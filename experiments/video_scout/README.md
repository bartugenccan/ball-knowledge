# Video set testi

Soru: Yapay zeka, koçun kliplerinden işe yarar bir set notu çıkarıp koça zaman kazandırıyor mu?

Bu klasör uygulamadan bağımsızdır ve EuroLeague verisini kullanmaz. Klipler, etiketler ve sonuçlar git'e girmez.

## Hazırlık

Gerekenler: [uv](https://docs.astral.sh/uv/), ffmpeg ve Claude API erişimi (`ANTHROPIC_API_KEY`).

1. Görüntü ve veri kullanımı için kulübün yazılı iznini alın.
2. Klipleri `clips/` altına koyun. Dosya adı önemli değil, modele gönderilmez.
3. `templates/` içindeki dosyaları bu klasöre kopyalayıp doldurun: `sets.csv`, `labels.csv`, `review.csv`.

## Etiketler

Koç etiketleri yapay zekanın çıktısını görmeden önce doldurur.

| Sütun | Değerler |
|---|---|
| `split` | `dev` (yaklaşık 20 klip, ayar için) veya `test` (kalanı, son karar için) |
| `set_name` | `sets.csv` içindeki ad, listede yoksa `bilinmiyor` |
| `primary_action` | `pick_and_roll`, `handoff`, `off_ball_screen`, `post_up`, `isolation`, `cut`, `transition`, `other` |
| `shot_zone` | `rim`, `paint`, `mid`, `corner3`, `above_break3`, `none` |
| `result` | `made`, `missed`, `turnover`, `foul`, `other` |
| `finisher_jersey` | Forma numarası, yoksa `bilinmiyor` |

Kliplerin yaklaşık %15'i listede olmayan set veya serbest hücum olsun. Sistemin "bilmiyorum" diyebildiği böyle ölçülür.

## Çalıştırma

```bash
cd experiments/video_scout
uv run scout.py run --split dev --dry-run    # API çağrısı yok: kare sayısı ve tahmini maliyet
uv run scout.py run --split dev              # varsayılan bütçe sınırı 5 dolar, --max-usd ile değişir
uv run scout.py score --split dev
```

Ayarları yalnızca `dev` kliplerine bakarak değiştirin ve her denemeye `--run` ile yeni ad verin. Ayarlar bitince `test` kliplerini **bir kez** çalıştırın. Sonucu görüp ayarı değiştirirseniz o klipler artık test sayılmaz.

## Zaman ölçümü

Koç `test` kliplerinin yarısını sıfırdan, diğer yarısını yapay zeka taslağını düzelterek not eder. Her set iki grupta da bulunsun. Bir klip yalnızca bir modda ölçülür, çünkü ikinci izleyiş zaten daha hızlı olur. Süreleri `review.csv` dosyasına yazın. Taslağı düzelttiği kliplere 1–5 arası faydalılık puanı da versin.

## Karar

| Ölçüt | Geçme şartı |
|---|---|
| Koçun kazandığı zaman | En az %50 |
| Yüksek güvenle verilen yanlış set | %10'un altında, en az 10 yüksek güvenli cevapla |

Bu eşikler ilk hipotezdir. 60–100 klipte doğruluk aralıkları geniş olur, bu yüzden sonuç ürünün çalıştığının kanıtı değil, devam edip etmeme kararıdır.

## Testler

```bash
uv run --with pytest --with "anthropic>=1,<2" pytest test_scout.py
```
