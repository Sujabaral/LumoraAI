<<<<<<< HEAD
# LumoraAI
AI-powered mental health chatbot using a hybrid pipeline (rules + ML + LLM) with sentiment analysis, crisis detection, and self-help tools (Flask, TensorFlow, SQLite).
=======
# 🌙 LUMORA: MindCare Chatbot

> A web-based AI mental health support chatbot built for educational 
> and self-help purposes — not a diagnostic tool.

---

## 💡 About

LUMORA is an AI-powered mental wellness chatbot designed to provide 
a safe, stigma-free space for users to express their feelings and 
access self-help tools. Built with Flask, TensorFlow/Keras, and SQLite, 
it combines machine learning with safety-first design principles.

> ⚠️ LUMORA is not a substitute for professional mental health care. 
> In crisis situations, it guides users to Nepal SOS hotlines and 
> professional help.

---

## ✨ Features


---

## 🎭 Adaptive Conversation Modes

Users can select a preferred chatbot personality:

| Mode | Behavior |
|------|--------|
| 🧘 Listener | Empathy-focused validation |
| 💪 Coach | Action-oriented guidance |
| 🧠 Therapist | Deep reflection & cognitive insights |
| ⚖️ Balanced | Mixed approach |
| 🤖 Auto | AI-selected mode |

> Implemented using `preferred_mode` and `style_from_user_mode()` in the chatbot brain pipeline.

---

## ✨ Features

### Intelligent Chatbot
- Hybrid response system (Rules + ML + LLM fallback)
- Context-aware replies with conversation memory
- Multi-session chat system (persistent for logged-in users)

### 🚨 Crisis Safety System
- Real-time risk classification
- High-risk → Immediate SOS escalation
- Medium-risk → Safety confirmation modal (Yes/No flow)
- Nepal hotline integration

### 🧠 Sentiment Analysis
- VADER-based emotional scoring
- Mood detection per message

### 📊 Mood Dashboard
- Daily / weekly / monthly visualization
- PDF export support

### Journaling System
- Private journal entries
- Mood tagging and reflection tracking

### 🔥 Burnout Detection
- Questionnaire-based evaluation
- Risk-based feedback

### 🧘 Mindfulness Tools
- Guided breathing and grounding exercises

### 👥 Community Forum
- Anonymous posts
- Comments, reactions, reporting, moderation

### 📅 Psychiatrist Booking
- Appointment scheduling system
- Khalti payment integration (sandbox)

### 👍 Message Feedback System
- 👍 / 👎 per chatbot message
- Optional detailed feedback

### 🧩 Coping Plan System
- Save coping strategies from chat
- Full CRUD functionality

### 🌐 Multilingual Support
- English + Nepali + Roman Nepali
- Automatic translation pipeline

### 🔐 Authentication Modes
- Guest mode (temporary session)
- Logged-in users (persistent data & history)

### 📊 Evaluation Matrix
- Has 3 evaluation models
---


## 🧠 System Architecture

LUMORA uses a **Hybrid AI Pipeline** integrating rule-based logic, machine learning, and optional LLM fallback.

### 🔁 Response Flow
---
User Input
↓
Language Detection (English / Nepali / Roman Nepali)
↓
Translation → English
↓
Risk Detection (Low / Medium / High)
↓
Rule-Based Guards (greetings, short input, meta)
↓
Keras Intent Classifier (TF-IDF + Context)
↓
Brain Engine (Strategy + User Mode)
↓
Optional Mistral LLM Fallback
↓
Humanized Response + Safety Layer


---
## 🧠 Model Performance

| Model | Dataset | Observations | Learning Rate | Iterations | Accuracy |
|-------|---------|-------------|---------------|------------|----------|
| Rule-Based (Pattern Matching) | Own | 1,200 | – | – | 78.4% |
| Naive Bayes | Public | 3,000 | – | – | 84.6% |
| TF-IDF + SVM | Public | 3,000 | 0.01 | 1,000 | 89.2% |
| Feed-Forward Neural Network | Own + Public | 5,000 | 0.001 | 2,000 | 92.8% |
| **LSTM (Proposed Model) ✅** | **Own + Public** | **5,000** | **0.001** | **3,000** | **95.1%** |

