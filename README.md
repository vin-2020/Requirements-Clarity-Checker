# ReqCheck - An AI-Powered Requirements Assistant ✨

An AI-assisted tool designed to help systems engineers and project managers improve the quality of their requirements. By identifying and flagging ambiguous language, passive voice, and incompleteness, this tool helps prevent costly rework and project delays. It uses NLP for analysis and an integrated LLM to provide intelligent rewrite suggestions and conversational assistance.

<img width="1897" height="702" alt="image" src="https://github.com/user-attachments/assets/ed962708-e080-4c46-bafa-3cd1137a11d8" />


---

### 🚀 Key Features

#### Analysis Features
* **📄 Document Parsing:** Upload and analyze requirements from `.txt` and `.docx` files.
* **📈 Quality Scoring:** Get an overall "Clarity Score" based on the number of issues found.
* **⚠️ Issue Detection:** Automatically flags common issues like ambiguity, passive voice, and incompleteness.
* **📊 Visual Reporting:** A summary bar chart and word cloud visualize the most common issues.
* **📝 Detailed Feedback:** Provides a line-by-line, color-coded analysis with educational tooltips.
* **💾 Exportable Reports:** Download the full analysis as a `.csv` file for easy sharing and tracking.

#### AI-Powered Assistant Features
* **💡 AI Rewrite Suggestions:** Uses the Google Gemini LLM to suggest clearer, stronger versions of flagged requirements.
* **✍️ Need-to-Requirement Helper:** Assists engineers in converting vague stakeholder needs into well-structured, formal "shall" statements.
* **💬 Requirements Chatbot:** An interactive, conversational AI assistant to discuss, refine, and get feedback on requirements in real-time.

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

1.  🚀 **Launch the App**
    * In your terminal (from the project's main folder), run this command:
        ```bash
        streamlit run ui/app.py
        ```
    * A new tab will automatically open in your web browser.

2.  🔑 **Enter Your API Key**
    * Paste your secret Google AI API Key into the password box at the top of the page to enable the AI features.

3.  📊 **Start Analyzing!**
    * You can now use any of the three tabs: "Document Analyzer," "Need-to-Requirement Helper," or the new "Requirements Chatbot."
    * For a comprehensive demo, try uploading the `DRONE_SRS_v1.0.txt` file.

---

### 🗺️ Project Roadmap

* [x] **Phase 1 (MVP):** Core ambiguity analysis engine (Command-line).
* [x] **Phase 2 (v1.0):** Functional UI with advanced NLP checks and reporting.
* [x] **Phase 3 (v2.0):** Integration of LLM for intelligent assistance, including a conversational chatbot.
* [ ] **Phase 4 (v3.0):** Evolve into a "Project Workspace" with a database to track quality over time.

---

### 🙏 Acknowledgments
* This project's structure and goals are aligned with the principles found in the **INCOSE Systems Engineering Handbook**.
