import os
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytz
import tweepy  # v2 Client kullanıyoruz

# ---------- Ortam değişkenleri güvenli parse ----------
def env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}

def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

# Zamanlama
TZ_NAME = os.getenv("TZ", "Europe/Istanbul")
TZ = pytz.timezone(TZ_NAME)

WINDOW_SECONDS = env_int("WINDOW_SECONDS", 60)            # 1 dakikalık pencere
FORCE_POST_NOW = env_bool("FORCE_POST_NOW", False)        # manuel tetikte set edilebilir
DRY_RUN       = env_bool("DRY_RUN", False)                # gerçek gönderim için false olmalı

# Dosya yolları
DATA_DIR   = Path("data")
SRC_DIR    = Path("src")
TWEETS_TXT = DATA_DIR / "tweets.txt"
HOURS_TXT  = DATA_DIR / "hours.txt"
STATE_JSON = SRC_DIR / "state.json"

def load_lines(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]

def load_state():
    if STATE_JSON.exists():
        with STATE_JSON.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"next_index": 0, "last_posted_iso": None}

def save_state(state):
    STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    with STATE_JSON.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def in_schedule_window(now_aware, hours_list):
    """hours.txt içindeki saat:dakika değerlerinden herhangi biriyle now arasında
    ±WINDOW_SECONDS penceresi var mı?"""
    if not hours_list:
        return True  # saat listesi boşsa zaman kısıtı yok demektir

    for hhmm in hours_list:
        try:
            hh, mm = hhmm.split(":")
            scheduled = now_aware.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            delta = abs((now_aware - scheduled).total_seconds())
            if delta <= WINDOW_SECONDS:
                return True
        except Exception:
            # satır hatası varsa atla
            continue
    return False

def build_client():
    # X (Twitter) API v2 tweet atmak için OAuth1 kimlik bilgileriyle Client
    consumer_key = os.getenv("TW_CONSUMER_KEY")
    consumer_secret = os.getenv("TW_CONSUMER_SECRET")
    access_token = os.getenv("TW_ACCESS_TOKEN")
    access_token_secret = os.getenv("TW_ACCESS_TOKEN_SECRET")

    missing = [n for n, v in {
        "TW_CONSUMER_KEY": consumer_key,
        "TW_CONSUMER_SECRET": consumer_secret,
        "TW_ACCESS_TOKEN": access_token,
        "TW_ACCESS_TOKEN_SECRET": access_token_secret,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"Eksik gizli anahtar(lar): {', '.join(missing)}")

    return tweepy.Client(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        wait_on_rate_limit=True,
    )

def main():
    now = datetime.now(TZ)
    print(f"Now ({TZ_NAME}): {now.isoformat()}")
    print(f"FORCE_POST_NOW={FORCE_POST_NOW}  DRY_RUN={DRY_RUN}  WINDOW_SECONDS={WINDOW_SECONDS}")

    tweets = load_lines(TWEETS_TXT)
    hours  = load_lines(HOURS_TXT)
    state  = load_state()

    if not tweets:
        print("tweets.txt boş veya bulunamadı. Çıkıyorum.")
        return

    idx = state.get("next_index", 0)
    if idx >= len(tweets):
        print(f"Tüm tweetler tüketildi (next_index={idx}, toplam={len(tweets)}). Çıkıyorum.")
        return

    # Zaman kontrolü (manuel tetikte FORCE_POST_NOW ile atlanabilir)
    if not FORCE_POST_NOW:
        if not in_schedule_window(now, hours):
            print("Current time not in schedule. Exiting.")
            return
    else:
        print("FORCE_POST_NOW=true → zaman kontrolü atlandı.")

    text = tweets[idx]
    print(f"Seçilen index: {idx} / {len(tweets)-1}")

    if DRY_RUN:
        print(f"[DRY_RUN] Tweet (gönderilmeyecek): {text[:120]}{'…' if len(text) > 120 else ''}")
        # Simülasyonda da state ilerletelim ki tekrar aynı tweette kalmasın
        state["next_index"] = idx + 1
        state["last_posted_iso"] = now.isoformat()
        save_state(state)
        print(f"Posted index {idx} (simülasyon). Tweet ID: None")
        return

    # Gerçek gönderim
    try:
        client = build_client()
        resp = client.create_tweet(text=text)
        tweet_id = getattr(resp, "data", {}).get("id") if hasattr(resp, "data") else None
        print(f"Tweet gönderildi. ID: {tweet_id}")

        # state güncelle
        state["next_index"] = idx + 1
        state["last_posted_iso"] = now.isoformat()
        save_state(state)
        print(f"Posted index {idx}. Next index: {state['next_index']}")
    except tweepy.Forbidden as e:
        # Örn: 403 duplicate / yetki seviyesi
        print(f"Tweepy Forbidden (403): {e}")
        print("Not: Duplicate içerik veya yetersiz erişim seviyesi olabilir.")
        raise
    except tweepy.Unauthorized as e:
        print(f"Tweepy Unauthorized (401): {e}")
        print("Not: Anahtar/Token değerlerini kontrol edin (Read+Write yetkisi).")
        raise
    except Exception as e:
        print(f"Beklenmeyen hata: {e}")
        raise

if __name__ == "__main__":
    main()