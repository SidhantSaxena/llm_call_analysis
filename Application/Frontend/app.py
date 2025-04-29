"""Call Analyzer - File Upload and Analysis.

This script allows users to upload either an audio file (.wav) or a transcript (.txt).
    - If an audio file is uploaded, it is sent to a FastAPI backend for transcription.
    - If a text file is uploaded, it is processed directly for analysis.
    - The processed data is stored in `st.session_state` and the user is redirected to the analytics page.
"""

import asyncio
import io
import sys
import tomllib
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path

import httpx
import streamlit as st
import toml
from loguru import logger

sys.path.append(str(Path(__file__).parent.resolve().parent))
from unified_logging.config_types import LoggingConfigs
from unified_logging.logging_client import setup_network_logger_client

CONFIG_FILE_PATH = Path.cwd() / "Application" / "unified_logging" / "configs.toml"
logging_configs = LoggingConfigs.load_from_path(CONFIG_FILE_PATH)
setup_network_logger_client(logging_configs, logger)
logger.info("Frontend started.")

def load_toml_config(file_path: str = "config.toml") -> dict[str, str]:
    """Load and parse a toml configuration file."""
    with Path(file_path).open("rb") as file:
        return tomllib.load(file)

async def call_process_url(call_dir: Path, process_url: str) -> httpx.Response :
    """Call the FastAPI process endpoint with the call directory path."""
    async with httpx.AsyncClient(timeout=1000.0) as client:
        return await client.get(process_url, params={"file_path": str(call_dir)})

async def call_llm_summary_url(content: str, summary_url: str) -> dict:
    """Call the FastAPI LLM summary endpoint asynchronously with the content as query."""
    async with httpx.AsyncClient(timeout=1000.0) as client:
        response = await client.get(summary_url, params={"query": content})
    return response.json()

config = load_toml_config()

if "file_uploaded" not in st.session_state:
    st.session_state.file_uploaded = False

if "refresh" not in st.session_state:
    st.session_state.refresh = False

def refresh_page() -> None:
    """Refresh page on button click."""
    st.session_state.refresh = not st.session_state.refresh

FASTAPI_UPLOAD_URL = config["fastapi"]["upload_url"]
FASTAPI_PROCESS_URL = config["fastapi"]["process_url"]
FASTAPI_LLM_SUMM_URL = config["fastapi"]["llm_summary_url"]

# Page config
st.set_page_config(page_title="Call Analyzer", layout="wide", initial_sidebar_state="collapsed")


st.title("📂 Upload Audio or Transcript Log")

# File uploader with both audio and text file support
ip_file = st.file_uploader("Upload your file (Audio: .wav | Text: .txt)", type=["wav", "txt"])

# Processing file given
if ip_file and not st.session_state.file_uploaded:
    file_name = ip_file.name
    file_extension = Path(file_name).suffix.lower() #os.path.splitext(file_name)[1].lower()

    # Create directory to store the file
    current_time = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    call_dir = Path("transcripts") / f"call_{current_time}"
    call_dir.mkdir(parents=True, exist_ok=True)

    # Define the storage path based on file type
    if file_extension == ".wav":
        save_path = call_dir / "audio.wav"
    elif file_extension == ".txt":
        save_path = call_dir / "diary.txt"
        # Save the uploaded file
        with save_path.open("wb") as f: #open(save_path, "wb") as f:
            f.write(ip_file.getbuffer())
    else:
        st.error("❌ Unsupported file type. Please upload a valid audio (.wav) or text (.txt) file.")
        st.stop()

    # Save the uploaded file
    with save_path.open("wb") as f:
        f.write(ip_file.getbuffer())
    st.toast(f"✅ {file_name} uploaded successfully!")
    st.session_state.file_uploaded = True

    # For audio files
    if file_extension == ".wav":
        st.info("🎵 Detected **Audio File**. Proceeding to transcription...")
        logger.info("Detected Audio File. Proceeding to transcription...")
        content=""
        try:
            with st.spinner("Processing audio..."):
                process_response = asyncio.run(call_process_url(call_dir, FASTAPI_PROCESS_URL))
                with (call_dir / "diary.txt").open(encoding="utf-8") as file:
                    content = file.read()
            if process_response.status_code == HTTPStatus.OK:
                st.session_state["ip_file"] = content
                st.session_state["file_type"] = 0
                st.success("✅ Text file stored successfully in session_state!")
            else:
                st.error("❌ Failed to process audio file.")

        except httpx.HTTPError as e:
            st.error(f"HTTP Error: {e}")
        data = asyncio.run(call_llm_summary_url(content, FASTAPI_LLM_SUMM_URL))
        toml_data = {"llm_response": data}
        summ_path = call_dir/ "call_summary.toml"
        with summ_path.open("w") as f:
            toml.dump(toml_data, f)

    # For transcripts
    elif file_extension == ".txt":
        st.toast("📄 Detected **Text File**. Proceeding to analysis...")
        logger.info("Detected Text File")
        with st.spinner("Processing... Please wait."):
            st.session_state["ip_file"] = ip_file
            st.session_state["file_type"] = 0
            data = asyncio.run(call_llm_summary_url(ip_file.read().decode("utf-8"), FASTAPI_LLM_SUMM_URL))
            toml_data = {"llm_response": data}
            summ_path = call_dir/ "call_summary.toml"
            with summ_path.open("w") as f:
                toml.dump(toml_data, f)

    # Wrong file type
    else:
        st.error("❌ Unsupported file type. Please upload a valid audio (.wav) or text (.txt) file.")
        st.stop()

def refresh_file() -> None:
    """Refresh file cache on button click."""
    st.session_state.file_uploaded = False

if st.session_state.file_uploaded:
    logger.info("Reset file cache")
    st.button("Upload another file", on_click=refresh_file)


st.header("📂 Uploaded Transcripts")
st.button("🔄 Refresh", on_click=refresh_page)
transcripts_dir = Path("transcripts")
st.write("________________________________________________________________________________________________________")
if transcripts_dir.exists() and any(transcripts_dir.iterdir()):
    for call_folder in sorted(transcripts_dir.iterdir(), reverse=True):
        logger.info(f"Rendering view for {call_folder.name}")
        if call_folder.is_dir():
            txt_file = call_folder / "diary.txt"
            summary_file = call_folder / "call_summary.toml"
            if summary_file.exists():
                data = toml.load(summary_file)
                response_str = data["llm_response"]["response"]
                parts = response_str.split("'call_theme':")
            if txt_file.exists():
                with st.container():
                    col1, col2, col3 = st.columns([0.45, 0.35,0.2])
                    with col1:
                        st.write(f"🗂️ {call_folder.name} ")
                    with col2:
                        if summary_file.exists():
                            st.write( f":blue[Call Theme:] {parts[1].strip(" ,\n")}")
                        else:
                            st.write(" ")
                    with col3:
                        if st.button("View Analysis", key=str(txt_file)):
                            # Read the file
                            with Path(txt_file).open(encoding="utf-8") as f:
                                content = f.read()
                            # Store in session state
                            st.session_state["ip_file"] = io.StringIO(content)
                            st.session_state["file_type"] = 0
                            st.switch_page("pages/analytics.py")
            st.write(f":green[Call Summary:] {parts[0].replace("'summary':", "").strip(" ,\n")}")
            st.write("________________________________________________________________________________________________________")
else:
    st.info("No previous transcripts found.")
