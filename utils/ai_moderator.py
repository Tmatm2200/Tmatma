"""
AI Moderator using scikit-learn for bad word detection.
Supports Arabic text.
"""
import json
import os
import logging
from typing import List, Dict, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import SVC
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib

logger = logging.getLogger(__name__)

class AIModerator:
    def __init__(self, data_file: str = "ai_training.json", model_file: str = "ai_model.pkl"):
        self.data_file = data_file
        self.model_file = model_file
        self.pipeline = None
        self.load_data()
        self.load_model()

    def load_data(self) -> None:
        """Load training data from JSON file."""
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.bad_words = data.get('bad', [])
                self.good_words = data.get('good', [])
        else:
            self.bad_words = []
            self.good_words = []

    def save_data(self) -> None:
        """Save training data to JSON file."""
        data = {'bad': self.bad_words, 'good': self.good_words}
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_label(self, text: str, is_bad: bool) -> None:
        """Add a labeled text to the training data."""
        if is_bad:
            if text not in self.bad_words:
                self.bad_words.append(text)
        else:
            if text not in self.good_words:
                self.good_words.append(text)
        self.save_data()
        self.train_model()  # Retrain after adding data

    def get_all_labeled(self) -> Dict[str, List[str]]:
        """Get all labeled words."""
        return {'bad': self.bad_words.copy(), 'good': self.good_words.copy()}

    def train_model(self) -> None:
        """Train the AI model on the labeled data."""
        if len(self.bad_words) < 2 or len(self.good_words) < 2:
            logger.warning("Not enough data to train model. Need at least 2 bad and 2 good examples.")
            self.pipeline = None
            return

        X = self.bad_words + self.good_words
        y = [1] * len(self.bad_words) + [0] * len(self.good_words)

        # For Arabic support, use character-level n-grams
        vectorizer = TfidfVectorizer(
            analyzer='char_wb',
            ngram_range=(1, 3),
            max_features=5000,
            lowercase=False  # Preserve case for Arabic
        )
        classifier = SVC(random_state=42, probability=True)

        self.pipeline = Pipeline([
            ('vectorizer', vectorizer),
            ('classifier', classifier)
        ])

        self.pipeline.fit(X, y)
        self.save_model()

        # Test accuracy on training data
        pred = self.pipeline.predict(X)
        acc = accuracy_score(y, pred)
        logger.info(f"Model trained with accuracy: {acc:.2f}")

    def save_model(self) -> None:
        """Save the trained model."""
        if self.pipeline:
            joblib.dump(self.pipeline, self.model_file)

    def load_model(self) -> None:
        """Load the trained model if exists."""
        if os.path.exists(self.model_file):
            try:
                self.pipeline = joblib.load(self.model_file)
                logger.info("Model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
                self.pipeline = None

    def predict_badness(self, text: str) -> float:
        """Predict the badness percentage of a text."""
        if not self.pipeline:
            return 0.0

        try:
            probas = self.pipeline.decision_function([text])
            # decision_function gives signed distance, convert to probability-like
            # For LinearSVC, probability=True enables predict_proba
            proba = self.pipeline.predict_proba([text])[0][1]  # Probability of class 1 (bad)
            return proba * 100
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return 0.0

    def is_bad(self, text: str, threshold: float = 75.0) -> bool:
        """Check if text is bad based on threshold."""
        return self.predict_badness(text) > threshold

# Global instance
ai_moderator = AIModerator()