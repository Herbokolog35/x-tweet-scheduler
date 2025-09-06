# src/poster.py
import os
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytz
import tweepy


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STATE_PATH = ROOT / "src" / "state.json"
TWEETS_PATH = DATA_DIR / "tweets.txt"
HOURS_PATH = DATA_DIR / "hours.txt"

TZ = pytz.timezone("Europe/Istanbul")


def env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def load_state():
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # İlk kez: son atılan index yok => -1
    return {
        "last_posted_index": -1,
        "last_posted_iso": None,
    }


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_lines(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Bulunamadı: {path}")
    with open(path, "r", encoding="utf-8") as f:
        # boş satırları ayıkla
        return [ln.strip() for ln in f.readlines() if ln.strip()]


def parse_hours(lines):
    hours = []
    for ln in lines:
        # Beklenen format: HH:MM (örn: 09:00)
        hhmm = ln.strip()
        try:
            hh, mm = hhmm.split(":")
            h = int(hh)
            m = int(mm)
            if 0 <= h < 24 and 0 <= m < 60:
                hours.append((h, m))
        except Exception:
            # hatalı satırları atla
            continue
    return hours


def is_now_within_window(now_tz: datetime, hours_hm, window_seconds: int) -> bool:
    """
    Şu an, planlı saatlerden herhangi birine +/- window_seconds içinde mi?
    Gecikmeli tetiklenmeler için 'bugün' ve 'dün' saatlerini kontrol ediyoruz.
    """
    if not hours_hm:
        return False

    for (h, m) in hours_hm:
        # bugün
        today_target = now_tz.replace(hour=h, minute=m, second=0, microsecond=0)
        # dün
        yesterday_target = (today_target - timedelta(days=1))
        # yarın (çok nadiren gerekli olabilir ama güvenlik için ekleyelim)
        tomorrow_target = (today_target + timedelta(days=1))

        for target in (yesterday_target, today_target, tomorrow_target):
            diff = abs((now_tz - target).total_seconds())
            if diff <= window_seconds:
                return True
    return False


def build_api():
    ck = os.getenv("TW_CONSUMER_KEY")
    cs = os.getenv("TW_CONSUMER_SECRET")
    at = os.getenv("TW_ACCESS_TOKEN")
    ats = os.getenv("TW_ACCESS_TOKEN_SECRET")

    if not all([ck, cs, at, ats]):
        raise RuntimeError(
            "Twitter anahtarları eksik. TW_CONSUMER_KEY / TW_CONSUMER_SECRET / "
            "TW_ACCESS_TOKEN / TW_ACCESS_TOKEN_SECRET ortam değişkenlerini tanımlayın."
        )

    auth = tweepy.OAuth1UserHandler(ck, cs, at, ats)
    return tweepy.API(auth)


def main():
    # Ortam değişkenleri
    DRY_RUN = env_bool("DRY_RUN", default=False)
    FORCE_POST_NOW = env_bool("FORCE_POST_NOW", default=False)
    WINDOW_SECONDS = int(os.getenv("WINDOW_SECONDS", "180"))

    now = datetime.now(TZ)
    print(f"Now (Europe/Istanbul): {now.isoformat()}")

    # Verileri yükle
    tweets = load_lines(TWEETS_PATH)
    hours_hm = parse_hours(load_lines(HOURS_PATH))

    state = load_state()
    last_posted_index = int(state.get("last_posted_index", -1))
    last_posted_iso = state.get("last_posted_iso")

    # Sıradaki index = en son atılan + 1
    next_index = last_posted_index + 1

    # Eğer tweet listesi biterse başa dön (sonsuz döngü için)
    if not tweets:
        print("Hiç tweet yok (data/tweets.txt boş). Çıkılıyor.")
        return

    if next_index >= len(tweets):
        print(f"next_index {next_index} tweet sayısını ({len(tweets)}) aştı, başa sarılıyor.")
        next_index = 0

    # Şimdi gönderim zamanı mı?
    should_post = FORCE_POST_NOW or is_now_within_window(now, hours_hm, WINDOW_SECONDS)

    # Durumu logla
    print(f"FORCE_POST_NOW={FORCE_POST_NOW} | DRY_RUN={DRY_RUN} | WINDOW_SECONDS={WINDOW_SECONDS}")
    print(f"last_posted_index={last_posted_index} | next_index={next_index}")
    if not FORCE_POST_NOW:
        print(f"Schedule matched? {'YES' if should_post else 'NO'}")

    if not should_post:
        print("Current time not in schedule. Exiting.")
        return

    tweet_text = tweets[next_index]
    print(f"Candidate tweet #{next_index}: {tweet_text[:80]}{'…' if len(tweet_text) > 80 else ''}")

    if DRY_RUN:
        print("[DRY_RUN] Tweet atılacak (simülasyon):", tweet_text[:80] + ("…" if len(tweet_text) > 80 else ""))
        # Dry-run’da da ilerlemek isteyebilirsiniz; pratikte üretime geçmeden akışı test etmeyi kolaylaştırır.
        state["last_posted_index"] = next_index
        state["last_posted_iso"] = now.isoformat()
        save_state(state)
        print(f"[DRY_RUN] last_posted_index -> {next_index} olarak güncellendi.")
        return

    # Gerçek gönderim
    try:
        api = build_api()
        status = api.update_status(status=tweet_text)
        tweet_id = getattr(status, "id", None)
        print(f"Tweet gönderildi. ID: {tweet_id}")

        # Başarıyla gönderildiyse state'i ilerlet
        state["last_posted_index"] = next_index
        state["last_posted_iso"] = now.isoformat()
        save_state(state)
        print(f"State kaydedildi: last_posted_index={next_index}")

    except tweepy.TweepyException as e:
        # Bazı Tweepy sürümleri error response’u farklı döndürebilir.
        msg = getattr(e, "response", None)
        text = ""
        if msg is not None and hasattr(msg, "text"):
            text = msg.text
        else:
            text = str(e)

        print("Tweepy error:", text)

        # Eğer “duplicate content” hatası geldiyse bu tweet’i atlanabilir.
        if "duplicate" in text.lower():
            print("Duplikasyon hatası: Bu içeriği zaten paylaştık, bir sonrakine geçiyoruz.")
            state["last_posted_index"] = next_index  # bu içeriği artık tüketilmiş say
            state["last_posted_iso"] = now.isoformat()
            save_state(state)
            print(f"State güncellendi (duplicate skip): last_posted_index={next_index}")
        else:
            print("Gönderim başarısız. State ilerletilmedi.")

    except Exception as e:
        print("Beklenmeyen hata:", repr(e))
        print("Gönderim başarısız. State ilerletilmedi.")


if __name__ == "__main__":
    main()