# WedelNewsBot
Fetches news from https://www.wedel.de/ (official website of a town in the north of Germany) and posts them to Twitter.

## Live Bot

The bot is currently live and tweeting at: https://twitter.com/WedelNews

## Third party modules and changes

**Warning:** The `twitter` module has been changed to support 280 characters per tweet. I grew tired of waiting for an official update and changed it myself. If the official module has been changed by now, there shouldn't be any issues.

* `twitter`: https://github.com/bear/python-twitter/
  * `pip install python-twitter` **not** just `twitter`, that's a different module!
* `bs4`: https://pypi.python.org/pypi/beautifulsoup4
* `sklearn`: http://scikit-learn.org/
* `nltk`: http://nltk.org/
  * You have to download the stopwords package: `import nltk` and `nltk.download("stopwords")`

## Feature / ToDo List

- [x] Place configuration variables outside the code and deploy on GitHub :)
- [x] Use 280 character tweets.
- [x] Use "#ANZEIGE" hashtag in the beginning of tweets for paid advertisements.
- [X] Use machine learning to automatically classify articles and add hashtags accordingly.
- [ ] Add robustness against tinyurl errors (e.g. service unavailable).
- [ ] Use a database for storing the news instead of a JSON file.
- [ ] Remove old news that are no longer on the website to save space and speed things up.
- [ ] Optimize machine learning tag suggestions.

