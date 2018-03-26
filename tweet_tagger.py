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
        all_content = "\n\n".join([news["title"], all_text, all_captions])
        return all_content

    def load_classifier(self, classifier_file):
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



    def suggest_hashtags(self, news):
        all_content = self.pre_process(news)
        pred = self.classifier.predict([all_content])
        pred_labels = self.mlb.inverse_transform(pred)

        for i, p in enumerate(pred):
            tags = []
            for lid in list(pred_labels[i]):
                tag = self.category_map_inverse[lid]
                if tag in self.tag_map:
                    tag = self.tag_map[tag]
                else:
                    tag = tag.capitalize()
                tags.append(tag)

        return tags
