import os
import json
from datetime import datetime
from dateutil import tz
import tweepy

STATE_PATH = os.path.join(os.path.dirname(__file__), 'state.json')
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
TWEETS_PATH = os.path.join(DATA_DIR, 'tweets.txt')
HOURS_PATH = os.path.join(DATA_DIR, 'hours.txt')

IST = tz.gettz('Europe/Istanbul')


def load_lines(path: str):
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return [ln.strip() for ln in f.readlines() if ln.strip()]


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"next_index": 0, "last_posted_iso": None}
    with open(STATE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_state(state):
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def now_ist():
    return datetime.now(tz=IST)


def current_hhmm(dt: datetime) -> str:
    return dt.strftime('%H:%M')


def should_post_this_minute(hours_list, dt: datetime) -> bool:
    # hours_list: ["08:00", "18:30", ...]
    return current_hhmm(dt) in set(hours_list)


def already_posted_this_minute(state, dt: datetime) -> bool:
    last = state.get('last_posted_iso')
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return False
    # aynı dakika içinde ikinci kez post etmeyi önle
    return current_hhmm(last_dt) == current_hhmm(dt) and last_dt.date() == dt.date()


def get_api_client():
    auth = tweepy.OAuth1UserHandler(
        os.environ['TW_CONSUMER_KEY'],
        os.environ['TW_CONSUMER_SECRET'],
        os.environ['TW_ACCESS_TOKEN'],
        os.environ['TW_ACCESS_TOKEN_SECRET']
    )
    return tweepy.API(auth)


def post_tweet(text: str, dry_run: bool = False):
    if dry_run:
        print(f"[DRY_RUN] Tweet: {text[:60]}…")
        return {"id": None}
    api = get_api_client()
    status = api.update_status(status=text)
    return {"id": getattr(status, 'id', None)}


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
    # Güvenlik: 280 sınırı
    if len(text) > 280:
        text = text[:279]

    try:
        resp = post_tweet(text, dry_run=dry_run)
        state['last_posted_iso'] = now.isoformat()
        state['next_index'] = idx + 1
        save_state(state)
        print(f"Posted index {idx}. Tweet ID: {resp['id']}")
    except tweepy.TweepyException as e:
        print('Tweepy error:', e)
    except Exception as e:
        print('Unexpected error:', e)


if __name__ == '__main__':
    main()
