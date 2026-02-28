from ftplib import FTP
from io import BytesIO, StringIO

import pandas as pd
import streamlit as st


def _ftp_config() -> dict:
    if "ftp" not in st.secrets:
        raise KeyError("Missing [ftp] section in .streamlit/secrets.toml")
    return st.secrets["ftp"]


@st.cache_data(show_spinner=False)
def _download_bytes(remote_path: str) -> bytes:
    config = _ftp_config()

    host = config.get("host")
    user = config.get("user")
    password = config.get("password")

    if not host or not user or not password:
        raise ValueError("FTP host/user/password is not fully configured in Streamlit secrets.")

    buffer = BytesIO()
    with FTP(host) as ftp:
        ftp.login(user=user, passwd=password)
        ftp.retrbinary(f"RETR {remote_path}", buffer.write)

    return buffer.getvalue()


def get_ftp_path(secret_key: str, fallback_path: str | None = None) -> str:
    config = _ftp_config()
    return str(config.get(secret_key, fallback_path or ""))


def read_excel_from_ftp(remote_path: str, **kwargs) -> pd.DataFrame:
    if not remote_path:
        raise ValueError("FTP remote path is empty.")
    data = _download_bytes(remote_path)
    return pd.read_excel(BytesIO(data), **kwargs)


def read_csv_from_ftp(remote_path: str, **kwargs) -> pd.DataFrame:
    if not remote_path:
        raise ValueError("FTP remote path is empty.")
    data = _download_bytes(remote_path)
    return pd.read_csv(StringIO(data.decode("utf-8")), **kwargs)


def read_tabular_from_ftp(remote_path: str, **kwargs) -> pd.DataFrame:
    lower = remote_path.lower()
    if lower.endswith(".csv"):
        return read_csv_from_ftp(remote_path, **kwargs)
    return read_excel_from_ftp(remote_path, **kwargs)
