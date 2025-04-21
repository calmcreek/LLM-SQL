from dotenv import load_dotenv
import streamlit as st
import os
import psycopg2
import google.generativeai as genai
import re
import pandas as pd


# Load environment variables
load_dotenv()

# Configure GenAI Key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))




def extract_sql_from_response(response_text):
    """
    Extracts the SQL query from a Gemini response that may contain explanations.
    """
    # Look for SQL code block
    sql_match = re.search(r"```sql\s*(.*?)\s*```", response_text, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(1).strip()

    # Fallback: Try to extract line starting with SELECT/INSERT/UPDATE/etc.
    lines = response_text.split('\n')
    sql_lines = []
    start_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'WITH']
    started = False
    for line in lines:
        if any(line.strip().upper().startswith(k) for k in start_keywords):
            started = True
        if started:
            sql_lines.append(line)
            if ';' in line:  # End of SQL query
                break
    return '\n'.join(sql_lines).strip()




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
def get_gemini_response(question, prompt, accuracy_level):
    try:
        if "lpa" not in question.lower():
            question = convert_salary_to_lpa(question)

        # Add tuning instruction based on dropdown label
        if accuracy_level == "Precise (100%)":
            tuning_instruction = (
                "ONLY generate SQL that directly matches the question. "
                "DO NOT make any assumptions, DO NOT infer or simplify. "
                "Stick to the exact words in the question."
            )
        elif accuracy_level == "Balanced(50%-90%)":
            tuning_instruction = (
                "Interpret the question with moderate flexibility. "
                "You may infer straightforward relationships, but do not guess. "
                "Make the SQL slightly broader if it improves clarity."
            )
        elif accuracy_level == "Creative (<50%)":
            tuning_instruction = (
                "Be imaginative and exploratory. You can freely assume relationships or missing conditions. "
                "Reframe or reinterpret vague questions. "
                "Even if the question is unclear or partial, still try to generate a reasonable SQL query that adds your own interpretation."
            )
        else:
            tuning_instruction = ""

        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content([
            prompt[0],
            f"{question}\n{tuning_instruction}\nExplain the logic of your SQL too."
        ])

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

        # Get column names
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

        conn.commit()
        cur.close()
        conn.close()

        # Return as tuple (columns, rows) to help build DataFrame properly
        return (columns, rows) if rows else (columns, [])
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
      **SQL Query:** SELECT * FROM student WHERE branch = 'CSE';

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

# Sample Queries
sample_queries = {

    "Select a query": "",
    " Simple → Count students": "How many students are in the database?",
    " Simple → Companies in Finance": "Find companies in the Finance sector.",
    " Simple → Students in CS branch": "List all students in the Computer Science branch.",
    " Simple → Offers above 10 LPA": "Show job offers where the package is more than 10 LPA.",

    " Medium → Students with high CGPA": "List students who have a CGPA above 9.",
    " Medium → Companies visiting in December": "Which companies are visiting in December?",
    " Medium → Total offers per student": "Show the number of offers each student received.",
    " Medium → Average package per company": "Find the average offered package for each company.",

    " Complex → Students placed in tech sector with >20 LPA": "List students placed in tech companies with a package over 20 LPA.",
    " Complex → Students not placed": "Find students who haven't received any job offers.",
    " Complex → Offers with multiple students per role": "List job roles offered to more than one student.",
    " Complex → Students placed before graduation year 2024": "Which students got placed before their graduation year 2024?",
    " Complex → Top 3 highest package offers with student & company": "Show top 3 highest package offers along with student and company details."
}



# CSS Styling
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






# Initialize session state defaults
if "sample_query" not in st.session_state:
    st.session_state.sample_query = "Select a query"
