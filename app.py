from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import os
from langchain_community.document_loaders import PyPDFLoader
import streamlit as st
from langchain_community.document_loaders import Docx2txtLoader
from langchain_core.documents import Document
from langchain_community.document_loaders import TextLoader
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import Runnable
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from prompts import ats_for_job_prompt, overall_review_prompt, ats_score_prompt, interview_prep_prompt
from langchain_core.output_parsers import StrOutputParser
import tempfile
load_dotenv()


st.set_page_config(
    page_title="Resume Review",
    page_icon=":briefcase:",
    layout="wide",
)
st.title("Resume Review with AW!!")

def load_resume(file_path):
    file_type = file_path.type 
    if file_type not in ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"]:
          st.error("Unsupported file format. Please upload a PDF, DOCX, or TXT file.")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_path = tmp_file.name
    if file_type == "application/pdf":
        loader = PyPDFLoader(tmp_path)
    elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        loader = Docx2txtLoader(tmp_path)
    elif file_type == "text/plain":
        loader = TextLoader(tmp_path)
    else:
        raise ValueError("Unsupported file format")
    
    docs = loader.load()
    return "\n".join([doc.page_content for doc in docs])

# Initialize session state for memory if not already
if "chat_history" not in st.session_state:
    st.session_state.chat_history = StreamlitChatMessageHistory()


# Step 2: Select Mode
if "mode" not in st.session_state:
    st.session_state["mode"] = None
    st.session_state["mode_done"] = False
if "job_description" not in st.session_state:
    st.session_state["job_description"] = ""

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable is not set.")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.5,
    max_tokens=2000,
    timeout=None,
    max_retries=2,
    api_key=GOOGLE_API_KEY,
)

def get_prompt_by_mode(mode):
    if mode == "Overall Review":
        return overall_review_prompt
    elif mode == "ATS Score":
        return ats_score_prompt
    elif mode == "ATS Score for specific job":
        return ats_for_job_prompt
    elif mode == "Interview Preparation":
        return interview_prep_prompt
    
st.sidebar.header("Resume Review with AW!!")
# Load the PDF file from the sidebar
uploaded_file = st.sidebar.file_uploader(
    "Upload your resume (PDF format)", type=["pdf", "docx", "txt"]
)
task_prompts = {
    "Overall Review": "Please review the overall resume.",
    "ATS Score": "Please evaluate the resume for ATS compatibility and give a score out of 100.",
    "ATS Score for specific job": "Please evaluate the resume against this job description and give ATS score.",
    "Summary of the Resume": "Please summarize the resume clearly.",
    "Interview Preparation": "Please provide interview preparation tips based on this resume."
}
if "chat_histories" not in st.session_state:
        st.session_state.chat_histories = {mode: StreamlitChatMessageHistory() for mode in task_prompts.keys()}

if "task_done" not in st.session_state:
        st.session_state.task_done = {mode: False for mode in task_prompts.keys()}

if uploaded_file is not None:
    content = load_resume(uploaded_file)
    st.session_state["resume_text"] = content
    st.sidebar.success("Resume loaded successfully!")

    # Select task/mode
    mode = st.sidebar.selectbox(
        "What do you want to Analyze from this resume?",
        [
            "-- Select --",
            "Overall Review",
            "ATS Score",
            "ATS Score for specific job",
            "Interview Preparation",
        ]
    )      
    # Mode selection
    if mode != "-- Select --":
        st.session_state["mode"] = mode
        selected_mode = st.session_state["mode"]

        # Initialize per-mode chat memory
        if "chat_histories" not in st.session_state:
            st.session_state.chat_histories = {}
        if selected_mode not in st.session_state.chat_histories:
            st.session_state.chat_histories[selected_mode] = StreamlitChatMessageHistory()

        # Set up prompt and chain per mode
        prompt = get_prompt_by_mode(selected_mode)
        chain = prompt | llm | StrOutputParser()
        chat_chain_with_history = RunnableWithMessageHistory(
                chain,
                lambda session_id: st.session_state.chat_histories[selected_mode],
                input_messages_key="input",
                history_messages_key="history"
            )
        # Show job description input only for that mode
        job_description = ""
        if selected_mode == "ATS Score for specific job":
            job_description = st.sidebar.text_area("Paste Job Description Here")
            if job_description:
                st.session_state["job_description"] = job_description

        # Button to trigger task response
        if st.sidebar.button("Review Task"):
            task_input = {
                "input": task_prompts.get(selected_mode, "Please perform the task."),
                "resume_text": st.session_state["resume_text"],
                "mode": selected_mode,
            }
            if selected_mode == "ATS Score for specific job" and job_description:
                task_input["job_description"] = st.session_state["job_description"]
                print( task_input )

            response = chat_chain_with_history.invoke(
                task_input,
                config={"configurable": {"session_id": f"{selected_mode}-session"}}
            )

        # Chat input handling
        user_input = st.chat_input("Ask a follow-up question...")
        if user_input:
            followup_input = {
                "input": user_input,
                "mode": selected_mode,
                "resume_text": st.session_state["resume_text"]
            }
            if selected_mode == "ATS Score for specific job" and "job_description" in st.session_state:
                followup_input["job_description"] = st.session_state["job_description"]

            response = chat_chain_with_history.invoke(
                followup_input,
                config={"configurable": {"session_id": f"{selected_mode}-session"}}
            )

        # ✅ Always show history for current mode
        chat_history = st.session_state.chat_histories.get(
            selected_mode, StreamlitChatMessageHistory()
        )
        for msg in chat_history.messages:
            with st.chat_message(msg.type):
                st.markdown(msg.content)