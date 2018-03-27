"""
    WedelNewsBot

    Fetches news from wedel.de and posts them to Twitter.
    Currently running at: https://twitter.com/WedelNews

"""

import requests
import re
from bs4 import BeautifulSoup
import json
from datetime import datetime
import twitter
from twitter.error import TwitterError
import os

from tweet_tagger import TweetTagger


NEWS_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "wedelnews.json")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "bot_config.json")

with open(CONFIG_FILE, "r") as f:
    bot_config = json.load(f)

T_CONSUMER_KEY = bot_config["T_CONSUMER_KEY"]
T_CONSUMER_SECRET = bot_config["T_CONSUMER_SECRET"]
T_ACCESS_TOKEN = bot_config["T_ACCESS_TOKEN"]
T_ACCESS_TOKEN_SECRET = bot_config["T_ACCESS_TOKEN_SECRET"]

# Experimental!
USE_HASHTAG_SUGGESTIONS = True
TRAIN_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "training.json")
PRETRAINED_CLF = os.path.join(os.path.dirname(os.path.realpath(__file__)), "pretrained_classifier.pkl")
TAG_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "tag_map.json")
with open(TAG_FILE, "r") as f:
    TAG_MAP = json.load(f)


twapi = twitter.Api(consumer_key=T_CONSUMER_KEY,
                    consumer_secret=T_CONSUMER_SECRET,
                    access_token_key=T_ACCESS_TOKEN,
                    access_token_secret=T_ACCESS_TOKEN_SECRET,
                    input_encoding="utf-8")


def get_news_sites(html):
    print("Retrieving news pages...")
    soup = BeautifulSoup(html, "html.parser")
    news_sites = set()
    links = soup.find_all("a")
    for link in links:
        link_href = link.get("href")
        if "/newsdetail/news/" in link_href:
            news_site_url = "https://www.wedel.de/{}".format(link_href)
            news_site_url = news_site_url.rsplit("#", maxsplit=1)[0]
            news_site_url = news_site_url.rsplit("?", maxsplit=1)[0]

            news_sites.add(news_site_url)
    return list(news_sites)


def get_article_from_html(html):
    article = {}
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find(id="content")
    article["title"] = content.h1.text.strip()
    images = [i.get("src") for i in content.find_all("img")]
    paragraphs = []
    image_captions = []
    for p in content.find_all("p"):
        if p.get("class") and "news-single-imgcaption" in p["class"]:
            if p.text.strip():
                image_captions.append(p.text.strip())
        else:
            if p.text.strip():
                paragraphs.append(p.text.strip())
    article["paragraphs"] = paragraphs
    article["images"] = list(zip(images, image_captions))

    date_new = re.search(r"(\d+.\d+.\d+)", " ".join(paragraphs[-2:]))
    if date_new:
        article["date"] = date_new.group(1)

    return article


def get_article(url):
    article_request = requests.get(url)
    article = get_article_from_html(article_request.text)
    article["url"] = url
    return article


def add_shortened_urls(articles):
    for a in articles:
        if "short_url" not in a:
            a["short_url"] = get_short_url(a["url"])
            print("Shortened '{}' to: {}".format(a["url"], a["short_url"]))


def get_all_articles():
    print("Retrieving all articles...")
    articles = []
    homepage_request = requests.get("https://www.wedel.de/")
    news_sites = get_news_sites(homepage_request.text)

    if os.path.isfile(NEWS_FILE):
        with open(NEWS_FILE, "r", encoding="utf-8") as f:
            try:
                known_articles = json.load(f)
            except json.JSONDecodeError:
                known_articles = {}
    else:
        known_articles = {}

    for i, ns in enumerate(news_sites):
        if get_last_url_part(str(ns)) not in known_articles:
            print("Processing {}".format(ns))
            article = get_article(ns)
            article["url"] = ns
            article["time_fetched"] = str(datetime.now())
            articles.append(article)

    return articles


def get_last_url_part(url):
    return url.rsplit("/", maxsplit=1)[1]


def get_short_url(url):
    return requests.get("http://tinyurl.com/api-create.php?url={0}".format(url)).text


def get_tweet_length(article):
    return sum(map(len, [article["paragraphs"][0], article["title"]])) + 23


def make_tweets(articles, tagger=None):
    max_tweet_len = 272
    tweets = []

    for a in articles:
        tags = []
        if tagger:
            tags = tagger.suggest_hashtags(a)

        summary = a["paragraphs"][0]
        if summary == "ANZEIGE":
            summary = a["paragraphs"][1]
            a["title"] = "#ANZEIGE: {}".format(a["title"])
        url = a["short_url"]

        tu_len = len(url) + len(a["title"])

        tagstring = ""
        ts_len = 0
        if len(tags) > 0:
            tagstring = " #{}".format(" #".join(tags))
            ts_len = len(tagstring)

        tweet = "{} — {} {}{}".format(a["title"], summary, url, tagstring)

        if len(tweet) > max_tweet_len:
            summary = summary[:(max_tweet_len - tu_len - ts_len - 9)] + "[...]"
            tweet = "{} — {} {}{}".format(a["title"], summary, url, tagstring)
        tweet = "{} #Wedel".format(tweet)
        tweets.append(tweet)

    return tweets


def get_unread_and_mark_as_read(articles):
    has_new = False

    if os.path.isfile(NEWS_FILE):
        with open(NEWS_FILE, "r", encoding="utf-8") as f:
            try:
                known_articles = json.load(f)
            except json.JSONDecodeError:
                known_articles = {}
    else:
        known_articles = {}
        has_new = True

    for a in articles:
        last_url_part = get_last_url_part(a["url"])
        if last_url_part not in known_articles:
            known_articles[last_url_part] = a
            has_new = True
            yield a

    if has_new:
        with open(NEWS_FILE, "w", encoding="utf-8") as f:
            json.dump(known_articles, f)
        pass


if __name__ == "__main__":
    print("News File Path: {}".format(NEWS_FILE))

    article_list = get_all_articles()
    add_shortened_urls(article_list)
    print()

    #TODO: Do not load the classifier if there are no new articles...
    tagger = None
    if USE_HASHTAG_SUGGESTIONS:
        tagger = TweetTagger(NEWS_FILE, TRAIN_FILE, tag_map=TAG_MAP)
        # tagger.load_classifier(PRETRAINED_CLF)
        tagger.train_classifier()

    for new_article in get_unread_and_mark_as_read(article_list):
        live_tweet = make_tweets([new_article], tagger=tagger)[0]

        try:
            # Only run this on the live server.
            # status = twapi.PostUpdate(live_tweet)
            pass
        except TwitterError as e:
            print(e)

        print("Tweeting: {} --> {}".format(
            new_article["title"].encode("ascii", "replace"),
            new_article["short_url"].encode("ascii", "replace")))
        print("{} ::: {}".format(
            len(live_tweet.encode("ascii", "replace")),
            live_tweet.encode("ascii", "replace")))
        print()

    print("Script finished.")
