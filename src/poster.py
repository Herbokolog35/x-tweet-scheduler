import os
import tweepy
import pytz
from datetime import datetime, timedelta

# Tweet metinlerinin bulunduğu dosya
TWEETS_FILE = "data/tweets.txt"
# Saatlerin bulunduğu dosya (HH:MM formatında, her satırda bir saat)
HOURS_FILE = "data/hours.txt"
# Durum dosyası (hangi tweetin sırada olduğunu takip eder)
STATE_FILE = "src/state.json"

import json

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"next_index": 0, "last_posted_iso": None}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def load_tweets():
    with open(TWEETS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def load_hours():
    with open(HOURS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def should_post_now(now, scheduled_times, tolerance_minutes=10):
    """
    Şu anki saat belirlenen zamanlardan ±tolerance_minutes içinde mi?
    """
    for st in scheduled_times:
        try:
            scheduled = now.replace(hour=int(st.split(":")[0]),
                                    minute=int(st.split(":")[1]),
                                    second=0, microsecond=0)
            if abs(now - scheduled) <= timedelta(minutes=tolerance_minutes):
                return True
        except Exception:
            continue
    return False

def main():
    # Ortam değişkenleri
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    force_post = os.getenv("FORCE_POST_NOW", "false").lower() == "true"

    # Türkiye saat dilimi
    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.now(tz)
    print(f"Now (Europe/Istanbul): {now.isoformat()}")

    tweets = load_tweets()
    hours = load_hours()
    state = load_state()

    # Tweet seç
    idx = state["next_index"] % len(tweets)
    tweet = tweets[idx]

    # Saat kontrolü
    if not force_post:
        if not should_post_now(now, hours, tolerance_minutes=10):
            print("Current time not in schedule. Exiting.")
            return

    # Tweepy v2 client
    client = tweepy.Client(
        consumer_key=os.getenv("TW_CONSUMER_KEY"),
        consumer_secret=os.getenv("TW_CONSUMER_SECRET"),
        access_token=os.getenv("TW_ACCESS_TOKEN"),
        access_token_secret=os.getenv("TW_ACCESS_TOKEN_SECRET")
    )

    if dry_run:
        print(f"[DRY_RUN] Tweet: {tweet[:50]}…")
        tweet_id = None
    else:
        try:
            response = client.create_tweet(text=tweet)
            tweet_id = response.data.get("id")
            print(f"Tweet posted. ID: {tweet_id}")
        except Exception as e:
            print(f"Tweepy error: {e}")
            return

    # Durumu güncelle
    state["next_index"] = idx + 1
    state["last_posted_iso"] = now.isoformat()
    save_state(state)
    print(f"Posted index {idx}. Tweet ID: {tweet_id}")

if __name__ == "__main__":
    main()
