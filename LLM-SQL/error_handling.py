from dotenv import load_dotenv
import streamlit as st
import os
import psycopg2
import google.generativeai as genai
import re

# Load environment variables
load_dotenv()

# Configure GenAI Key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Convert salary numbers in question to LPA
def convert_salary_to_lpa(question):
    def format_salary(match):
        salary_str = match.group(0).replace(",", "")
        salary = int(salary_str)
        salary_lpa = salary / 100000
        return f"{salary_lpa} LPA"
    question = re.sub(r"\b[\d,]+\b", format_salary, question)
    return question

# Generate SQL query using Gemini
def get_gemini_response(question, prompt):
    try:
        if "lpa" not in question.lower():
            question = convert_salary_to_lpa(question)
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content([prompt[0], question])
        if response and hasattr(response, "candidates") and response.candidates:
            generated_text = response.candidates[0].content.parts[0].text.strip()
            if "SQL Query:" in generated_text:
                generated_text = generated_text.split("SQL Query:")[-1].strip()
            return generated_text
        else:
            return "Error: Unable to generate SQL query."
    except Exception as e:
        return f"Error: {str(e)}"

# Read SQL Query result from PostgreSQL
def read_sql_query(sql):
    sql_upper = sql.strip().upper()

    if sql_upper.startswith("INSERT"):
        return [("Error:", "Can't insert into the database.")]
    elif sql_upper.startswith("UPDATE"):
        return [("Error:", "Can't update the database.")]
    elif sql_upper.startswith("DELETE"):
        return [("Error:", "Can't delete from the database.")]
    
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        conn.commit()
        cur.close()
        conn.close()
        return rows if rows else [("Notice:", "Query executed successfully but returned no rows.")]
    except psycopg2.Error as e:
        return [("Error:", str(e))]


# Prompt for Gemini
prompt = [
    """
    You are an expert in converting English questions to SQL queries!
    The SQL database contains the following tables and columns:

    1 **STUDENT Table**
       - student_id (Primary Key)
       - name
       - branch
       - skills
       - cgpa
       - graduation_year

    2 **COMPANIES Table**
       - company_id (Primary Key)
       - name
       - sector
       - visit_month

    3 **OFFERS Table**
       - offer_id (Primary Key)
       - student_id (Foreign Key → STUDENT.student_id)
       - company_id (Foreign Key → COMPANIES.company_id)
       - package_lpa
       - job_role

    **Examples:**
    - "How many students are in the database?"  
      **SQL Query:** SELECT COUNT(*) FROM student;

    - "List all students in the Computer Science branch."  
      **SQL Query:** SELECT * FROM student WHERE branch = 'Computer Science';

    - "Find companies in the Finance sector."  
      **SQL Query:** SELECT * FROM companies WHERE sector = 'Finance';

    - "Show job offers where the package is more than 20 LPA."  
      **SQL Query:** SELECT * FROM offers WHERE package_lpa > 20;

    - "Find all students who have offers in Google."  
      **SQL Query:** 
        SELECT s.name, o.job_role, o.package_lpa 
        FROM student s
        JOIN offers o ON s.student_id = o.student_id
        JOIN companies c ON o.company_id = c.company_id
        WHERE c.name = 'Google';

    **Important Rules:**
    - The SQL query should NOT include ```sql formatting or backticks.
    - The SQL query should be properly formatted for PostgreSQL.
    """
]

# Streamlit Setup
st.set_page_config(page_title="SQL Query Generator")

# Initialize page navigation
if "page" not in st.session_state:
    st.session_state["page"] = "home"

def set_page(page_name):
    st.session_state["page"] = page_name

# Initialize session variables
if "generated_query" not in st.session_state:
    st.session_state.generated_query = ""
    
if "query_result" not in st.session_state:
    st.session_state.query_result = None

# Sample Queries
sample_queries = {
    "Select a query": "",
    "Count students": "How many students are in the database?",
    "Companies in Finance": "Find companies in the Finance sector."
}

# CSS for Styling
st.markdown("""
    <style>
        .stApp { background-color: #EBE8DB; }

        .st-header {
            color: #B03052 !important;
            font-size: 32px !important;
            text-align: center !important;
            font-weight: bold !important;
        }

        div.stButton > button:first-child {
            background-color: #B03052;
            color: white;
            border-radius: 8px;
            padding: 8px 16px;
            font-size: 16px;
            transition: 0.3s;
        }

        div.stButton > button:first-child:hover {
            background-color: #D76C82;
        }

        div.stTextInput > div > input {
            border: 2px solid #007acc;
            border-radius: 5px;
            padding: 8px;
            font-size: 16px;
        }

        .custom-label {
            color: #3D0301;
            font-size: 21px !important;
            margin-bottom: -5px !important;
            padding-bottom: 0px !important;
        }

        .custom-subheader {
            color: #3D0301;
            font-size: 21px !important;
            margin-top: 20px !important;
            margin-bottom: 10px !important;
        }

        .bottom-buttons {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 20px;
        }

        .bottom-buttons button {
            background-color: #BE5985;
            color: white;
            border: none;
            padding: 10px 20px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            border-radius: 5px;
        }

        .bottom-buttons button:hover {
            background-color: #D76C82;
        }

        .block-container {
            padding-bottom: 80px;
        }
    </style>
""", unsafe_allow_html=True)

