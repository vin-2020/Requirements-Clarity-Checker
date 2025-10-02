# ReqCheck - An AI-Powered Requirements Assistant ✨

An AI-assisted tool designed to help systems engineers and project managers improve the quality of their requirements. By identifying and flagging ambiguous language, passive voice, and incompleteness, this tool helps prevent costly rework and project delays. It uses NLP for analysis, an integrated LLM for intelligent assistance, and a project-based workspace to manage documents over time.

<img width="1850" height="832" alt="image" src="https://github.com/user-attachments/assets/32f41833-3093-43d3-98e7-dadee3b9581a" />

---

### 🚀 Key Features

#### Analysis Features
* **🗂️ Project Workspace:** Create projects to store and manage multiple requirement documents in one place, with a persistent database backend.
* **📄 Document Analysis:** Upload and analyze requirements from `.txt` and `.docx` files within a project.
* **📈 Quality Scoring:** Get an overall "Clarity Score" for your document.
* **⚠️ Issue Detection:** Automatically flags common issues like:
    * **Ambiguity:** Catches subjective and weak words.
    * **Passive Voice:** Identifies passive constructions using `spaCy`.
    * **Incompleteness:** Detects requirement fragments that are missing a verb.
    * **Singularity:** Flags requirements that contain multiple actions (e.g., using "and"/"or"), which should be split apart.
* **📊 Visual Reporting:** A summary bar chart and word cloud visualize the most common issues.
* **📝 Detailed Feedback:** Provides a line-by-line, color-coded analysis with educational tooltips.
* **💾 Exportable Reports:** Download the full analysis as a `.csv` file for easy sharing and tracking.

#### AI-Powered Assistant Features
* **🤖 Intelligent Requirement Extractor:** Uses an LLM to analyze unstructured documents and intelligently extract requirement statements, regardless of format.
* **💡 AI Rewrite & Decompose Suggestions:** Uses the Google Gemini LLM to suggest clearer versions of flagged requirements or decompose complex requirements into multiple singular ones.
* **✍️ Interactive Requirement Tutor:** A guided, form-based tool that teaches newcomers the correct structure of a high-quality requirement (Actor, Action, Object, Constraint) and uses AI to review the final result.
* **💬 Requirements Chatbot:** An interactive AI assistant to discuss and refine requirements in real-time.

---

### 🤔 How ReqCheck Works: An Analogy

🚗 Sedan vs. Hatchback: Why Bad Requirements Break Projects

A stakeholder says:

“I need a comfortable sedan for daily commutes.”

The requirement engineer writes it down as:

“The vehicle shall have four wheels and transport people safely.”

The design team builds… a hatchback.
Because hey — it has four wheels and it’s safe, right?

But the stakeholder didn’t want just “a car.” They wanted a sedan — comfort, space, and features that the vague requirement never captured.

✅ How ReqCheck Helps
ReqCheck doesn’t magically know what “sedan” means. But it catches the fuzzy, underspecified requirement early, flags missing details, and pushes you to clarify before the build team drives off in the wrong direction.

That way, a sedan request actually results in a sedan — not an accidental hatchback. 🚘
---

### 🛠️ Getting Started

Follow these instructions to get a copy of the project up and running on your local machine.

#### **1. Prerequisites**

* You must have **Python 3.9** or newer installed on your system.
* You need a **Google AI API Key** to use the AI-powered features. You can get a free key from [Google AI Studio](https://aistudio.google.com/).

#### **2. Installation**

**Note for New GitHub Users:** To use the `git clone` command, you must have **Git** installed on your computer. You can download it for free from [git-scm.com](https://git-scm.com/).

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
    * You can now use any of the three tabs: "Document Analyzer," the "Interactive Requirement Tutor," or the "Requirements Chatbot" for your selected project.

---

### 🗺️ Project Roadmap

* [x] **Phase 1 (MVP):** Core ambiguity analysis engine (Command-line).
* [x] **Phase 2 (v2.0):** Functional UI with advanced NLP checks and full AI assistance features.
* [/] **Phase 3 (v3.0):** Evolving into a "Project Workspace" with a database, AI-powered parser, and trend analysis. *(In Progress)*

---

### 🙏 Acknowledgments
* This project's structure and goals are aligned with principles from the **INCOSE Systems Engineering Handbook**.

---

### 📧 Contact
For any questions, feedback, or collaboration inquiries, please feel free to reach out at: `reqcheck.dev@gmail.com`
