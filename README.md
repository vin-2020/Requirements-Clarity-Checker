# ReqCheck - Requirements Clarity Checker ✅

An AI-assisted tool designed to help systems engineers and project managers improve the quality of their requirements. By identifying and flagging ambiguous or subjective language, this tool helps prevent costly rework and project delays.


---

### 🚀 Key Features

* **Document Analysis:** Upload and analyze requirements from `.txt` and `.docx` files.
* **Quality Scoring:** Get an overall "Clarity Score" for your document.
* **Issue Detection:** Automatically flags common issues like:
    * **Ambiguity:** Catches subjective and weak words (e.g., "should", "user-friendly", "robust").
    * **Passive Voice:** Identifies passive constructions that can obscure responsibility.
* **Visual Reporting:** A summary bar chart shows the breakdown of all issues found.
* **Detailed Feedback:** Provides a line-by-line analysis of every requirement in the document.

---

### 🛠️ Getting Started

Follow these instructions to get a copy of the project up and running on your local machine.

#### **1. Prerequisites**

* You must have **Python 3.9** or newer installed on your system.

#### **2. Installation**

1.  **Clone the repository:**
    Open your terminal and run the following command to clone the project.
    ```bash
    git clone [https://github.com/vin-2020/Requirements-Clarity-Checker.git](https://github.com/vin-2020/Requirements-Clarity-Checker.git)
    ```
2.  **Navigate to the project directory:**
    ```bash
    cd Requirements-Clarity-Checker
    ```

3.  **Install the required libraries:**
    This command reads the `requirements.txt` file and installs everything you need.
    ```bash
    pip install -r requirements.txt
    ```

---

### 🏃‍♀️ Usage

1.  Make sure you are in the main project directory in your terminal.
2.  Run the following command to start the Streamlit application:
    ```bash
    streamlit run ui/app.py
    ```
3.  Your web browser will automatically open a new tab with the ReqCheck application running.
   <img width="2517" height="782" alt="image" src="https://github.com/user-attachments/assets/ac920e68-5a07-44dc-a01d-706c2ec796e8" />

4.  **Use the file uploader to test the app! For a quick start, you can use the `requirements_example.txt` file included in this repository.**

---

### 🗺️ Project Roadmap

* [x] **Phase 1 (MVP):** Core ambiguity analysis engine (Command-line).
* [ ] **Phase 2 (v1.0):** Functional UI, file parsing, scoring, and basic NLP checks.
* [ ] **Phase 3 (v2.0):** Integration of Large Language Models (LLMs) for advanced suggestions and need-to-requirement conversion.

---

### 🙏 Acknowledgments
* This project's structure and goals are aligned with the principles found in the **INCOSE Systems Engineering Handbook**.
