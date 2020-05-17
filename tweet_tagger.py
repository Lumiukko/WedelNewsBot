import json
import os
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import MultiLabelBinarizer
import nltk
from sklearn.externals import joblib


class TweetTagger:

    def __init__(self, news_file, training_file, tag_map=dict()):
        self.news_file = news_file
        self.training_file = training_file
        self.tag_map = tag_map
        self.classifier = None
        self.mlb = None
        self.category_map = None
        self.category_map_inverse = None

    @staticmethod
    def pre_process(news):
        img_captions = []
        for img in news["images"]:
            if len(img) > 1:
                img_captions.append(img[1])
        all_captions = "\n".join(img_captions)
        all_text = "\n".join(news["paragraphs"])

        teaser = ("" if "teaser" not in news else news["teaser"])

        all_content = "\n\n".join([news["title"], teaser, all_text, all_captions])
        return all_content

    def load_classifier(self, classifier_file):
        with open(self.news_file, "r") as f:
            news = json.load(f)
        with open(self.training_file, "r") as f:
            train = json.load(f)

        categories = {}
        for i, n in enumerate(train):
            cs = train[n].split(sep=",")
            for c in cs:
                cat = c.strip()
                if len(cat) > 1:
                    categories.setdefault(cat, 0)

        cat_map = dict(zip(categories.keys(), range(len(categories))))
        cat_map_inv = dict(zip(range(len(categories)), categories.keys()))

        self.category_map = cat_map
        self.category_map_inverse = cat_map_inv

        train_data = []
        train_target = []

        for i, n in enumerate(train):
            all_content = self.pre_process(news[n])

            targets = []

            cs = train[n].split(sep=",")
            for c in cs:
                cat = c.strip()
                if len(cat) > 1:
                    targets.append(cat_map[cat])

            train_data.append(all_content)
            train_target.append(targets)

        mlb = MultiLabelBinarizer()
        mlb.fit(train_target)
        train_target_binary = mlb.transform(train_target)
        print("Number of labels: {}".format(len(train_target_binary[0])))

        text_clf = joblib.load(classifier_file)

        self.classifier = text_clf
        self.mlb = mlb

    def train_classifier(self):
        with open(self.news_file, "r") as f:
            news = json.load(f)
        with open(self.training_file, "r") as f:
            train = json.load(f)

        stopwords = set(nltk.corpus.stopwords.words("german"))

        categories = {}
        for i, n in enumerate(train):
            cs = train[n].split(sep=",")
            for c in cs:
                cat = c.strip()
                if len(cat) > 1:
                    categories.setdefault(cat, 0)

        self.category_map = dict(zip(categories.keys(), range(len(categories))))
        self.category_map_inverse = dict(zip(range(len(categories)), categories.keys()))

        train_data = []
        train_target = []

        for i, n in enumerate(train):
            all_content = self.pre_process(news[n])
            targets = []
            cs = train[n].split(sep=",")
            for c in cs:
                cat = c.strip()
                if len(cat) > 1:
                    targets.append(self.category_map[cat])

            train_data.append(all_content)
            train_target.append(targets)

        self.mlb = MultiLabelBinarizer()
        self.mlb.fit(train_target)
        train_target_binary = self.mlb.transform(train_target)


        self.classifier = Pipeline([("vect", CountVectorizer(stop_words=stopwords, ngram_range=(1, 3))),
                                    ("tfidf", TfidfTransformer()),
                                    ("clf", KNeighborsClassifier(n_neighbors=5, weights="distance"))])
        self.classifier.fit(train_data, train_target_binary)


        # Test run on all available news that haven't been used for training.
        test_data = []
        test_data_original = []

        for i, n in enumerate(news):
            if n not in train:
                img_captions = []
                for img in news[n]["images"]:
                    if len(img) > 1:
                        img_captions.append(img[1])
                all_captions = "\n".join(img_captions)
                all_text = "\n".join(news[n]["paragraphs"])

                teaser = ("" if "teaser" not in news else news["teaser"])
                all_content = "\n\n".join([news[n]["title"], teaser, all_text, all_captions])

                test_data.append(all_content)
                test_data_original.append(news[n])

        pred = self.classifier.predict(test_data)
        pred_labels = self.mlb.inverse_transform(pred)

        news_tagged = 0
        tags_used = 0
        tag_dict = {}

        for i, p in enumerate(pred):
            tags = []
            for lid in list(pred_labels[i]):
                tags.append(self.category_map_inverse[lid])
                tag_dict.setdefault(self.category_map_inverse[lid], 0)
                tag_dict[self.category_map_inverse[lid]] += 1

            if len(tags) > 0:
                # tweet = make_tweet(test_data_original[i], process_tags(tags))
                # print("{} ::: {}".format(len(tweet), tweet))
                news_tagged += 1
                tags_used += len(tags)

        # Print out some rudimentary metrics.
        print("=================================================================================================")
        print("Number of labels: {}".format(len(train_target_binary[0])))
        print("{} news tagged... (ca. {}%)".format(news_tagged, round((news_tagged/len(test_data))*100)))
        print("{} tags used...".format(tags_used))
        print("Average tags per tagged news: {}".format(tags_used/news_tagged))
        print("{} unique tags".format(len(tag_dict)))
        print()
        print(tag_dict)
        print("=================================================================================================")

        # joblib.dump(text_clf, "last_classifier.pkl")

    def suggest_hashtags(self, news):
        all_content = self.pre_process(news)
        pred = self.classifier.predict([all_content])
        pred_labels = self.mlb.inverse_transform(pred)

        tags = []
        for i, p in enumerate(pred):
            for lid in list(pred_labels[i]):
                tag = self.category_map_inverse[lid]
                if tag in self.tag_map:
                    tag = self.tag_map[tag]
                else:
                    tag = tag.capitalize()
                tags.append(tag)

        return tags
