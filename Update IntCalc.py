import streamlit as st
import pandas as pd
from datetime import datetime, date
import warnings
import csv
from typing import Optional, Tuple
import io

warnings.filterwarnings("ignore")

# === Configuration ===
st.set_page_config(
    page_title="Interest Calculator Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# === Enhanced Data Loading with Error Handling ===
@st.cache_data
def load_reference_data() -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], str]:
    """Load rates and bands data with comprehensive error handling."""
    error_msg = ""
    rates_df = None
    bands_df = None
    
    try:
        # Load rates data
        rates_df = pd.read_csv("rates.csv", dayfirst=True)
        rates_df.columns = rates_df.columns.str.strip()
        rates_df["Start Date"] = pd.to_datetime(rates_df["Start Date"], dayfirst=True)
        
        # Load bands data
        bands_df = pd.read_csv("bands.csv")
        bands_df.columns = bands_df.columns.str.strip()
        
        # Parse band ranges more robustly
        if 'lower' in bands_df.columns:
            band_parts = bands_df['lower'].astype(str).str.split('-', expand=True)
            bands_df['Minimum'] = pd.to_numeric(band_parts[0], errors='coerce')
            bands_df['Maximum'] = pd.to_numeric(band_parts[1], errors='coerce')
        
        # Validate data integrity
        if rates_df.empty or bands_df.empty:
            error_msg = "Reference data files are empty"
        elif rates_df['Start Date'].isna().any():
            error_msg = "Invalid dates found in rates.csv"
        elif bands_df[['Minimum', 'Maximum']].isna().any().any():
            error_msg = "Invalid band ranges found in bands.csv"
            
    except FileNotFoundError as e:
        error_msg = f"Reference file not found: {str(e)}"
    except Exception as e:
        error_msg = f"Error loading reference data: {str(e)}"
    
    return rates_df, bands_df, error_msg

# === Business Logic Functions ===
def get_band_for_balance(balance: float, bands_df: pd.DataFrame) -> Optional[str]:
    """Determine the interest band for a given balance."""
    if bands_df is None or balance < 0:
        return None
    
    matching_bands = bands_df[
        (bands_df["Minimum"] <= balance) & 
        (bands_df["Maximum"] >= balance)
    ]
    
    return matching_bands.iloc[0]["band"] if not matching_bands.empty else None

def get_interest_rate(target_date: pd.Timestamp, band_name: str, rates_df: pd.DataFrame) -> float:
    """Get the applicable interest rate for a specific date and band."""
    if rates_df is None or not band_name:
        return 0.0
    
    applicable_rates = rates_df[
        (rates_df["Start Date"] <= target_date) & 
        (rates_df["band"] == band_name)
    ].sort_values("Start Date")
    
    if applicable_rates.empty:
        return 0.0
    
    return float(applicable_rates.iloc[-1]["rate"])

def process_ledger_data(uploaded_file) -> Tuple[Optional[pd.DataFrame], str]:
    """Process uploaded CSV ledger file with robust parsing."""
    try:
        # Read the file content
        file_content = uploaded_file.read()
        
        # Try different encodings
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        df_raw = None
        
        for encoding in encodings:
            try:
                content_str = file_content.decode(encoding)
                df_raw = pd.read_csv(
                    io.StringIO(content_str),
                    skiprows=2,
                    header=0,
                    engine='python',
                    quoting=csv.QUOTE_ALL,
                    skip_blank_lines=True,
                    on_bad_lines='skip'
                )
                break
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        
        if df_raw is None:
            return None, "Could not parse the CSV file with any supported encoding"
        
        # Validate required columns
        required_columns = ["Date", "Client"]
        missing_cols = [col for col in required_columns if col not in df_raw.columns]
        
        if missing_cols:
            available_cols = ", ".join(df_raw.columns.tolist())
            return None, f"Missing required columns: {missing_cols}. Available columns: {available_cols}"
        
        # Clean and process the data
        ledger_df = df_raw[["Date", "Client"]].copy()
        ledger_df["Date"] = pd.to_datetime(ledger_df["Date"], dayfirst=True, errors="coerce")
        
        # Clean monetary values
        ledger_df["Change"] = (
            ledger_df["Client"]
            .astype(str)
            .str.replace(r'[£,$,€,\s]', '', regex=True)
            .str.replace(r'[()]', '-', regex=True)  # Handle negative values in parentheses
        )
        ledger_df["Change"] = pd.to_numeric(ledger_df["Change"], errors='coerce')
        
        # Remove invalid rows
        initial_count = len(ledger_df)
        ledger_df = ledger_df.dropna(subset=["Date", "Change"])
        final_count = len(ledger_df)
        
        if final_count == 0:
            return None, "No valid transactions found after data cleaning"
        
        info_msg = f"Successfully processed {final_count} transactions"
        if initial_count > final_count:
            info_msg += f" ({initial_count - final_count} invalid rows removed)"
        
        return ledger_df.sort_values("Date"), info_msg
        
    except Exception as e:
        return None, f"Error processing file: {str(e)}"

