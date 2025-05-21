import streamlit as st
import pandas as pd
from datetime import datetime
import warnings

warnings.filterwarnings("ignore")

# === Load Rates and Bands ===
@st.cache_data
def load_data():
    rates = pd.read_csv("rates.csv", dayfirst=True)
    bands = pd.read_csv("bands.csv")

    rates.columns = rates.columns.str.strip()
    bands.columns = bands.columns.str.strip()
    rates["Start Date"] = pd.to_datetime(rates["Start Date"], dayfirst=True)

    bands[['Minimum', 'Maximum']] = bands['lower'].astype(str).str.split('-', expand=True)
    bands['Minimum'] = pd.to_numeric(bands['Minimum'], errors='coerce')
    bands['Maximum'] = pd.to_numeric(bands['Maximum'], errors='coerce')

    return rates, bands

rates, bands = load_data()

# === Utility Functions ===
def get_band_name(balance):
    row = bands[(bands["Minimum"] <= balance) & (bands["Maximum"] >= balance)]
    return row.iloc[0]["band"] if not row.empty else None

def get_rate_for_date_and_band(date, band_name):
    applicable = rates[(rates["Start Date"] <= date) & (rates["band"] == band_name)]
    return float(applicable.iloc[-1]["rate"]) if not applicable.empty else 0.0

def calculate_interest_with_steps(transactions_df, end_date):
    total_interest = 0.0
    balance = 0.0
    log_rows = []

    date_range = pd.date_range(start=transactions_df["Date"].min(), end=end_date)
    trans_by_date = transactions_df.groupby("Date")["Change"].sum().to_dict()

    for current_date in date_range:
        if current_date in trans_by_date:
            balance += trans_by_date[current_date]

        band = get_band_name(balance)
        if not band:
            rate = 0.0
            daily_interest = 0.0
        else:
            rate = get_rate_for_date_and_band(current_date, band) / 100 / 365
            daily_interest = balance * rate
            total_interest += daily_interest

        log_rows.append({
            "Date": current_date.strftime("%d/%m/%Y"),
            "Balance": balance,
            "Band": band if band else "N/A",
            "Daily Rate (%)": round(rate * 365 * 100, 4),
            "Daily Interest": round(daily_interest, 6),
            "Total Interest So Far": round(total_interest, 6)
        })

    log_df = pd.DataFrame(log_rows)
    return log_df, round(total_interest, 2)

# === STREAMLIT UI ===
st.title("Interest Calculator Dashboard")

uploaded_file = st.file_uploader("Upload Ledger Report CSV", type=["csv"])
end_date = st.date_input("End Date", datetime.today())

if uploaded_file:
    try:
        # Read and clean the uploaded file
        df_raw = pd.read_csv(uploaded_file, skiprows=5, engine="python", encoding="utf-8")
        df_raw.dropna(axis=1, how='all', inplace=True)
        df_raw.dropna(axis=0, how='all', inplace=True)
        df_raw.columns = df_raw.columns.str.strip().str.replace('\n', ' ', regex=False)

        # Detect correct columns
        date_col = next((col for col in df_raw.columns if "Date" in col), None)
        client_col = next((col for col in df_raw.columns if "Client" in col), None)

        if not date_col or not client_col:
            st.error("Missing 'Date' or 'Client' column in uploaded file.")
            st.stop()

        # Extract only the two columns needed
        ledger = df_raw[[date_col, client_col]].copy()
        ledger.columns = ["Date", "Client"]

        # Parse date
        ledger["Date"] = pd.to_datetime(ledger["Date"], dayfirst=True, errors="coerce")

        # Extract numeric transaction values from "Client" column
        ledger["Change"] = ledger["Client"].astype(str).str.extract(r'(-?\d[\d,]*\.?\d*)')[0]
        ledger["Change"] = ledger["Change"].str.replace(",", "", regex=False)
        ledger["Change"] = pd.to_numeric(ledger["Change"], errors='coerce')

        # Keep rows with both a date and a valid transaction
        ledger = ledger[ledger["Date"].notna() & ledger["Change"].notna()]
        ledger = ledger.sort_values("Date")

        # Run calculation
        result_df, total_interest = calculate_interest_with_steps(ledger, end_date)

        # Output
        st.subheader("Total Interest:")
        st.metric("£", total_interest)

        st.subheader("Interest Calculation Log")
        st.dataframe(result_df)

        st.download_button("Download CSV", result_df.to_csv(index=False), "calculation_log.csv", "text/csv")

    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
