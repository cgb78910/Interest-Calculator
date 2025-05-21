import streamlit as st
import pandas as pd
from datetime import datetime
import warnings
import csv

warnings.filterwarnings("ignore")

# === Load Rates and Bands with caching for performance ===
@st.cache_data
def load_data():
    rates = pd.read_csv("rates.csv", dayfirst=True)
    bands = pd.read_csv("bands.csv")

    # Clean column names (strip whitespace)
    rates.columns = rates.columns.str.strip()
    bands.columns = bands.columns.str.strip()

    # Convert 'Start Date' to datetime
    rates["Start Date"] = pd.to_datetime(rates["Start Date"], dayfirst=True)

    # Parse band ranges: split 'lower' column into numeric min and max
    bands[['Minimum', 'Maximum']] = bands['lower'].astype(str).str.split('-', expand=True)
    bands['Minimum'] = pd.to_numeric(bands['Minimum'], errors='coerce')
    bands['Maximum'] = pd.to_numeric(bands['Maximum'], errors='coerce')

    return rates, bands


rates, bands = load_data()

# === Helper: Find band for given balance ===
def get_band_name(balance: float) -> str | None:
    match = bands[(bands["Minimum"] <= balance) & (bands["Maximum"] >= balance)]
    if not match.empty:
        return match.iloc[0]["band"]
    return None

# === Helper: Get applicable rate for given date and band ===
def get_rate_for_date_and_band(date: pd.Timestamp, band_name: str) -> float:
    applicable_rates = rates[(rates["Start Date"] <= date) & (rates["band"] == band_name)]
    if not applicable_rates.empty:
        # Use the latest rate before or on the date
        return float(applicable_rates.iloc[-1]["rate"])
    return 0.0

# === Core interest calculation, returns daily log and total ===
def calculate_interest_with_steps(transactions_df: pd.DataFrame, end_date: datetime):
    total_interest = 0.0
    balance = 0.0
    log_rows = []

    # Create date range from first transaction to end_date
    date_range = pd.date_range(start=transactions_df["Date"].min(), end=end_date)

    # Sum daily transactions for quick lookup
    trans_by_date = transactions_df.groupby("Date")["Change"].sum().to_dict()

    for current_date in date_range:
        # Apply transactions on current date if any
        if current_date in trans_by_date:
            balance += trans_by_date[current_date]

        # Find band and rate
        band = get_band_name(balance)
        if band is None:
            rate = 0.0
            daily_interest = 0.0
        else:
            # Annual rate to daily rate conversion
            rate = get_rate_for_date_and_band(current_date, band) / 100 / 365
            daily_interest = balance * rate
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
        # Read ledger CSV, skipping metadata rows
        df_raw = pd.read_csv(
            uploaded_file,
            skiprows=3,  # Adjust this if metadata rows differ
            header=None,
            engine='python',
            quoting=csv.QUOTE_ALL,
            skip_blank_lines=True,
            on_bad_lines='skip',
            encoding='utf-8'
        )

        # Assign columns (adjust as per your CSV structure)
        df_raw.columns = [
            "Date",
            "Trans Reference",
            "Third Party",
            "Client Amount",
            "Client Balance",
            "Unnamed 5",
            "Office Balance",
            "Unnamed 7",
            "Disb Balance",
            "Unnamed 9",
            "Deposit Balance",
            "Unnamed 11"
        ]

        # Keep only date and amount columns
        ledger = df_raw[["Date", "Client Amount"]].copy()

        # Parse dates robustly
        ledger["Date"] = pd.to_datetime(ledger["Date"], dayfirst=True, errors="coerce")

        # Clean amount: remove £ and commas, convert to numeric
        ledger["Change"] = ledger["Client Amount"].astype(str).str.replace(r'[£,]', '', regex=True)
        ledger["Change"] = pd.to_numeric(ledger["Change"], errors='coerce')

        # Remove invalid rows
        ledger = ledger.dropna(subset=["Date", "Change"])

        if ledger.empty:
            st.warning("No valid transaction rows found after cleaning.")
        else:
            result_df, total_interest = calculate_interest_with_steps(ledger, end_date)

            st.subheader("Total Interest:")
            st.metric(label="£", value=f"{total_interest:.2f}")

            st.subheader("Interest Calculation Log")
            st.dataframe(result_df)

            st.download_button(
                label="Download Calculation Log as CSV",
                data=result_df.to_csv(index=False),
                file_name="calculation_log.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")
