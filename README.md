# ReqCheck - Requirements Clarity Checker ✅

An AI-assisted tool designed to help systems engineers and project managers improve the quality of their requirements. By identifying and flagging ambiguous or subjective language, this tool helps prevent costly rework and project delays.

![ReqCheck Screenshot]()

---

### 🚀 Key Features

* **Document Analysis:** Upload and analyze requirements from `.txt` and `.docx` files.
* **Quality Scoring:** Get an overall "Clarity Score" for your document.
* **Issue Detection:** Automatically flags common issues like:
    * **Ambiguity:** Catches subjective and weak words (e.g., "should", "user-friendly", "robust").
    * **Passive Voice:** Identifies passive constructions using `spaCy`.
    * **Incompleteness:** Detects requirement fragments that are missing a verb.
* **Visual Reporting:** A summary bar chart and word cloud visualize the most common issues.
* **Detailed Feedback:** Provides a line-by-line, color-coded analysis of every requirement.
* **Exportable Reports:** Download the full analysis as a `.csv` file for easy sharing and tracking.

---

### 🛠️ Getting Started

Follow these instructions to get a copy of the project up and running on your local machine.

#### **1. Prerequisites**

* You must have **Python 3.9** or newer installed on your system.

#### **2. Installation**

1.  **Clone the repository:**
    Open your terminal and run the following command:
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
    This is a one-time download for the grammar engine.
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
3.  Your web browser will automatically open a new tab with the ReqCheck application running.
4.  Use the file uploader to test the app! For a quick start, you can use the `sophisticated_requirements.txt` file included in this repository.

---

### 🗺️ Project Roadmap

* [x] **Phase 1 (MVP):** Core ambiguity analysis engine (Command-line).
* [x] **Phase 2 (v1.0):** Functional UI, file parsing, scoring, NLP checks, and CSV export.
* [ ] **Phase 3 (v2.0):** Integration of Large Language Models (LLMs) for advanced suggestions and need-to-requirement conversion.

---

### 🙏 Acknowledgments
* This project's structure and goals are aligned with the principles found in the **INCOSE Systems Engineering Handbook**.
