# train_lstm.py
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import tensorflow as tf

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, classification_report


SEED = 42
tf.keras.utils.set_random_seed(SEED)
np.random.seed(SEED)

# Match your baseline split
TEST_SIZE = 0.2

# ✅ Use recent augmented data
INTENTS_PATH = "ChatbotWebsite/static/data/intents_augmented.json"

# Tokenizer / sequence settings
MAX_WORDS = 20000      # vocab size
MAX_LEN = 40           # pad/truncate length (tune 30-60)
EMB_DIM = 128
LSTM_UNITS = 128

EPOCHS = 20
BATCH_SIZE = 32
LR = 1e-3


def load_intents_texts_labels(intents_path: str) -> tuple[list[str], list[str]]:
    """
    Loads texts + labels from intents JSON.

    Supported JSON shapes:
      A) {"intents":[{"tag":"...", "patterns":[...]}]}
      B) [{"tag":"...", "patterns":[...]}]
    """
    p = Path(intents_path)
    if not p.exists():
        raise FileNotFoundError(f"INTENTS_PATH not found: {p.resolve()}")

    with p.open("r", encoding="utf-8") as f:
        obj = json.load(f)

    intents = obj.get("intents") if isinstance(obj, dict) else obj
    if not isinstance(intents, list):
        raise ValueError("Invalid intents file format: expected list or {'intents': [...]}")

    texts: list[str] = []
    labels: list[str] = []

    for it in intents:
        tag = it.get("tag") or it.get("intent") or it.get("name")
        patterns = it.get("patterns") or it.get("examples") or it.get("texts")

        if not tag or not patterns:
            continue

        for pat in patterns:
            if not isinstance(pat, str):
                continue
            t = pat.strip()
            if not t:
                continue
            texts.append(t)
            labels.append(tag)

    if not texts:
        raise ValueError("No training samples found in intents file (patterns empty).")

    return texts, labels


def main():
    texts, labels = load_intents_texts_labels(INTENTS_PATH)

    print("\nDATASET CHECK (LSTM)")
    print("INTENTS_PATH:", INTENTS_PATH)
    print("Total samples:", len(texts))
    print("Unique labels:", len(set(labels)))
    print("Top label counts:", Counter(labels).most_common(8))

    # Label encoding
    le = LabelEncoder()
    y_int = le.fit_transform(labels)
    num_classes = len(le.classes_)

    # Train/Val split (stratify)
    X_train_txt, X_val_txt, y_train_int, y_val_int = train_test_split(
        texts,
        y_int,
        test_size=TEST_SIZE,
        random_state=SEED,
        stratify=y_int,
    )

    # Tokenize (fit ONLY on train)
    tok = tf.keras.preprocessing.text.Tokenizer(num_words=MAX_WORDS, oov_token="<OOV>")
    tok.fit_on_texts(X_train_txt)

    X_train_seq = tok.texts_to_sequences(X_train_txt)
    X_val_seq = tok.texts_to_sequences(X_val_txt)

    X_train = tf.keras.preprocessing.sequence.pad_sequences(
        X_train_seq, maxlen=MAX_LEN, padding="post", truncating="post"
    )
    X_val = tf.keras.preprocessing.sequence.pad_sequences(
        X_val_seq, maxlen=MAX_LEN, padding="post", truncating="post"
    )

    y_train = tf.keras.utils.to_categorical(y_train_int, num_classes=num_classes)
    y_val = tf.keras.utils.to_categorical(y_val_int, num_classes=num_classes)

    # Model
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(MAX_LEN,)),
        tf.keras.layers.Embedding(input_dim=MAX_WORDS, output_dim=EMB_DIM),
        tf.keras.layers.SpatialDropout1D(0.2),
        tf.keras.layers.LSTM(LSTM_UNITS, dropout=0.2, recurrent_dropout=0.0),
        tf.keras.layers.Dense(128, activation="relu"),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(num_classes, activation="softmax"),
    ])

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LR),
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=4, restore_best_weights=True
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss", factor=0.5, patience=2, min_lr=1e-5, verbose=1
        ),
    ]

    print("\n🚀 Training LSTM...")
    hist = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=callbacks,
        verbose=1,
    )

    best_val_acc = float(np.max(hist.history["val_accuracy"]))
    final_val_acc = float(hist.history["val_accuracy"][-1])
    print(f"\n✅ Best Val Accuracy:  {best_val_acc:.4f} ({best_val_acc*100:.2f}%)")
    print(f"✅ Final Val Accuracy: {final_val_acc:.4f} ({final_val_acc*100:.2f}%)")

    # Evaluate like baselines
    probs = model.predict(X_val, verbose=0)
    pred_int = np.argmax(probs, axis=1)

    acc = accuracy_score(y_val_int, pred_int)
    print("\n=== LSTM (Tokenizer + Embedding) ===")
    print("Accuracy:", acc)
    print(classification_report(
        y_val_int, pred_int,
        target_names=le.classes_,
        digits=3,
        zero_division=0
    ))


if __name__ == "__main__":
    main()