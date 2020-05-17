"""
    WedelNewsBot

    Fetches news from wedel.de and posts them to Twitter.
    Currently running at: https://twitter.com/WedelNews

"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import twitter
from twitter.error import TwitterError
import os
import logging
from tweet_tagger import TweetTagger


logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG)

NEWS_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "wedelnews.json")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "bot_config.json")


with open(CONFIG_FILE, "r") as f:
    bot_config = json.load(f)

T_CONSUMER_KEY = bot_config["T_CONSUMER_KEY"]
T_CONSUMER_SECRET = bot_config["T_CONSUMER_SECRET"]
T_ACCESS_TOKEN = bot_config["T_ACCESS_TOKEN"]
T_ACCESS_TOKEN_SECRET = bot_config["T_ACCESS_TOKEN_SECRET"]

# Experimental!
USE_HASHTAG_SUGGESTIONS = False
DEV_IGNORE_KNOWN_ARTICLES = False
DEV_STORE_NEW_ARTICLES = True

# Only set this to False when you are sure.
DEV_DONT_TWEET_YET = True

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
    logging.debug("Retrieving news from HTML...")
    soup = BeautifulSoup(html, "html.parser")
    news_sites = set()
    links = soup.find_all("a")
    logging.debug("Found {} links.".format(len(links)))
    for link in links:
        link_href = link.get("href")
        if "/newsdetail/" in link_href:
            if "https://www.wedel.de" == link_href[0:20]:
                link_href = link_href[20:]
            news_site_url = "https://www.wedel.de/{}".format(link_href)
            news_site_url = news_site_url.rsplit("#", maxsplit=1)[0]
            news_site_url = news_site_url.rsplit("?", maxsplit=1)[0]
            news_sites.add(news_site_url)
            logging.debug("Added news site URL: {}".format(news_site_url))
    logging.debug("Retrieved {} news site links from HTML.".format(len(news_sites)))
    return list(news_sites)


def get_article_from_html(html):
    logging.debug("Extracting article from HTML...")
    article = {}

    html = html.replace(u'\xa0', ' ')
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find(id="content")
    if content is None:
        logging.debug("Could not find #content, abortingL...")
        return None
    article["title"] = content.h1.text.strip()
    article["teaser"] = content.h2.text.strip()
    article["time"] = content.time.text.strip()

    images = []
    paragraphs = []
    for div in content.find_all("div"):
        if div.get("class") and "news-text-wrap" in div["class"]:
            for p in div.find_all("p"):
                paragraphs.append(p.text.strip())

    for pic in content.find_all("picture"):
        picture_text = pic.find("img").get("alt")
        picture_link = pic.find("img").get("src")
        picture_link = "https://www.wedel.de" + picture_link
        images.append([picture_link, picture_text])

    article["paragraphs"] = paragraphs
    article["images"] = images
    return article


def get_article(url):
    logging.debug("Retrieving online news page: {}".format(url))
    article_request = requests.get(url)
    logging.debug("Got response: {}".format(article_request.status_code))
    article = get_article_from_html(article_request.text)
    if article is None:
        return None
    logging.debug("Article information extracted.")
    article["url"] = url
    return article


def add_shortened_urls(articles):
    for a in articles:
        if "short_url" not in a:
            a["short_url"] = get_short_url(a["url"])
            logging.debug("Shortened '{}' to: {}".format(a["url"], a["short_url"]))


def get_all_articles():
    logging.debug("Retrieving all articles from website...")
    articles = []
    homepage_request = requests.get("https://www.wedel.de/")
    logging.debug("Got response: {}".format(homepage_request.status_code))
    news_sites = get_news_sites(homepage_request.text)

    if not DEV_IGNORE_KNOWN_ARTICLES and os.path.isfile(NEWS_FILE):
        logging.debug("Opening stored news file...")
        with open(NEWS_FILE, "r", encoding="utf-8") as f:
            try:
                known_articles = json.load(f)
                logging.debug("Done. Loaded {} articles.".format(len(known_articles)))
            except json.JSONDecodeError:
                logging.warning("Could not load news articles, malformed JSON. Starting fresh.")
                known_articles = {}
    else:
        logging.debug("No stored news file found, starting fresh...")
        known_articles = {}

    for i, ns in enumerate(news_sites):
        if get_last_url_part(str(ns)) not in known_articles:
            logging.debug("Processing news page {}".format(ns))
            article = get_article(ns)
            #TODO: This is a quick and dirty fix for an error where the URL is malformed.
            if article is not None:
                article["url"] = ns
                article["time_fetched"] = str(datetime.now())
                articles.append(article)
            else:
                logging.warning("Something went wrong with the URL: {}".format(ns))

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

    for art in articles:
        tags = []
        if tagger:
            tags = tagger.suggest_hashtags(art)

        summary = art["teaser"]

        # Not sure this is marked in the same way as before...
        """
        if summary == "ANZEIGE":
            summary = art["paragraphs"][1]
            a["title"] = "#ANZEIGE: {}".format(art["title"])
        """
        url = art["short_url"]
        tu_len = len(url) + len(art["title"])

        tagstring = ""
        ts_len = 0
        if len(tags) > 0:
            tagstring = " #{}".format(" #".join(tags))
            ts_len = len(tagstring)

        tweet = "{} — {} {}{}".format(art["title"], art["teaser"], url, tagstring)

        if len(tweet) > max_tweet_len:
            summary = summary[:(max_tweet_len - tu_len - ts_len - 9)] + "[...]"
            tweet = "{} — {} {}{}".format(art["title"], summary, url, tagstring)

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

    if DEV_STORE_NEW_ARTICLES and has_new:
        with open(NEWS_FILE, "w", encoding="utf-8") as f:
            json.dump(known_articles, f)


if __name__ == "__main__":
    logging.info("News File Path: {}".format(NEWS_FILE))

    article_list = get_all_articles()
    add_shortened_urls(article_list)

    #TODO: Do not load the classifier if there are no new articles...
    tagger = None
    if USE_HASHTAG_SUGGESTIONS:
        tagger = TweetTagger(NEWS_FILE, TRAIN_FILE, tag_map=TAG_MAP)
        # tagger.load_classifier(PRETRAINED_CLF)
        tagger.train_classifier()

    for new_article in get_unread_and_mark_as_read(article_list):
        live_tweet = make_tweets([new_article], tagger=tagger)[0]

        if not DEV_DONT_TWEET_YET:
            try:
                status = twapi.PostUpdate(live_tweet)
            except TwitterError as e:
                logging.error(e)

        logging.info("{} ::: {}".format(
            len(live_tweet.encode("ascii", "replace")),
            live_tweet.encode("ascii", "replace")))


    logging.info("Script finished.")
