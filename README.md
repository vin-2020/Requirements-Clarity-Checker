# ReqCheck - An AI-Powered Requirements Assistant ✨

An AI-assisted tool designed to help systems engineers and project managers improve the quality of their requirements. By identifying and flagging ambiguous language, passive voice, and incompleteness, this tool helps prevent costly rework and project delays. It uses NLP for analysis and an integrated LLM to provide intelligent rewrite suggestions.

![ReqCheck GIF Demo]()

---

### 🚀 Key Features

#### Analysis Features
* **📄 Document Parsing:** Upload and analyze requirements from `.txt` and `.docx` files.
* **📈 Quality Scoring:** Get an overall "Clarity Score" based on the number and severity of issues found.
* **⚠️ Issue Detection:** Automatically flags common issues:
    * **Ambiguity:** Catches subjective and weak words (e.g., "should", "user-friendly").
    * **Passive Voice:** Identifies passive constructions using `spaCy`.
    * **Incompleteness:** Detects requirement fragments that are missing a verb.
* **📊 Visual Reporting:** A summary bar chart and word cloud visualize the most common issues.
* **📝 Detailed Feedback:** Provides a line-by-line, color-coded analysis with educational tooltips.
* **💾 Exportable Reports:** Download the full analysis as a `.csv` file for easy sharing and tracking.

#### AI-Powered Assistant Features
* **💡 AI Rewrite Suggestions:** Uses the Google Gemini LLM to suggest clearer, stronger, and more measurable versions of flagged requirements.
* **✍️ Need-to-Requirement Helper:** Assists engineers in converting vague stakeholder needs into well-structured, formal "shall" statements.

---

### 🛠️ Getting Started

Follow these instructions to get a copy of the project up and running on your local machine.

#### **1. Prerequisites**

* You must have **Python 3.9** or newer installed on your system.
* You need a **Google AI API Key** to use the AI-powered features. You can get a free key from [Google AI Studio](https://aistudio.google.com/).

#### **2. Installation**

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/vin-2020/Requirements-Clarity-Checker.git](https://github.com/vin-2020/Requirements-Clarity-Checker.git)
    ```

2.  **Navigate to the project directory:**
    ```bash
    cd Requirements-Clarity-Checker
    ```

3.  **Install the required Python libraries:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Download the NLP model for spaCy:**
    ```bash
    python -m spacy download en_core_web_sm
    ```

---

### 🏃‍♀️ Usage

1.  Make sure you are in the main project directory in your terminal.
2.  Run the following command to start the Streamlit application:
    ```bash
    streamlit run ui/app.py
    ```
3.  Your web browser will open. Paste your Google AI API Key into the input box at the top.
4.  Use the file uploader to analyze a document, or use the "Need-to-Requirement Helper" to generate new requirements!

---

### 🗺️ Project Roadmap

* [x] **Phase 1 (MVP):** Core ambiguity analysis engine (Command-line).
* [x] **Phase 2 (v1.0):** Functional UI with advanced NLP checks and reporting.
* [x] **Phase 3 (v2.0):** Integration of LLM for intelligent assistance features.
* [ ] **Phase 4 (v3.0):** Evolve into a "Project Workspace" with a database to track quality over time.

---

### 🙏 Acknowledgments
* This project's structure and goals are aligned with principles from the **INCOSE Systems Engineering Handbook**.
