"""The attributes the product shows, and how each one is presented."""

from __future__ import annotations

from bk.ratings.attributes import Attribute
from bk.ratings.defense import DEFENSE_ATTRIBUTES, DEFENSE_K
from bk.ratings.mental import MENTAL_ATTRIBUTES, MENTAL_SPECS
from bk.ratings.metrics_v2 import ATTRIBUTES_V2, INFO_METRICS, SPECS, TIER_ATTRIBUTES

ORDER = ("finishing", "mid_range", "three_point", "free_throw", "shot_creation", "passing", "ball_security", "drawing_fouls",
         "off_rebounding", "def_rebounding", "steals", "shot_blocking", "rim_protection", "perimeter_defense", "discipline",
         "team_defense", "stamina", "consistency")

_ALL = {a.key: a for a in (*ATTRIBUTES_V2, *DEFENSE_ATTRIBUTES, *MENTAL_ATTRIBUTES)}
RATING_ATTRIBUTES: tuple[Attribute, ...] = tuple(_ALL[k] for k in ORDER)
ATTR_BY_KEY = {a.key: a for a in RATING_ATTRIBUTES}

PRIOR_K: dict[str, float] = {
    **{m: s.k for m, s in SPECS.items() if m not in INFO_METRICS},
    "three_value": SPECS["three_pct"].k,  # as uncertain as the accuracy inside it
    **DEFENSE_K,
    **{m: s.k for m, s in MENTAL_SPECS.items()},
}


