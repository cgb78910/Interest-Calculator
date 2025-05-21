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

    # Clean column names
    rates.columns = rates.columns.str.strip()
    bands.columns = bands.columns.str.strip()

    # Format dates
    rates["Start Date"] = pd.to_datetime(rates["Start Date"], dayfirst=True)

    # Split bands
    bands[['Minimum', 'Maximum']] = bands['lower'].astype(str).str.split('-', expand=True)
    bands['Minimum'] = pd.to_numeric(bands['Minimum'], errors='coerce')
    bands['Maximum'] = pd.to_numeric(bands['Maximum'], errors='coerce')

    return rates, bands

rates, bands = load_data()

# === Helper Functions ===
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
    log_df["Date"] = log_df["Date"].astype(str)
    return log_df, round(total_interest, 2)

# === Streamlit UI ===
st.title("Interest Calculator Dashboard")

uploaded_file = st.file_uploader("Upload Transactions CSV", type=["csv"])
end_date = st.date_input("End Date", datetime.today())

if uploaded_file:
    try:
        # Try standard format
        df = pd.read_csv(uploaded_file, encoding='utf-8', engine='python')
        df.columns = df.columns.str.strip()

        if "Date" in df.columns and "Client" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
            df["Change"] = df["Client"].astype(str).replace('[£,]', '', regex=True)
            df["Change"] = pd.to_numeric(df["Change"], errors="coerce")
            transactions = df[["Date", "Change"]].dropna()
        else:
            raise ValueError("Missing 'Date' and 'Client' columns — trying fallback format.")

    except Exception as e:
        try:
            # Try fallback format (ledger-style)
            raw_df = pd.read_csv(uploaded_file, skiprows=5, encoding='utf-8', engine='python')
            raw_df.columns = raw_df.columns.str.strip()

            if "Date" not in raw_df.columns or "Office" not in raw_df.columns:
                raise ValueError("Fallback failed: Missing 'Date' or 'Office' column.")

            ledger_df = raw_df[["Date", "Office"]].copy()
            ledger_df["Date"] = pd.to_datetime(ledger_df["Date"], dayfirst=True, errors='coerce')
            ledger_df = ledger_df.dropna(subset=["Date"])
            ledger_df["Change"] = ledger_df["Office"].astype(str).replace('[£,]', '', regex=True)
            ledger_df["Change"] = pd.to_numeric(ledger_df["Change"], errors='coerce')
            transactions = ledger_df.dropna(subset=["Change"])[["Date", "Change"]]

            if transactions.empty:
                raise ValueError("No valid transactions found in fallback.")

        except Exception as fallback_error:
            st.error(f"Could not process file: {fallback_error}")
            st.stop()

    # Run calculation and output results
    result_df, total_interest = calculate_interest_with_steps(transactions, end_date)

    st.subheader("Total Interest:")
    st.metric("£", total_interest)

    st.subheader("Interest Calculation Log")
    st.dataframe(result_df)

    st.download_button("Download CSV", result_df.to_csv(index=False), "calculation_log.csv", "text/csv")