if "accuracy_level" not in st.session_state:
    st.session_state.accuracy_level = "Balanced(50%-90%)"





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
    ...
    """)

# Home Page
def home_page():
    st.markdown('<p class="st-header">LLM SQL Query Generator</p>', unsafe_allow_html=True)

    # --------- Initialize session state ---------
    if "sample_query" not in st.session_state:
        st.session_state.sample_query = "Select a query"
    if "accuracy_level" not in st.session_state:
        st.session_state.accuracy_level = "Balanced(50%-90%)"
    if "reset_dropdowns" not in st.session_state:
        st.session_state.reset_dropdowns = False

    # --------- Reset trigger ---------
    if st.session_state.reset_dropdowns:
        st.session_state.sample_query = "Select a query"
        st.session_state.accuracy_level = "Balanced(50%-90%)"
        st.session_state.reset_dropdowns = False
        st.rerun()

    # --------- Dropdowns ---------
    selected_query = st.selectbox(
        "Try a Sample Query:",
        list(sample_queries.keys()),
        index=list(sample_queries.keys()).index(st.session_state.sample_query),
        key="sample_query"  # Binds to session state
    )

    accuracy_level = st.selectbox(
        "Choose SQL Accuracy Level:",
        ["Precise (100%)", "Balanced(50%-90%)", "Creative (<50%)"],
        index=["Precise (100%)", "Balanced(50%-90%)", "Creative (<50%)"].index(st.session_state.accuracy_level),
        key="accuracy_level"  # Binds to session state
    )

    # --------- Query input ---------
    default_question = sample_queries[selected_query] if selected_query != "Select a query" else ""
    st.markdown('<p class="custom-label">Enter your query in English:</p>', unsafe_allow_html=True)
    question = st.text_input("", value=default_question, placeholder="Type your question here...")

    # --------- Generate query ---------
    if st.button("Generate Query"):
        if question.strip() == "":
            st.warning("Please enter a question first.")
        else:
            with st.spinner("Generating SQL..."):
                full_response = get_gemini_response(question, prompt, st.session_state.accuracy_level)
                st.session_state.full_response = full_response
                st.session_state.generated_query = extract_sql_from_response(full_response)
                st.session_state.query_result = None

    # --------- Show generated SQL ---------
    if st.session_state.get("generated_query"):
        st.markdown('<p class="custom-subheader">Generated SQL Query</p>', unsafe_allow_html=True)
        st.code(st.session_state.generated_query, language="sql")

        if "show_explanation" not in st.session_state:
            st.session_state.show_explanation = False

        if st.button("💡 Show Explanation of the Logic"):
            st.session_state.show_explanation = not st.session_state.show_explanation

        if st.session_state.show_explanation:
            st.markdown('<p class="custom-subheader">Explanation</p>', unsafe_allow_html=True)
            explanation_only = st.session_state.full_response.replace(st.session_state.generated_query, "").strip()
            st.info(explanation_only)
            #st.markdown(f'<p style="font-size:16px; color: #666;">{explanation_only}</p>', unsafe_allow_html=True)


        if st.button("Execute Query"):
            st.session_state.query_result = read_sql_query(st.session_state.generated_query)
            st.session_state.reset_dropdowns = True
            st.rerun()

    # --------- Query result ---------
    if st.session_state.get("query_result") is not None:
        result = st.session_state.query_result

        # Error as string
        if isinstance(result, str) and result.startswith("Error:"):
            st.error(result)

        # Error as list containing error string
        elif isinstance(result, list) and result and isinstance(result[0], str) and result[0].startswith("Error:"):
            st.error(result[0])

        # Result is query output
        else:
            st.markdown('<p class="custom-subheader">Query Results</p>', unsafe_allow_html=True)
            try:
                # Expect result to be a tuple: (column_names, rows)
                if isinstance(result, tuple) and len(result) == 2:
                    columns, rows = result
                    df = pd.DataFrame(rows, columns=columns)
                else:
                    # fallback to raw DataFrame if format unknown
                    df = pd.DataFrame(result)

                if df.empty:
                    st.info("Query executed successfully but returned no results.")
                else:
                    st.dataframe(df)

            except Exception as e:
                st.warning("Unable to display as DataFrame. Showing raw output instead:")
                st.write(result)
                st.error(f"Details: {e}")


    



# Page Routing
if st.session_state["page"] == "about":
    about_page()
else:
    home_page()
