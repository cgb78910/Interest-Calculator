import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import warnings
import csv
from typing import Optional, Tuple, Dict
import io
import numpy as np

warnings.filterwarnings("ignore")

# === Enhanced Configuration ===
st.set_page_config(
    page_title="Interest Calculator Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better aesthetics
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }

    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #667eea;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
    }

    .success-message {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 0.75rem;
        border-radius: 5px;
        margin: 1rem 0;
    }

    .info-box {
        background-color: #f8f9fa;
        border-left: 4px solid #007bff;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 5px;
    }

    .sidebar .sidebar-content {
        background: linear-gradient(180deg, #f8f9fa 0%, #e9ecef 100%);
    }

    .stProgress .st-bo {
        background-color: #667eea;
    }
</style>
""", unsafe_allow_html=True)

# === Enhanced Data Loading with Better Caching ===
@st.cache_data(ttl=3600)  # Cache for 1 hour
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
        rates_df = rates_df.sort_values("Start Date")

        # Load bands data
        bands_df = pd.read_csv("bands.csv")
        bands_df.columns = bands_df.columns.str.strip()

        # Parse band ranges more robustly
        if 'lower' in bands_df.columns:
            band_parts = bands_df['lower'].astype(str).str.split('-', expand=True)
            bands_df['Minimum'] = pd.to_numeric(band_parts[0], errors='coerce')
            bands_df['Maximum'] = pd.to_numeric(band_parts[1], errors='coerce')

        # Sort bands by minimum value
        bands_df = bands_df.sort_values('Minimum')

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

# === Enhanced Business Logic Functions ===
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

def validate_csv_structure(df: pd.DataFrame) -> Tuple[bool, str]:
    """Validate the structure of the uploaded CSV."""
    required_columns = ["Date", "Client"]
    missing_cols = [col for col in required_columns if col not in df.columns]

    if missing_cols:
        available_cols = ", ".join(df.columns.tolist())
        return False, f"Missing required columns: {missing_cols}. Available columns: {available_cols}"

    return True, "CSV structure is valid"

@st.cache_data
def process_ledger_data(file_content: bytes) -> Tuple[Optional[pd.DataFrame], str]:
    """Process uploaded CSV ledger file with robust parsing."""
    try:
        # Try different encodings
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
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

        # Validate CSV structure
        is_valid, validation_msg = validate_csv_structure(df_raw)
        if not is_valid:
            return None, validation_msg

        # Clean and process the data
        ledger_df = df_raw[["Date", "Client"]].copy()

        # Enhanced date parsing
        ledger_df["Date"] = pd.to_datetime(
            ledger_df["Date"], 
            dayfirst=True, 
            errors="coerce",
            infer_datetime_format=True
        )

        # Enhanced monetary value cleaning
        ledger_df["Change"] = (
            ledger_df["Client"]
            .astype(str)
            .str.replace(r'[£,$,€,\s]', '', regex=True)
            .str.replace(r'[()]', '-', regex=True)
            .str.replace(r'[,]', '', regex=True)  # Remove thousand separators
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

        return ledger_df.sort_values("Date").reset_index(drop=True), info_msg

    except Exception as e:
        return None, f"Error processing file: {str(e)}"

def calculate_daily_interest(transactions_df: pd.DataFrame, end_date: date, 
                           rates_df: pd.DataFrame, bands_df: pd.DataFrame) -> Tuple[pd.DataFrame, float, Dict]:
    """Calculate daily interest with detailed logging and statistics."""

    # Initialize tracking variables
    running_balance = 0.0
    total_interest = 0.0
    calculation_log = []

    # Statistics tracking
    stats = {
        'max_balance': 0.0,
        'min_balance': 0.0,
        'avg_balance': 0.0,
        'days_earning_interest': 0,
        'total_days': 0
    }

    # Create date range and group transactions
    start_date = transactions_df["Date"].min()
    date_range = pd.date_range(start=start_date, end=end_date)
    daily_transactions = transactions_df.groupby("Date")["Change"].sum()

    balances = []

    # Process each day
    for current_date in date_range:
        # Apply any transactions for this date
        if current_date in daily_transactions:
            running_balance += daily_transactions[current_date]

        balances.append(running_balance)

        # Determine interest band and rate
        current_band = get_band_for_balance(running_balance, bands_df)

        if current_band and running_balance > 0:
            annual_rate = get_interest_rate(current_date, current_band, rates_df)
            daily_rate = annual_rate / 100 / 365
            daily_interest = running_balance * daily_rate
            stats['days_earning_interest'] += 1
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

    # Calculate statistics
    stats['max_balance'] = max(balances) if balances else 0
    stats['min_balance'] = min(balances) if balances else 0
    stats['avg_balance'] = np.mean(balances) if balances else 0
    stats['total_days'] = len(date_range)

    log_df = pd.DataFrame(calculation_log)
    return log_df, round(total_interest, 2), stats

def create_balance_chart(calculation_df: pd.DataFrame) -> pd.DataFrame:
    """Prepare balance data for Streamlit charting."""
    chart_df = calculation_df.copy()
    chart_df['Date'] = pd.to_datetime(chart_df['Date'], dayfirst=True)
    chart_df = chart_df.set_index('Date')
    return chart_df[['Balance']]

def create_interest_chart(calculation_df: pd.DataFrame) -> pd.DataFrame:
    """Prepare interest data for Streamlit charting."""
    chart_df = calculation_df.copy()
    chart_df['Date'] = pd.to_datetime(chart_df['Date'], dayfirst=True)
    chart_df = chart_df.set_index('Date')
    return chart_df[['Cumulative Interest']]

# === Enhanced Streamlit UI ===
def main():
    # Enhanced header
    st.markdown("""
        <div class="main-header">
            <h1>💰 Interest Calculator Dashboard</h1>
            <p>Professional-grade interest calculation with advanced analytics</p>
        </div>
    """, unsafe_allow_html=True)

    # Sidebar for settings and info
    with st.sidebar:
        st.header("⚙️ Settings")

        show_charts = st.checkbox("Show Interactive Charts", value=True)
        show_detailed_log = st.checkbox("Show Detailed Calculation Log", value=True)

        st.header("ℹ️ Quick Help")
        st.info("""
        **CSV Format Required:**
        - Column 1: Date
        - Column 2: Client (monetary values)
        - Skip first 2 rows (headers)

        **Supported Formats:**
        - £1,234.56
        - $1234.56
        - (1234.56) for negatives
        """)

    # Load reference data
    with st.spinner("Loading reference data..."):
        rates_df, bands_df, load_error = load_reference_data()

    if load_error:
        st.error(f"**⚠️ Configuration Error:** {load_error}")
        st.info("📁 Please ensure 'rates.csv' and 'bands.csv' files are present and properly formatted.")
        return

    # Display reference data info in expandable sections
    with st.expander("📊 Reference Data Summary", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("💹 Current Interest Rates")
            if not rates_df.empty:
                # Show only the most recent rates by default
                latest_rates = rates_df.groupby('band').last().reset_index()
                st.dataframe(
                    latest_rates[['band', 'rate', 'Start Date']], 
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("No rate data available")

        with col2:
            st.subheader("📈 Interest Bands")
            if not bands_df.empty:
                display_bands = bands_df[['band', 'Minimum', 'Maximum']].copy()
                display_bands['Range'] = display_bands.apply(
                    lambda x: f"£{x['Minimum']:,.0f} - £{x['Maximum']:,.0f}", axis=1
                )
                st.dataframe(
                    display_bands[['band', 'Range']], 
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("No band data available")

    # Main interface
    st.subheader("📁 Upload & Configure")

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_file = st.file_uploader(
            "📂 Select your CSV ledger file",
            type=["csv"],
            help="Upload a CSV file containing Date and Client columns"
        )

    with col2:
        end_date = st.date_input(
            "📅 Calculation End Date",
            value=datetime.today().date(),
            help="Interest will be calculated up to this date"
        )

    if uploaded_file is not None:
        # Process the uploaded file
        with st.spinner("🔄 Processing ledger data..."):
            file_content = uploaded_file.read()
            ledger_df, process_msg = process_ledger_data(file_content)

        if ledger_df is None:
            st.error(f"**⚠️ Processing Error:** {process_msg}")
            return

        st.markdown(f'<div class="success-message">✅ {process_msg}</div>', unsafe_allow_html=True)

        # Enhanced transaction summary
        with st.expander("📋 Transaction Summary", expanded=True):
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(
                    "📊 Total Transactions", 
                    f"{len(ledger_df):,}"
                )

            with col2:
                st.metric(
                    "📅 Date Range", 
                    f"{(ledger_df['Date'].max() - ledger_df['Date'].min()).days} days"
                )

            with col3:
                st.metric(
                    "💰 Net Change", 
                    f"£{ledger_df['Change'].sum():,.2f}"
                )

            with col4:
                avg_transaction = ledger_df['Change'].mean()
                st.metric(
                    "📈 Avg Transaction", 
                    f"£{avg_transaction:,.2f}"
                )

            # Show sample transactions
            st.write("**📝 Recent Transactions (Sample):**")
            sample_df = ledger_df.head(10).copy()
            sample_df['Date'] = sample_df['Date'].dt.strftime('%d/%m/%Y')
            sample_df['Change'] = sample_df['Change'].apply(lambda x: f"£{x:,.2f}")
            st.dataframe(sample_df, use_container_width=True, hide_index=True)

        # Calculate interest with progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.text('🔢 Calculating daily interest...')
        progress_bar.progress(25)

        calculation_df, total_interest, stats = calculate_daily_interest(
            ledger_df, end_date, rates_df, bands_df
        )

        progress_bar.progress(75)
        status_text.text('📊 Generating visualizations...')

        progress_bar.progress(100)
        status_text.text('✅ Calculation complete!')

        # Clear progress indicators
        progress_bar.empty()
        status_text.empty()

        # Display results with enhanced metrics
        st.markdown("---")
        st.subheader("🎯 Calculation Results")

        # Key metrics in a more visual layout
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                label="💰 Total Interest Earned",
                value=f"£{total_interest:,.2f}",
                delta=f"{stats['days_earning_interest']} earning days"
            )

        with col2:
            final_balance = calculation_df["Balance"].iloc[-1] if not calculation_df.empty else 0
            st.metric(
                label="🏦 Final Balance",
                value=f"£{final_balance:,.2f}",
                delta=f"Max: £{stats['max_balance']:,.2f}"
            )

        with col3:
            st.metric(
                label="📊 Average Balance",
                value=f"£{stats['avg_balance']:,.2f}",
                delta=f"Min: £{stats['min_balance']:,.2f}"
            )

        with col4:
            efficiency = (stats['days_earning_interest'] / stats['total_days'] * 100) if stats['total_days'] > 0 else 0
            st.metric(
                label="⚡ Interest Efficiency",
                value=f"{efficiency:.1f}%",
                delta=f"{stats['total_days']} total days"
            )

        # Interactive charts using Streamlit's built-in charting
        if show_charts and not calculation_df.empty:
            st.subheader("📈 Visual Analytics")

            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                st.write("**💰 Balance Over Time**")
                balance_chart_data = create_balance_chart(calculation_df)
                st.line_chart(balance_chart_data, height=300)

            with chart_col2:
                st.write("**📈 Cumulative Interest Over Time**")
                interest_chart_data = create_interest_chart(calculation_df)
                st.area_chart(interest_chart_data, height=300)

        # Detailed calculation log
        if show_detailed_log:
            st.subheader("📋 Daily Calculation Log")

            # Add filtering options
            col1, col2 = st.columns(2)
            with col1:
                date_filter = st.selectbox(
                    "Filter by period:",
                    ["All", "Last 30 days", "Last 90 days", "Last year"]
                )

            with col2:
                balance_filter = st.number_input(
                    "Minimum balance to show:",
                    min_value=0.0,
                    value=0.0,
                    step=100.0
                )

            # Apply filters
            filtered_df = calculation_df.copy()

            if date_filter != "All":
                days_map = {"Last 30 days": 30, "Last 90 days": 90, "Last year": 365}
                cutoff_date = (datetime.now() - timedelta(days=days_map[date_filter])).strftime("%d/%m/%Y")
                filtered_df = filtered_df[filtered_df['Date'] >= cutoff_date]

            if balance_filter > 0:
                filtered_df = filtered_df[filtered_df['Balance'] >= balance_filter]

            st.dataframe(
                filtered_df, 
                use_container_width=True, 
                height=400,
                hide_index=True
            )

        # Enhanced download options
        st.subheader("📥 Export Options")
        col1, col2, col3 = st.columns(3)

        with col1:
            csv_data = calculation_df.to_csv(index=False)
            st.download_button(
                label="📊 Download Full Report (CSV)",
                data=csv_data,
                file_name=f"interest_calculation_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        with col2:
            summary_data = f"""INTEREST CALCULATION SUMMARY
================================
Generated: {datetime.now().strftime('%d/%m/%Y %H:%M')}
Period: {ledger_df['Date'].min().strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}

FINANCIAL SUMMARY
-----------------
Total Interest Earned: £{total_interest:,.2f}
Final Balance: £{final_balance:,.2f}
Average Balance: £{stats['avg_balance']:,.2f}
Maximum Balance: £{stats['max_balance']:,.2f}
Minimum Balance: £{stats['min_balance']:,.2f}

CALCULATION DETAILS
-------------------
Total Days Calculated: {stats['total_days']}
Days Earning Interest: {stats['days_earning_interest']}
Interest Efficiency: {efficiency:.1f}%
Total Transactions: {len(ledger_df)}
Net Transaction Value: £{ledger_df['Change'].sum():,.2f}

Generated by Interest Calculator Dashboard
Built by Colby Ballan
"""
            st.download_button(
                label="📄 Download Summary (TXT)",
                data=summary_data,
                file_name=f"interest_summary_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain",
                use_container_width=True
            )

        with col3:
            # Create a simple Excel-style export with multiple sheets worth of data
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                calculation_df.to_excel(writer, sheet_name='Daily Calculations', index=False)
                ledger_df.to_excel(writer, sheet_name='Transactions', index=False)

                # Summary sheet
                summary_df = pd.DataFrame({
                    'Metric': ['Total Interest', 'Final Balance', 'Average Balance', 'Max Balance', 'Min Balance', 'Total Days', 'Interest Days'],
                    'Value': [total_interest, final_balance, stats['avg_balance'], stats['max_balance'], stats['min_balance'], stats['total_days'], stats['days_earning_interest']]
                })
                summary_df.to_excel(writer, sheet_name='Summary', index=False)

            st.download_button(
                label="📈 Download Excel Report",
                data=excel_buffer.getvalue(),
                file_name=f"interest_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

# === Enhanced Footer ===
def display_footer():
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; padding: 30px; background: linear-gradient(90deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 10px; margin-top: 2rem;'>
            <h3 style='color: #495057; margin-bottom: 10px;'>💼 Professional Interest Calculator</h3>
            <p style='color: #6c757d; margin-bottom: 5px;'>Advanced financial calculations with interactive analytics</p>
            <p style='color: #6c757d; font-size: 0.9em;'>Built with ❤️ by <strong>Colby Ballan</strong></p>
            <div style='margin-top: 15px; font-size: 0.8em; color: #868e96;'>
                <span>🚀 Powered by Streamlit</span> | 
                <span>📊 Enhanced Analytics</span> | 
                <span>⚡ Optimized for Performance</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
    display_footer()