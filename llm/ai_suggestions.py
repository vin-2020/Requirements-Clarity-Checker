# llm/ai_suggestions.py
import google.generativeai as genai
import streamlit as st

@st.cache_data
def get_ai_suggestion(api_key, requirement_text):
    """
    Sends a requirement to the Google Gemini AI and asks for a rewrite suggestion.
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        You are an expert Systems Engineer following INCOSE standards. 
        Your task is to rewrite the following requirement to be more clear, specific, active, and measurable.
        
        Original Requirement: "{requirement_text}"
        
        Rewritten Requirement:
        """
        
        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        return f"An error occurred with the AI service: {e}"

def generate_requirement_from_need(api_key, need_text):
    """
    Takes a vague user need and uses an LLM to generate a well-structured requirement.
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        You are a Systems Engineer creating a formal requirement from a stakeholder's informal need.
        Convert the following need into a structured requirement with the format:
        "[Condition], the [System/Actor] shall [Action] [Object] [Performance Metric]."

        If the need is too vague to create a full requirement, identify the missing pieces (like a measurable number or a clear action) and ask a clarifying question.

        Stakeholder Need: "{need_text}"

        Structured Requirement or Clarifying Question:
        """
        
        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        return f"An error occurred with the AI service: {e}"