# Bottom buttons
st.markdown('<div class="bottom-buttons">', unsafe_allow_html=True)
col1, col2 = st.columns([0.2, 0.2])
with col1:
    if st.button("Home", use_container_width=True):
        set_page("home")
with col2:
    if st.button("About", use_container_width=True):
        set_page("about")
st.markdown('</div>', unsafe_allow_html=True)

# About Page
def about_page():
    st.title("About LLM SQL Query Generator")
    st.write("""
    The **LLM SQL Query Generator** helps users create SQL queries from natural language questions using a powerful Large Language Model (LLM).  

    Instead of memorizing SQL syntax, you can now simply describe what you want in plain English — and the tool will generate the correct SQL query for you.

    ---

    ## 🤖 How It Works
    This tool leverages a language model trained on SQL patterns and database schemas. When you type a natural language question, it:
    1. Understands your **intent**
    2. Recognizes relevant **tables & columns**
    3. Generates a valid **SQL query** for your input

    ---

    ## 📌 **Database Schema**

    ### 📊 `student` Table:
    - `student_id` (INT, Primary Key)  
    - `name` (VARCHAR)  
    - `branch` (VARCHAR)  
    - `skills` (VARCHAR)  
    - `cgpa` (DECIMAL)  
    - `graduation_year` (INT)

    ### 📊 `companies` Table:
    - `company_id` (INT, Primary Key)  
    - `name` (VARCHAR)  
    - `sector` (VARCHAR)  
    - `visit_month` (VARCHAR)  

    ### 📊 `offers` Table:
    - `offer_id` (INT, Primary Key)  
    - `student_id` (INT, Foreign Key → student.student_id)  
    - `company_id` (INT, Foreign Key → companies.company_id)  
    - `package_lpa` (DECIMAL)  
    - `job_role` (VARCHAR)  

    ---

    ## 🧪 Sample Natural Language Queries

    Try asking questions like:

    - 🚀 "Show students with offers above 30 LPA"
    - 🧑‍🎓 "List students with CGPA greater than 9 from the CSE branch"
    - 💼 "Which companies offered roles to students in 2024?"
    - 📅 "Find all companies visiting in the month of December"
    - 🔗 "List students along with the companies that hired them"
    - 📈 "Which student got the highest package and from which company?"
    - 🔍 "Show all students who know Python and have an offer"
    - 🏆 "Who are the top 5 students based on CGPA?"

    ---

    ## 💬 Why Use LLM for SQL?

    - ✅ No need to memorize syntax
    - ✅ Supports flexible phrasing (e.g., "above 30 LPA", "more than 9 CGPA")
    - ✅ Saves time for beginners and non-technical users
    - ✅ Makes querying accessible with just natural language

    ---

    Try typing your own query above and let the magic happen! ✨
    """)


# Home Page
def home_page():
    st.markdown('<p class="st-header">LLM SQL Query Generator</p>', unsafe_allow_html=True)

    st.markdown('<p class="custom-label">🎯 Try a Sample Query:</p>', unsafe_allow_html=True)
    selected_query = st.selectbox("", list(sample_queries.keys()), index=0)
    default_question = sample_queries[selected_query] if selected_query != "Select a query" else ""

    st.markdown('<p class="custom-label">Enter your query in English:</p>', unsafe_allow_html=True)
    question = st.text_input("", value=default_question, placeholder="Type your question here...")

    if st.button("Generate Query"):
        if question.strip() == "":
            st.warning("Please enter a question first.")
        else:
            st.session_state.generated_query = get_gemini_response(question, prompt)
            st.session_state.query_result = None

    if st.session_state.generated_query:
        st.markdown('<p class="custom-subheader">Generated SQL Query</p>', unsafe_allow_html=True)
        st.code(st.session_state.generated_query, language="sql")

        if st.button("Execute Query"):
            st.session_state.query_result = read_sql_query(st.session_state.generated_query)

    if st.session_state.query_result:
        st.markdown('<p class="custom-subheader">Query Results</p>', unsafe_allow_html=True)
        for row in st.session_state.query_result:
            st.write(row)

# Page Routing
if st.session_state["page"] == "about":
    about_page()
else:
    home_page()
