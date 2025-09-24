# ReqCheck - An AI-Powered Requirements Assistant ✨

An AI-assisted tool designed to help systems engineers and project managers improve the quality of their requirements. By identifying and flagging ambiguous language, passive voice, and incompleteness, this tool helps prevent costly rework and project delays. It uses NLP for analysis, an integrated LLM for intelligent assistance, and a project-based workspace to manage documents over time.

<img width="2525" height="1291" alt="Screenshot 2025-09-25 004348" src="https://github.com/user-attachments/assets/55ed198e-6300-46ea-8c94-277643ae5c77" />

---

### 🚀 Key Features

* **🗂️ Project Workspace:** Create projects to store and manage multiple requirement documents in one place, with a persistent database backend.
* **📄 Document Analysis:** Upload and analyze requirements from `.txt` and `.docx` files within a project.
* **📈 Quality Scoring:** Get an overall "Clarity Score" for your document.
* **⚠️ Issue Detection:** Automatically flags common issues like ambiguity, passive voice, and incompleteness.
* **📊 Visual Reporting:** A summary bar chart and word cloud visualize the most common issues.
* **📝 Detailed Feedback:** Provides a line-by-line, color-coded analysis with educational tooltips.
* **💾 Exportable Reports:** Download the full analysis as a `.csv` file for easy sharing and tracking.

#### AI-Powered Assistant Features
* **🤖 Intelligent Requirement Extractor:** Uses an LLM to analyze unstructured documents and intelligently extract requirement statements, regardless of format.
* **💡 AI Rewrite Suggestions:** Uses the Google Gemini LLM to suggest clearer versions of flagged requirements.
* **✍️ Need-to-Requirement Helper:** Assists engineers in converting vague stakeholder needs into formal "shall" statements.
* **💬 Requirements Chatbot:** An interactive AI assistant to discuss and refine requirements in real-time.

---

### 🛠️ Getting Started

Follow these instructions to get a copy of the project up and running on your local machine.

#### **1. Prerequisites**

* You must have **Python 3.9** or newer installed on your system.
* You need a **Google AI API Key** to use the AI-powered features. You can get a free key from [Google AI Studio](https://aistudio.google.com/).

#### **2. Installation**

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/vin-2020/Requirements-Clarity-Checker.git
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

2.  🗂️ **Create or Select a Project**
    * The app will start in the "Project Workspace." You can create a new project or load an existing one.

3.  🔑 **Enter Your API Key**
    * Once a project is loaded, paste your secret Google AI API Key into the password box to enable the AI features.

4.  📊 **Start Analyzing!**
    * You can now use any of the three tabs: "Document Analyzer," "Need-to-Requirement Helper," or the "Requirements Chatbot" for your selected project.

---

### 🗺️ Project Roadmap

* [x] **Phase 1 (MVP):** Core ambiguity analysis engine (Command-line).
* [x] **Phase 2 (v2.0):** Functional UI with advanced NLP checks and AI assistance features.
* [/] **Phase 3 (v3.0):** Evolving into a "Project Workspace" with a database and AI-powered parser. *(In Progress)*

---

### 🙏 Acknowledgments
* This project's structure and goals are aligned with principles from the **INCOSE Systems Engineering Handbook**.
