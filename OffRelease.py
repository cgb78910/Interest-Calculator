import streamlit as st
import pandas as pd
from datetime import datetime
import warnings
import csv

warnings.filterwarnings("ignore")

# === Load Rates and Bands with caching ===
@st.cache_data
def load_data():
    rates = pd.read_csv("rates.csv", dayfirst=True)
    bands = pd.read_csv("bands.csv")

    # Clean up column names
    rates.columns = rates.columns.str.strip()
    bands.columns = bands.columns.str.strip()

    # Convert dates
    rates["Start Date"] = pd.to_datetime(rates["Start Date"], dayfirst=True)

    # Parse band min/max
    bands[['Minimum', 'Maximum']] = bands['lower'].astype(str).str.split('-', expand=True)
    bands['Minimum'] = pd.to_numeric(bands['Minimum'], errors='coerce')
    bands['Maximum'] = pd.to_numeric(bands['Maximum'], errors='coerce')

    return rates, bands

rates, bands = load_data()

# === Helper: Get band for balance ===
def get_band_name(balance: float) -> str | None:
    match = bands[(bands["Minimum"] <= balance) & (bands["Maximum"] >= balance)]
    return match.iloc[0]["band"] if not match.empty else None

# === Helper: Get interest rate for date and band ===
def get_rate_for_date_and_band(date: pd.Timestamp, band_name: str) -> float:
    applicable_rates = rates[(rates["Start Date"] <= date) & (rates["band"] == band_name)]
    return float(applicable_rates.iloc[-1]["rate"]) if not applicable_rates.empty else 0.0

# === Core calculation ===
def calculate_interest_with_steps(transactions_df: pd.DataFrame, end_date: datetime):
    total_interest = 0.0
    balance = 0.0
    log_rows = []

    date_range = pd.date_range(start=transactions_df["Date"].min(), end=end_date)
    trans_by_date = transactions_df.groupby("Date")["Change"].sum().to_dict()

    for current_date in date_range:
        if current_date in trans_by_date:
            balance += trans_by_date[current_date]

        band = get_band_name(balance)
        if band:
            rate = get_rate_for_date_and_band(current_date, band) / 100 / 365
            daily_interest = balance * rate
        else:
            rate = 0.0
            daily_interest = 0.0

        total_interest += daily_interest

        log_rows.append({
            "Date": current_date.strftime("%d/%m/%Y"),
            "Balance": round(balance, 2),
            "Band": band or "N/A",
            "Daily Rate (%)": round(rate * 365 * 100, 4),
            "Daily Interest": round(daily_interest, 6),
            "Total Interest So Far": round(total_interest, 6)
        })

    log_df = pd.DataFrame(log_rows)
    return log_df, round(total_interest, 2)

# === Streamlit UI ===
st.title("Interest Calculator Dashboard")

uploaded_file = st.file_uploader("Upload Ledger Report CSV", type=["csv"])
end_date = st.date_input("End Date", datetime.today())

if uploaded_file:
    try:
        # Correctly skip metadata and use real header
        df_raw = pd.read_csv(
            uploaded_file,
            skiprows=2,  # skip metadata only
            header=0,
            engine='python',
            quoting=csv.QUOTE_ALL,
            skip_blank_lines=True,
            on_bad_lines='skip',
            encoding='utf-8'
        )

        # Ensure the necessary columns are present
        required_cols = ["Date", "Client"]
        if not all(col in df_raw.columns for col in required_cols):
            st.error("CSV is missing required columns: 'Date' and 'Client'")
        else:
            ledger = df_raw.loc[:, ["Date", "Client"]].copy()

            # Clean and parse
            ledger["Date"] = pd.to_datetime(ledger["Date"], dayfirst=True, errors="coerce")
            ledger["Change"] = ledger["Client"].astype(str).str.replace(r'[£,]', '', regex=True)
            ledger["Change"] = pd.to_numeric(ledger["Change"], errors='coerce')
            ledger = ledger.dropna(subset=["Date", "Change"])

            if ledger.empty:
                st.warning("No valid transaction rows found after cleaning.")
            else:
                result_df, total_interest = calculate_interest_with_steps(ledger, end_date)

                st.subheader("Total Interest:")
                st.metric(label="£", value=f"{total_interest:.2f}")

                st.subheader("Interest Calculation Log")
                st.dataframe(result_df, use_container_width=True)

                st.download_button(
                    label="Download Calculation Log as CSV",
                    data=result_df.to_csv(index=False),
                    file_name="calculation_log.csv",
                    mime="text/csv"
                )

    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")

    st.markdown(
    """
    <hr style="margin-top: 3em;">
    <div style='text-align: center; font-size: 0.95em; color: #555;'>
        <em>Written by Colby Ballan</em>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown(
    """
    <style>
    .footer {
        position: relative;
        text-align: center;
        margin-top: 3em;
        font-size: 0.9em;
        color: #888;
    }
    .footer img {
        width: 40px;
        vertical-align: middle;
        margin-right: 10px;
        opacity: 0.8;
    }
    .footer span {
        vertical-align: middle;
        font-style: italic;
    }
    </style>

    <div class="footer">
        <!-- Optional logo (replace the src with your own logo URL or remove the img tag) -->
        <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/1869px-Python-logo-notext.svg.png" alt="Logo">
        <span>Written by Colby Ballan</span>
    </div>
    """,
    unsafe_allow_html=True
)