def calculate_daily_interest(transactions_df: pd.DataFrame, end_date: date, 
                           rates_df: pd.DataFrame, bands_df: pd.DataFrame) -> Tuple[pd.DataFrame, float]:
    """Calculate daily interest with detailed logging."""
    
    # Initialize tracking variables
    running_balance = 0.0
    total_interest = 0.0
    calculation_log = []
    
    # Create date range and group transactions
    start_date = transactions_df["Date"].min()
    date_range = pd.date_range(start=start_date, end=end_date)
    daily_transactions = transactions_df.groupby("Date")["Change"].sum()
    
    # Process each day
    for current_date in date_range:
        # Apply any transactions for this date
        if current_date in daily_transactions:
            running_balance += daily_transactions[current_date]
        
        # Determine interest band and rate
        current_band = get_band_for_balance(running_balance, bands_df)
        
        if current_band and running_balance > 0:
            annual_rate = get_interest_rate(current_date, current_band, rates_df)
            daily_rate = annual_rate / 100 / 365  # Convert to daily decimal rate
            daily_interest = running_balance * daily_rate
        else:
            annual_rate = 0.0
            daily_rate = 0.0
            daily_interest = 0.0
        
        total_interest += daily_interest
        
        # Log the calculation
        calculation_log.append({
            "Date": current_date.strftime("%d/%m/%Y"),
            "Balance": round(running_balance, 2),
            "Interest Band": current_band or "None",
            "Annual Rate (%)": round(annual_rate, 4),
            "Daily Interest": round(daily_interest, 6),
            "Cumulative Interest": round(total_interest, 6)
        })
    
    log_df = pd.DataFrame(calculation_log)
    return log_df, round(total_interest, 2)

# === Streamlit UI ===
def main():
    st.title("💰 Interest Calculator Dashboard")
    st.markdown("---")
    
    # Load reference data
    rates_df, bands_df, load_error = load_reference_data()
    
    if load_error:
        st.error(f"**Configuration Error:** {load_error}")
        st.info("Please ensure 'rates.csv' and 'bands.csv' files are present and properly formatted.")
        return
    
    # Display reference data info
    with st.expander("📊 Reference Data Summary", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Interest Rates")
            st.dataframe(rates_df, use_container_width=True)
        
        with col2:
            st.subheader("Interest Bands")
            st.dataframe(bands_df, use_container_width=True)
    
    # Main interface
    st.subheader("📁 Upload Ledger Data")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "Select your CSV ledger file",
            type=["csv"],
            help="Upload a CSV file containing Date and Client columns"
        )
    
    with col2:
        end_date = st.date_input(
            "Calculation End Date",
            value=datetime.today().date(),
            help="Interest will be calculated up to this date"
        )
    
    if uploaded_file is not None:
        # Process the uploaded file
        with st.spinner("Processing ledger data..."):
            ledger_df, process_msg = process_ledger_data(uploaded_file)
        
        if ledger_df is None:
            st.error(f"**Processing Error:** {process_msg}")
            return
        
        st.success(process_msg)
        
        # Display transaction summary
        with st.expander("📋 Transaction Summary", expanded=False):
            st.write(f"**Date Range:** {ledger_df['Date'].min().strftime('%d/%m/%Y')} to {ledger_df['Date'].max().strftime('%d/%m/%Y')}")
            st.write(f"**Total Transactions:** {len(ledger_df)}")
            st.write(f"**Net Change:** £{ledger_df['Change'].sum():,.2f}")
            st.dataframe(ledger_df.head(10), use_container_width=True)
        
        # Calculate interest
        with st.spinner("Calculating interest..."):
            calculation_df, total_interest = calculate_daily_interest(
                ledger_df, end_date, rates_df, bands_df
            )
        
        # Display results
        st.markdown("---")
        st.subheader("🎯 Results")
        
        # Key metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                label="Total Interest Earned",
                value=f"£{total_interest:,.2f}"
            )
        
        with col2:
            final_balance = calculation_df["Balance"].iloc[-1] if not calculation_df.empty else 0
            st.metric(
                label="Final Balance",
                value=f"£{final_balance:,.2f}"
            )
        
        with col3:
            days_calculated = len(calculation_df)
            st.metric(
                label="Days Calculated",
                value=f"{days_calculated:,}"
            )
        
        # Detailed calculation log
        st.subheader("📈 Daily Calculation Log")
        st.dataframe(calculation_df, use_container_width=True, height=400)
        
        # Download options
        col1, col2 = st.columns(2)
        
        with col1:
            csv_data = calculation_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Calculation Log",
                data=csv_data,
                file_name=f"interest_calculation_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        
        with col2:
            summary_data = f"""Interest Calculation Summary
Generated: {datetime.now().strftime('%d/%m/%Y %H:%M')}
Total Interest: £{total_interest:,.2f}
Final Balance: £{final_balance:,.2f}
Calculation Period: {days_calculated} days
"""
            st.download_button(
                label="📋 Download Summary",
                data=summary_data,
                file_name=f"interest_summary_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain"
            )

# === Footer ===
def display_footer():
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; padding: 20px; color: #666; font-size: 0.9em;'>
            <p>💼 <em>Professional Interest Calculator</em></p>
            <p>Built with ❤️ by <strong>Colby Ballan</strong></p>
        </div>
        """,
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
    display_footer()