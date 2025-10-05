# src/tools/twitter_client.py
from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List, Optional
import requests
from requests_oauthlib import OAuth1
from dotenv import load_dotenv

load_dotenv()

class RateLimitedError(RuntimeError):
    def __init__(self, message: str, reset_epoch: Optional[int], limit: Optional[int], remaining: Optional[int]):
        super().__init__(message)
        self.reset_epoch = reset_epoch
        self.limit = limit
        self.remaining = remaining


class TwitterClient:
    V2_BASE = "https://api.twitter.com/2"
    V11_BASE = "https://api.twitter.com/1.1"

    def __init__(
        self,
        bearer_token: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        timeout: int = 20,
        user_agent: str = "trading_bot_v2/1.0",
        debug: bool = False,
    ) -> None:
        self.bearer_token = (
            bearer_token
            or os.getenv("BEARER_TOKEN")
            or os.getenv("X_BEARER_TOKEN")
            or os.getenv("TWITTER_BEARER_TOKEN")
            or ""
        ).strip()
        self.api_key = (api_key or os.getenv("API_KEY") or "").strip()
        self.api_secret = (api_secret or os.getenv("API_SECRET") or "").strip()
        self.timeout = timeout
        self.user_agent = user_agent
        self.debug = debug

        if not self.bearer_token:
            raise ValueError("BEARER_TOKEN not set (try BEARER_TOKEN, X_BEARER_TOKEN, or TWITTER_BEARER_TOKEN).")

    def _bearer_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }

    def _oauth1(self) -> OAuth1:
        if not (self.api_key and self.api_secret):
            raise ValueError("API_KEY and API_SECRET are required for OAuth1 (v1.1) requests.")
        return OAuth1(self.api_key, self.api_secret)

    def _raise_http(self, r: requests.Response, context: str) -> None:
        # Special handling for 429 so the caller can decide what to do.
        if r.status_code == 429:
            limit = r.headers.get("x-rate-limit-limit")
            remaining = r.headers.get("x-rate-limit-remaining")
            reset = r.headers.get("x-rate-limit-reset")
            snippet = r.text[:500]
            raise RateLimitedError(
                message=f"{context} rate-limited (429). Body: {snippet}",
                reset_epoch=int(reset) if (reset and reset.isdigit()) else None,
                limit=int(limit) if (limit and limit.isdigit()) else None,
                remaining=int(remaining) if (remaining and remaining.isdigit()) else None,
            )

        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            snippet = r.text[:500]
            raise RuntimeError(f"{context} failed: {e}\nURL: {r.url}\nBody (first 500):\n{snippet}") from None

    def _get_v2(self, path: str, params: Optional[Dict] = None) -> Dict:
        url = path if path.startswith("http") else f"{self.V2_BASE}{path}"
        r = requests.get(url, headers=self._bearer_headers(), params=params or {}, timeout=self.timeout)
        if self.debug:
            print(f"[twitter v2] GET {r.url}")
            print(f"[twitter v2] status={r.status_code}")
        self._raise_http(r, "Twitter v2 request")
        return r.json()

    def _get_v11(self, path: str, params: Optional[Dict] = None) -> Dict:
        url = path if path.startswith("http") else f"{self.V11_BASE}{path}"
        r = requests.get(url, auth=self._oauth1(), params=params or {}, timeout=self.timeout)
        if self.debug:
            print(f"[twitter v1.1] GET {r.url}")
            print(f"[twitter v1.1] status={r.status_code}")
        self._raise_http(r, "Twitter v1.1 request")
        return r.json()

    def get_tweet(
        self,
        tweet_id: str,
        tweet_fields: Optional[List[str]] = None,
        user_fields: Optional[List[str]] = None,
        expansions: Optional[List[str]] = None,
    ) -> Dict:
        params: Dict[str, str] = {}
        if tweet_fields:
            params["tweet.fields"] = ",".join(tweet_fields)
        if user_fields:
            params["user.fields"] = ",".join(user_fields)
        if expansions:
            params["expansions"] = ",".join(expansions)
        return self._get_v2(f"/tweets/{tweet_id}", params=params)

    def search_recent_tweets(
        self,
        query: str,
        max_results: int = 50,
        next_token: Optional[str] = None,
        tweet_fields: Optional[List[str]] = None,
        user_fields: Optional[List[str]] = None,
        expansions: Optional[List[str]] = None,
    ) -> Dict:
        params: Dict[str, str] = {
            "query": query,
            "max_results": str(max(10, min(100, max_results))),
        }
        if next_token:
            params["next_token"] = next_token
        if tweet_fields:
            params["tweet.fields"] = ",".join(tweet_fields)
        if user_fields:
            params["user.fields"] = ",".join(user_fields)
        if expansions:
            params["expansions"] = ",".join(expansions)

        return self._get_v2("/tweets/search/recent", params=params)

    def search_recent_tweets_iter(
        self,
        query: str,
        limit: int = 100,
        tweet_fields: Optional[List[str]] = None,
        user_fields: Optional[List[str]] = None,
        expansions: Optional[List[str]] = None,
    ) -> Iterable[Dict]:
        fetched = 0
        next_token: Optional[str] = None

        while fetched < limit:
            batch_size = min(100, limit - fetched)
            data = self.search_recent_tweets(
                query=query,
                max_results=batch_size,
                next_token=next_token,
                tweet_fields=tweet_fields,
                user_fields=user_fields,
                expansions=expansions,
            )
            yield data

            meta = data.get("meta", {})
            result_count = int(meta.get("result_count") or 0)
            fetched += result_count
            next_token = meta.get("next_token")
            if not next_token or result_count == 0:
                break


# CLI unchanged (keep your single-tweet tester if you want)
if __name__ == "__main__":
    import argparse, json
    p = argparse.ArgumentParser(description="Twitter client smoke tests")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--tweet", help="Tweet ID or full URL")
    p.add_argument("--query", default='(cashtags:SPY OR $SPY OR SPY) lang:en -is:retweet -is:reply')
    p.add_argument("--limit", type=int, default=20)
    args = p.parse_args()

    client = TwitterClient(debug=args.debug)
    if args.tweet:
        import re
        m = re.search(r"(?:status|statuses)/(\d+)", args.tweet)
        tid = m.group(1) if m else args.tweet
        doc = client.get_tweet(tid, tweet_fields=["created_at","lang","public_metrics","author_id"])
        print(json.dumps(doc, indent=2)[:4000])
    else:
        page = client.search_recent_tweets(args.query, max_results=10)
        print(json.dumps(page, indent=2)[:4000])