> LSTM was selected as the final production model due to its ability to understand 
> sequential and contextual text, achieving the highest accuracy of **95.1%**.
---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, Flask |
| Database | SQLite + SQLAlchemy |
| ML/AI | TensorFlow, Keras, NLTK, VADER |
| Frontend | HTML, CSS, Bootstrap, JavaScript |
| Auth | Flask-Login, Flask-WTF |
| PDF Export | ReportLab / Matplotlib |
| Payment | Khalti (Sandbox) |
| Deployment | Ngrok |

---

## 🧠 Model Performance

| Model | Validation Accuracy |
|-------|-------------------|
| Naive Bayes (TF-IDF) | 38.74% |
| Linear SVM (TF-IDF) | 42.61% |
| **Keras FFNN (TF-IDF + History) [Production]** | **38.80%** |
| LSTM (Embedding) | 32.86% |

> The Keras model was chosen for production due to its ability to 
> incorporate conversation history features and extensibility.

---

## 🚀 Getting Started
```bash
# Clone the repo
git clone https://github.com/Sujabaral/lumora-mindcare.git
cd lumora-mindcare

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Then open `http://localhost:5000` in your browser.

---

## 📁 Project Structure
```
lumora/
├── app.py
├── chatbot/
│ ├── brain/
│ ├── pipeline/
│ ├── style/
├── models/
├── modules/
│ ├── chat/
│ ├── mood/
│ ├── journal/
│ ├── community/
├── static/
├── templates/
├── database/
---

## 👩‍💻 Built By

Suja Baral 

## 📸 Screenshots

## 🏠 Home Interface

<p align="center">
  <img src="images/home.png" width="600"/>
</p>

## 🤖 Chatbot Modes

<p align="center">
  <img src="images/chatbotmodes.png" width="600"/>
</p>

## 💬 Chat Response

<p align="center">
  <img src="images/chatresponse.png" width="600"/>
</p>

## 💬 Chat Response (Extended)

<p align="center">
  <img src="images/chatresponse2.png" width="600"/>
</p>

## 🌏 Nepali Response

<p align="center">
  <img src="images/responseinnepali.png" width="600"/>
</p>

## 😊 Sentiment Analysis

<p align="center">
  <img src="images/sentimentanalysis.png.jpeg" width="600"/>
</p>

## 🔥 Burnout Detection

<p align="center">
  <img src="images/burnoutdetection.png" width="600"/>
</p>

## 📊 Evaluation Matrix

<p align="center">
  <img src="images/evaluationmatrix.png" width="600"/>
</p>

## 📈 Graph Visualization

<p align="center">
  <img src="images/j2Graph.png" width="600"/>
</p>

## 📓 Journals

<p align="center">
  <img src="images/journals.png" width="600"/>
</p>

## 🌐 Community

<p align="center">
  <img src="images/community.png" width="600"/>
</p>

## 🌐 Community View

<p align="center">
  <img src="images/communityview.png" width="600"/>
</p>

## 🧑‍⚕️ Consultation

<p align="center">
  <img src="images/consultation.png" width="600"/>
</p>

## 💬 Feedback

<p align="center">
  <img src="images/feedback.png" width="600"/>
</p>

## 🏷️ Message Label

<p align="center">
  <img src="images/messagelabel.png" width="600"/>
</p>

## 🧾 PDF Report

<p align="center">
  <img src="images/pdfreport.png" width="600"/>
</p>

## 🆘 SOS Feature

<p align="center">
  <img src="images/sos.png" width="600"/>
</p>

---

---

## 📄 License

This project was developed for educational purpose.
>>>>>>> 2f40be4 (Added README with screenshots)
