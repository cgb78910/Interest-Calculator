import pandas as pd
from datetime import datetime
from pandas import to_datetime, date_range
import warnings

# === DATA LOADING UTILITIES ===
def load_and_clean_csv(file_path: str, date_cols: list[str] = None) -> pd.DataFrame:
    df = pd.read_csv(file_path, dayfirst=True if date_cols else False)
    df.columns = df.columns.str.strip()
    if date_cols:
        for col in date_cols:
            df[col] = to_datetime(df[col], dayfirst=True)
    return df

def parse_band_ranges(bands_df: pd.DataFrame) -> pd.DataFrame:
    bands_df[['Minimum', 'Maximum']] = bands_df['lower'].astype(str).str.split('-', expand=True)
    bands_df['Minimum'] = pd.to_numeric(bands_df['Minimum'], errors='coerce')
    bands_df['Maximum'] = pd.to_numeric(bands_df['Maximum'], errors='coerce')
    return bands_df

# === HELPER FUNCTIONS ===
def get_band_name(balance: float) -> str | None:
    if pd.isna(balance):
        return None
    row = bands.query("Minimum <= @balance <= Maximum")
    return row.iloc[0]["band"] if not row.empty else None

def get_rate_for_date_and_band(date: datetime, band_name: str) -> float:
    applicable = rates[(rates["Start Date"] <= date) & (rates["band"] == band_name)]
    return float(applicable.iloc[-1]["rate"]) if not applicable.empty else 0.0

def calculate_interest_with_steps(transactions_df: pd.DataFrame, end_date: datetime = None, output_filename: str = "interest_calculation_log.csv") -> float:
    if end_date is None:
        end_date = datetime.today()

    total_interest = 0.0
    balance = 0.0
    log_rows = []

    date_range_iter = date_range(start=transactions_df["Date"].min(), end=end_date)
    trans_by_date = transactions_df.groupby("Date")["Change"].sum().to_dict()

    for current_date in date_range_iter:
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
            "Date": current_date.strftime("%d-%m-%y"),
            "Balance": balance,
            "Band": band if band else "N/A",
            "Daily Rate (%)": round(rate * 365 * 100, 4),
            "Daily Interest": round(daily_interest, 6),
            "Total Interest So Far": round(total_interest, 6)
        })

    log_df = pd.DataFrame(log_rows)
    log_df.to_csv(output_filename, index=False)

    return round(total_interest, 2)

# === MAIN EXECUTION BLOCK ===
def main():
    transactions_file = input("Enter transactions CSV filename (default 'transactions.csv'): ").strip()
    if not transactions_file:
        transactions_file = "transactions.csv"

    transactions = pd.read_csv(transactions_file, header=None, names=["Date", "Change"], dayfirst=True)
    transactions.columns = transactions.columns.str.strip()
    transactions["Date"] = to_datetime(transactions["Date"], dayfirst=True)
    transactions["Change"] = pd.to_numeric(transactions["Change"], errors='coerce')

    base_name = transactions_file.rsplit('.', 1)[0]
    output_filename = f"{base_name}_calculation.csv"

    interest = calculate_interest_with_steps(transactions, output_filename=output_filename)
    print(f"Total interest calculated: £{interest}")
    print(f"Detailed daily interest calculation saved to '{output_filename}'")

# === INITIALIZATION ===
if __name__ == "__main__":
    warnings.filterwarnings("ignore")

    # Load required files once globally
    rates = load_and_clean_csv("rates.csv", date_cols=["Start Date"])
    bands = parse_band_ranges(load_and_clean_csv("bands.csv"))

    main()