# What each rating means, in basketball terms. Keep these in step with the formulas above.
# what: the question it answers. how: what goes in. note: how to read it, when that is not obvious.
HINTS: dict[str, dict[str, str]] = {
    "finishing": {
        "what": "Pota çevresinde ne kadar sorumluluk alıp ne kadar verimli bitiriyor?",
        "how": "Pota ve boyalı alan isabeti (%40), bu bölgeden şut kullanma sıklığı (%40) ve asistsiz isabetler (%20). Putback ve hızlı hücum gibi kolay şutlar buna göre düzeltilir.",
        "note": "Az şutla yüksek yüzde tepeye çıkmaz: kolay şut bekleyen bitirici ile bitirişi kendi yaratan aynı değildir.",
    },
    "mid_range": {
        "what": "Boyalı alan dışından ikilikte ne kadar tehlikeli?",
        "how": "Orta mesafe isabeti (%80) ve kullanma sıklığı (%20). Bu şutlar az olduğu için oyuncunun serbest atışı ve boyu da tahmine girer.",
        "note": "Veri ince ayrım için yetmediğinden Düşük, Orta veya Yüksek gösterilir.",
    },
    "three_point": {
        "what": "Üçlük tehdidi ne kadar büyük?",
        "how": "Sıradan bir şutçuya göre üçlükten maç başına fazladan ürettiği sayı: 3 × maç başına deneme × (isabet − %32). Deneme ve isabet çarpıldığı için ikisi de tek başına yetmez. Periyot sonu umut atışları sayılmaz. Üçlük yüzdesi yavaş oturduğu için önceki sezonlar ve serbest atış becerisi de hesaba girer.",
        "note": "Bu yüzden bu sezonun yüzdesiyle puan birebir aynı sırada olmayabilir. Az deneyen isabetli bir şutçu, çok deneyen isabetli bir şutçunun altında kalır.",
    },
    "free_throw": {
        "what": "Çizgide ne kadar güvenilir?",
        "how": "Serbest atış yüzdesi. Önceki sezonlar da sayılır; çok az atışta oyuncunun mevkisindeki tipik yüzdeye yaklaşır.",
        "note": "Serbest atışı ne sıklıkla kazandığı Faul Alma'da ölçülür.",
    },
    "shot_creation": {
        "what": "Sayıyı kendi yaratabiliyor mu?",
        "how": "Asistsiz attığı sayı, 100 hücumda. Putback ve umut atışları sayılmaz.",
    },
    "passing": {
        "what": "Takım arkadaşlarına ne kadar sayı üretiyor?",
        "how": "Sahadayken takım arkadaşlarının isabetlerindeki asist payı (%60) ve asistlerinden doğan sayı, 100 hücumda (%40). Üçlük asisti ikilik asistinden değerlidir.",
        "note": "Kaçan şutla biten paslar veride yok.",
    },
    "ball_security": {
        "what": "Topu çok kullanırken ne kadar az kaybediyor?",
        "how": "Top teması başına top kaybı (%50) ve top kullanımı, 100 hücumda (%50). Top teması: şut, serbest atış, top kaybı ve asist.",
        "note": "Topa az dokunan oyuncu az kaybettiği için ödüllendirilmez.",
    },
    "drawing_fouls": {
        "what": "Rakibi ne kadar faule zorluyor?",
        "how": "Hücumda aldığı faul (%50) ve kazandığı serbest atış serisi (%50), 100 hücumda. Teknik ve sportmenlik dışı faul atışları sayılmaz.",
    },
    "off_rebounding": {
        "what": "Takımının kaçırdığı şutlarda ribaundun ne kadarını topluyor?",
        "how": "Sahadayken oluşan hücum ribaundu fırsatlarındaki payı. Oyuncuya yazılmayan takım ribaundları fırsat sayılmaz.",
    },
    "def_rebounding": {
        "what": "Rakibin kaçırdığı şutlarda ribaundun ne kadarını topluyor?",
        "how": "Sahadayken oluşan savunma ribaundu fırsatlarındaki payı. Oyuncuya yazılmayan takım ribaundları fırsat sayılmaz.",
    },
    "steals": {
        "what": "Savunmada ne sıklıkla top çalıyor?",
        "how": "Top çalma, oynadığı 100 savunma hücumunda. Önceki sezonlar da sayılır.",
        "note": "Oran olduğu için az süre alan oyuncu da yüksek çıkabilir; maçta 10 dakikanın altındakiler liderlik listesine girmez.",
    },
    "shot_blocking": {
        "what": "Rakibin ikiliklerinin ne kadarını blokluyor?",
        "how": "Sahadayken rakibin ikilik denemelerindeki blok payı. Üçlük blokları sayılmaz.",
    },
    "rim_protection": {
        "what": "Potayı ne kadar koruyor?",
        "how": "Blok payı (%50) ve sahadayken rakibin boyalı alan sayısına etkisi (%50). Bu etki, takım arkadaşlarından ve takımın genel savunmasından ayrılarak hesaplanır.",
        "note": "Tahminidir: kimin kimi savunduğu veride yok. Sezon başında az veri görünür.",
    },
    "perimeter_defense": {
        "what": "Çevrede üçlükleri ne kadar engelliyor?",
        "how": "Sahadayken rakibin üçlük denemesine etkisi (%50), top çalma (%30) ve rakibin üçlük isabeti (%20). Üçlük isabeti savunmacının elinde olmadığı için az ağırlık alır.",
        "note": "Tahminidir ve zayıf bir ölçümdür: takım değiştiren oyuncularda kalıcı değil. Bu yüzden Düşük, Orta veya Yüksek gösterilir.",
    },
    "discipline": {
        "what": "Faul belasına girmeden oynayabiliyor mu?",
        "how": "Yaptığı faul, oynadığı 100 hücumda. Hücum faulleri dahil; sportmenlik dışı, teknik ve diskalifiye faulleri iki kat sayılır.",
        "note": "Düşük faul iyidir. Maç başına değil, sahada kalınan süreye göre bakılır.",
    },
    "team_defense": {
        "what": "Sahadayken takımı daha az sayı mı yiyor?",
        "how": "Sahadaki beşlilerin yediği sayılardan, takım arkadaşlarının etkisi ayrılarak bulunur. Önceki sezon da hesaba girer.",
        "note": "Tahminidir ve geniş aralıklıdır: küçük puan farklarını fazla yorumlamayın.",
    },
    "stamina": {
        "what": "Takımında ne kadar oyun yükü taşıyor?",
        "how": "Takım maçı başına dakika (%60) ve dakikalarının 7+ dakika kesintisiz serilerde geçen payı (%40).",
        "note": "Fiziksel dayanıklılık ölçümü değildir; antrenörün rotasyonunu da yansıtır.",
    },
    "consistency": {
        "what": "Maçtan maça ne kadar aynı oyuncu?",
        "how": "Oynadığı süreye göre maç üretiminin dalgalanması, aynı üretim seviyesindeki oyuncularla karşılaştırılır. Çok üreten oyuncu doğal dalgalanmasından ötürü cezalandırılmaz.",
        "note": "20 maçtan önce değerlendirilmez.",
    },
}


def display_kind(key: str) -> str:
    return "tier" if key in TIER_ATTRIBUTES else "number"
