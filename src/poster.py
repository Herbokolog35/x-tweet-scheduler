# -*- coding: utf-8 -*-
"""
X Tweet Scheduler — v2 API sürümü (Tweepy Client.create_tweet)
- Zaman dilimi: Europe/Istanbul
- Kaynaklar:
  data/tweets.txt  -> her satır = 1 tweet (<= 280)
  data/hours.txt   -> HH:MM (24s), örn: 08:00, 18:30
- Durum (ilerleme) dosyası: src/state.json  (otomatik oluşturulur)
- DRY_RUN=true ise sadece log yazar, tweet göndermez.
"""

import os
import json
from datetime import datetime
from dateutil import tz
import tweepy

# Yollar
STATE_PATH = os.path.join(os.path.dirname(__file__), 'state.json')
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
TWEETS_PATH = os.path.join(DATA_DIR, 'tweets.txt')
HOURS_PATH = os.path.join(DATA_DIR, 'hours.txt')

# Zaman dilimi
IST = tz.gettz('Europe/Istanbul')


# ---------- Yardımcılar ----------
def load_lines(path: str):
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        # boş satırları at
        return [ln.strip() for ln in f if ln.strip()]


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"next_index": 0, "last_posted_iso": None}
    with open(STATE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_state(state: dict):
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def now_ist() -> datetime:
    return datetime.now(tz=IST)


def hhmm(dt: datetime) -> str:
    return dt.strftime('%H:%M')


def should_post_this_minute(hours_list, dt: datetime) -> bool:
    # hours_list ["08:00", "18:30", ...]
    return hhmm(dt) in set(hours_list)


def already_posted_this_minute(state: dict, dt: datetime) -> bool:
    last = state.get('last_posted_iso')
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return False
    # aynı gün ve aynı dakika tekrarını engelle
    return (hhmm(last_dt) == hhmm(dt)) and (last_dt.date() == dt.date())


# ---------- X API v2 İstemcisi ----------
def get_v2_client() -> tweepy.Client:
    """
    X API v2 ile tweet atmak için Tweepy Client.
    Gerekli yetkiler: App 'Read and write', kullanıcı Access Token'ları yazma izni.
    """
    return tweepy.Client(
        consumer_key=os.environ['TW_CONSUMER_KEY'],
        consumer_secret=os.environ['TW_CONSUMER_SECRET'],
        access_token=os.environ['TW_ACCESS_TOKEN'],
        access_token_secret=os.environ['TW_ACCESS_TOKEN_SECRET'],
        wait_on_rate_limit=True,
    )


def post_tweet(text: str, dry_run: bool = False) -> dict:
    """
    DRY_RUN etkinse sadece log yazar; değilse v2 `create_tweet` çağrılır.
    Dönen değer {"id": "..."} biçimindedir.
    """
    # X karakter sınırı
    if len(text) > 280:
        text = text[:279]

    if dry_run:
        print(f"[DRY_RUN] Tweet: {text[:160]}…")
        return {"id": None}

    client = get_v2_client()

    try:
        resp = client.create_tweet(text=text)
        tweet_id = resp.data.get("id") if resp and resp.data else None
        print("Tweet gönderildi. ID:", tweet_id)
        return {"id": tweet_id}
    except tweepy.Forbidden as e:
        # Tipik: 453 kodlu “erişim seviyesi yetersiz” hatası
        print("Tweepy Forbidden (403):", getattr(e, "api_codes", None), str(e))
        print("Not: Uygulamanızın planı/izinleri yazma iznini desteklemelidir (Basic/Pro + Read&Write).")
        raise
    except tweepy.HTTPException as e:
        print("Tweepy HTTPException:", getattr(e, "response", None))
        raise
    except Exception as e:
        print("Beklenmeyen hata:", e)
        raise


# ---------- Giriş Noktası ----------
def main():
    dry_run = os.getenv('DRY_RUN', 'false').lower() == 'true'

    tweets = load_lines(TWEETS_PATH)
    hours = load_lines(HOURS_PATH)

    if not tweets:
        print('No tweets found. Exiting.')
        return
    if not hours:
        print('No schedule hours found. Exiting.')
        return

    state = load_state()
    idx = state.get('next_index', 0)

    if idx >= len(tweets):
        print(f'All tweets sent ({len(tweets)}). Nothing to do.')
        return

    now = now_ist()
    print('Now (Europe/Istanbul):', now.isoformat())

    if not should_post_this_minute(hours, now):
        print('Current time not in schedule. Exiting.')
        return

    if already_posted_this_minute(state, now):
        print('Already posted in this minute. Exiting.')
        return

    text = tweets[idx]

    # Gönder
    try:
        resp = post_tweet(text, dry_run=dry_run)
        # Başarılı kabul edilen her durumda state ilerletilir (DRY_RUN dahil)
        state['last_posted_iso'] = now.isoformat()
        state['next_index'] = idx + 1
        save_state(state)
        print(f"Posted index {idx}. Tweet ID: {resp.get('id')}")
    except Exception:
        # Hata olursa state ilerletmeyin — tekrar denenir
        print("Gönderim başarısız oldu; state güncellenmedi.")


if __name__ == '__main__':
    main()
