"""
Pivot ITM Trading System - Part 1: Configuration & Utilities
Handles configuration, logging, state management, and utility functions
"""

import os
import sys
import time
import logging
from datetime import datetime, date, timedelta

import pyotp
import pandas as pd
from dotenv import load_dotenv
from growwapi import GrowwAPI


# =============================================================================
# CONFIGURATION
# =============================================================================

# Trading mode
TRADING_MODE = "PAPER"  # Options: PAPER, LIVE

# Logging
LOG_FILE = "pivot_itm_trading.log"
LOG_LEVEL = logging.INFO
JOURNAL_FILE = "trade_journal.csv"

# Position sizing (FIXED LOT MODE)
NIFTY_LOT_SIZE = 65        # Exchange fixed
TRADE_LOTS = 1             # 👈 CHANGE THIS ONLY (1, 2, 3...)

# Risk management
MAX_DAILY_TRADES = 2
PIVOT_BUFFER_POINTS = 25  # ⚠️ CRITICAL: Pullback zone around pivot
STOP_LOSS_PERCENT = 0.10  # 10% option stop loss
PROFIT_TARGET_PERCENT = 0.10  # 10% profit target

# Trading hours
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
EOD_EXIT = "15:20"  # Exit before close
ENTRY_CUTOFF = "15:20"   # ❗ No new trades after 12 PM
BIAS_CANDLE_START = "09:15"
BIAS_CANDLE_END = "09:20"

# API settings
MAX_RETRIES = 3
RETRY_DELAY_SEC = 2
CIRCUIT_BREAKER_FAILURES = 5
CIRCUIT_BREAKER_TIMEOUT_SEC = 300

# Validation ranges
MIN_OPTION_PRICE = 1.0
MAX_OPTION_PRICE = 1000.0
MIN_SPOT_PRICE = 15000
MAX_SPOT_PRICE = 30000

# Status logging
HEARTBEAT_INTERVAL_SEC = 600  # 10 minutes

# NSE holidays for 2026
HOLIDAYS_2026 = {
    date(2026, 1, 15), date(2026, 1, 26), date(2026, 3, 3), date(2026, 3, 26),
    date(2026, 3, 31), date(2026, 4, 3), date(2026, 4, 14), date(2026, 5, 1),
    date(2026, 5, 28), date(2026, 6, 26), date(2026, 9, 14), date(2026, 10, 2),
    date(2026, 10, 20), date(2026, 11, 10), date(2026, 11, 24), date(2026, 12, 25),
}


# =============================================================================
# GLOBAL STATE
# =============================================================================

executed_trades_count = 0
current_position = None
last_trading_date = None
daily_pivot_point = None
instruments_data = None
instrument_lookup_cache = {}
last_status_timestamp = None
last_heartbeat_timestamp = None

# Daily bias state
daily_bias = None          # "BULLISH" or "BEARISH"
bias_lock_date = None
bias_candle_data = None


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================

class CircuitBreaker:
    """Prevents repeated failures by temporarily halting operations"""
    
    def __init__(self, threshold=5, timeout=300):
        self.failure_count = 0
        self.threshold = threshold
        self.timeout = timeout
        self.opened_at = None
    
    def record_failure(self):
        """Increment failure count and open circuit if threshold reached"""
        self.failure_count += 1
        if self.failure_count >= self.threshold:
            self.opened_at = time.time()
            logging.error(f"🚨 CIRCUIT BREAKER OPENED | Failures: {self.failure_count}/{self.threshold}")
    
    def record_success(self):
        """Reset circuit on successful operation"""
        if self.failure_count > 0:
            logging.info(f"✅ Circuit breaker reset | Previous failures: {self.failure_count}")
        self.failure_count = 0
        self.opened_at = None
    
    def is_open(self):
        """Check if circuit is currently open"""
        if not self.opened_at:
            return False
        
        elapsed = time.time() - self.opened_at
        if elapsed > self.timeout:
            logging.info(f"🔄 Circuit breaker timeout expired | Resetting after {int(elapsed)}s")
            self.failure_count = 0
            self.opened_at = None
            return False
        
        return True
    
    def status(self):
        """Get current status string"""
        if self.opened_at:
            remaining = max(0, self.timeout - int(time.time() - self.opened_at))
            return f"OPEN ({remaining}s remaining, {self.failure_count} failures)"
        return f"CLOSED ({self.failure_count}/{self.threshold} failures)"


# Initialize circuit breakers for critical operations
spot_price_breaker = CircuitBreaker(CIRCUIT_BREAKER_FAILURES, CIRCUIT_BREAKER_TIMEOUT_SEC)
option_price_breaker = CircuitBreaker(CIRCUIT_BREAKER_FAILURES, CIRCUIT_BREAKER_TIMEOUT_SEC)


# =============================================================================
# LOGGING SETUP
# =============================================================================

def initialize_logging():
    """Configure logging to file and console"""
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)

    # Console handler with UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logging.info("=" * 80)
    logging.info("🟢 LOGGING SYSTEM INITIALIZED")
    logging.info("=" * 80)


def log_strategy_banner():
    """Display strategy overview at startup"""
    logging.info("")
    logging.info("╔" + "═" * 78 + "╗")
    logging.info("║" + " " * 78 + "║")
    logging.info("║" + "        PIVOT ITM TRADING SYSTEM v2.1 - STRATEGY OVERVIEW".center(78) + "║")
    logging.info("║" + " " * 78 + "║")
    logging.info("╚" + "═" * 78 + "╝")
    logging.info("")
    logging.info("📋 STRATEGY RULES:")
    logging.info("   1️⃣  Calculate pivot from previous day's H, L, C")
    logging.info("   2️⃣  Determine bias from first 5-min candle (09:15-09:20)")
    logging.info("   3️⃣  Wait for pullback to pivot zone (±25 points)")
    logging.info("   4️⃣  Enter ITM option ONLY in bias direction")
    logging.info("   5️⃣  Exit at ±10% of option entry price")
    logging.info("")
    logging.info("⚙️  PARAMETERS:")
    logging.info(f"   • Pivot Buffer Zone : ±{PIVOT_BUFFER_POINTS} points")
    logging.info(f"   • Stop Loss         : {STOP_LOSS_PERCENT*100:.0f}% of option price")
    logging.info(f"   • Profit Target     : {PROFIT_TARGET_PERCENT*100:.0f}% of option price")
    logging.info(f"   • Max Daily Trades  : {MAX_DAILY_TRADES}")
    logging.info(f"   • Fixed Lots        : {TRADE_LOTS} (Lot size = {NIFTY_LOT_SIZE})")
    logging.info("")
    logging.info("=" * 80)


def log_daily_bias_banner(first_candle, pivot, bias):
    """Banner-style logging for daily bias determination"""
    logging.info("")
    logging.info("╔" + "═" * 78 + "╗")
    logging.info("║" + " " * 78 + "║")
    logging.info("║" + "           🎯 DAILY MARKET BIAS CONFIRMED 🎯".center(78) + "║")
    logging.info("║" + " " * 78 + "║")
    logging.info("╚" + "═" * 78 + "╝")
    logging.info("")
    logging.info(f"📍 Pivot Point        : {pivot:.2f}")
    logging.info(f"🕒 Bias Candle Time   : {BIAS_CANDLE_START} - {BIAS_CANDLE_END}")
    logging.info(f"📊 Candle OHLC        : O={first_candle['open']:.2f}, H={first_candle['high']:.2f}, "
                 f"L={first_candle['low']:.2f}, C={first_candle['close']:.2f}")
    logging.info("")
    
    close_price = first_candle['close']
    diff = close_price - pivot
    
    if bias == "BULLISH":
        logging.info("🟢 MARKET BIAS        : BULLISH")
        logging.info(f"📈 First Candle       : Closed {diff:.2f} points ABOVE pivot")
        logging.info("🎯 Trade Direction    : BUY CALL (CE) on pullback")
        logging.info(f"📍 Entry Zone         : {pivot - PIVOT_BUFFER_POINTS:.2f} - {pivot + PIVOT_BUFFER_POINTS:.2f}")
        logging.info("⚠️  Wait for pullback to pivot zone before entering")
    elif bias == "BEARISH":
        logging.info("🔴 MARKET BIAS        : BEARISH")
        logging.info(f"📉 First Candle       : Closed {abs(diff):.2f} points BELOW pivot")
        logging.info("🎯 Trade Direction    : BUY PUT (PE) on pullback")
        logging.info(f"📍 Entry Zone         : {pivot - PIVOT_BUFFER_POINTS:.2f} - {pivot + PIVOT_BUFFER_POINTS:.2f}")
        logging.info("⚠️  Wait for pullback to pivot zone before entering")
    
    logging.info("")
    logging.info("🔒 Bias is now LOCKED for the day - will not change")
    logging.info("=" * 80)
    logging.info("")


def log_trade_to_journal(trade, exit_price, exit_reason):
    """Append trade to CSV journal with detailed logging"""
    pnl = (exit_price - trade["entry_price"]) * trade["quantity"]
    pnl_percent = ((exit_price - trade["entry_price"]) / trade["entry_price"]) * 100
    
    trade_record = {
        "date": date.today(),
        "symbol": trade["symbol"],
        "direction": trade["direction"],
        "entry_price": trade["entry_price"],
        "exit_price": exit_price,
        "quantity": trade["quantity"],
        "invested": trade["invested"],
        "pnl": round(pnl, 2),
        "pnl_percent": round(pnl_percent, 2),
        "exit_reason": exit_reason,
        "entry_time": trade["entry_time"],
        "exit_time": datetime.now(),
        "stop_loss": trade.get("stop_loss"),
        "profit_target": trade.get("profit_target"),
        "pivot": trade.get("pivot")
    }

    df = pd.DataFrame([trade_record])
    file_exists = os.path.isfile(JOURNAL_FILE)
    df.to_csv(JOURNAL_FILE, mode="a", header=not file_exists, index=False)

    # Enhanced logging
    result_emoji = "✅" if pnl > 0 else "❌" if pnl < 0 else "➖"
    logging.info("")
    logging.info("=" * 80)
    logging.info(f"{result_emoji} TRADE LOGGED TO JOURNAL")
    logging.info("=" * 80)
    logging.info(f"📝 P&L Amount  : ₹{pnl:,.2f}")
    logging.info(f"📊 P&L Percent : {pnl_percent:+.2f}%")
    logging.info(f"📄 Symbol      : {trade['symbol']}")
    logging.info(f"🚪 Exit Reason : {exit_reason}")
    logging.info("=" * 80)
    logging.info("")


def log_system_heartbeat():
    """Log periodic system status"""
    position_status = "OPEN" if current_position else "NONE"
    bias_status = daily_bias if daily_bias else "NOT SET"
    
    logging.info("")
    logging.info("╔" + "═" * 78 + "╗")
    logging.info("║" + "                    💓 SYSTEM HEARTBEAT 💓".center(78) + "║")
    logging.info("╚" + "═" * 78 + "╝")
    logging.info(f"📅 Date              : {date.today()}")
    logging.info(f"⏰ Time              : {datetime.now().strftime('%H:%M:%S')}")
    logging.info(f"🔢 Trades Today      : {executed_trades_count}/{MAX_DAILY_TRADES}")
    logging.info(f"📊 Position Status   : {position_status}")
    logging.info(f"🧠 Daily Bias        : {bias_status}")
    logging.info(f"📍 Pivot Point       : {daily_pivot_point if daily_pivot_point else 'Not Set'}")
    logging.info(f"🔌 Spot Breaker      : {spot_price_breaker.status()}")
    logging.info(f"🔌 Option Breaker    : {option_price_breaker.status()}")
    logging.info("=" * 80)
    logging.info("")


def generate_daily_report(report_date=None):
    """Generate end-of-day performance summary"""
    if not os.path.exists(JOURNAL_FILE):
        logging.info("📊 No trade journal found for report generation")
        return

    if report_date is None:
        report_date = date.today()

    try:
        df = pd.read_csv(JOURNAL_FILE)
    except pd.errors.EmptyDataError:
        logging.info(f"📊 No trades logged on {report_date} (empty journal)")
        return

    if "date" not in df.columns:
        logging.warning("⚠️  Journal missing 'date' column")
        return

    df['date'] = pd.to_datetime(df['date']).dt.date
    day_trades = df[df['date'] == report_date]

    if day_trades.empty:
        logging.info(f"📊 No trades executed on {report_date}")
        return

    total_pnl = day_trades['pnl'].sum()
    wins = len(day_trades[day_trades['pnl'] > 0])
    losses = len(day_trades[day_trades['pnl'] <= 0])
    win_rate = (wins / len(day_trades) * 100)

    avg_win = day_trades[day_trades['pnl'] > 0]['pnl'].mean() if wins > 0 else 0
    avg_loss = day_trades[day_trades['pnl'] <= 0]['pnl'].mean() if losses > 0 else 0

    logging.info("📊 DAILY PERFORMANCE REPORT")
    logging.info(f"Date        : {report_date}")
    logging.info(f"Trades      : {len(day_trades)}")
    logging.info(f"Wins        : {wins}")
    logging.info(f"Losses      : {losses}")
    logging.info(f"Win Rate    : {win_rate:.1f}%")
    logging.info(f"Total P&L   : ₹{total_pnl:,.2f}")
    logging.info(f"Avg Win     : ₹{avg_win:,.2f}")
    logging.info(f"Avg Loss    : ₹{avg_loss:,.2f}")


# =============================================================================
# MARKET CHECKS
# =============================================================================

def is_trading_day():
    """Check if today is a valid trading day"""
    today = date.today()
    
    if today.weekday() >= 5:
        logging.warning(f"📅 {today.strftime('%A')} - Weekend, market closed")
        return False
    
    if today in HOLIDAYS_2026:
        logging.warning(f"📅 {today} - NSE Holiday, market closed")
        return False
    
    return True


def is_market_open():
    """Check if current time is within market hours"""
    now = datetime.now().time()
    open_time = datetime.strptime(MARKET_OPEN, "%H:%M").time()
    close_time = datetime.strptime(MARKET_CLOSE, "%H:%M").time()
    is_open = open_time <= now <= close_time
    
    if not is_open:
        logging.debug(f"⏰ Market closed | Current: {now.strftime('%H:%M')} | Hours: {MARKET_OPEN}-{MARKET_CLOSE}")
    
    return is_open


def get_sleep_duration():
    """Calculate intelligent sleep duration"""
    if not is_market_open():
        return 300
    elif current_position is None:
        return 30
    else:
        return 5


# =============================================================================
# GROWW API INITIALIZATION
# =============================================================================

def initialize_groww_api():
    """Login to Groww API and return client"""
    logging.info("🔐 Initializing Groww API connection...")
    
    load_dotenv()
    api_key = os.getenv("GROWW_API_KEY")
    totp_secret = os.getenv("GROWW_TOTP_SECRET")

    if not api_key or not totp_secret:
        logging.error("❌ CRITICAL: Missing API credentials in .env file")
        logging.error("   Required: GROWW_API_KEY, GROWW_TOTP_SECRET")
        sys.exit(1)

    try:
        totp_code = pyotp.TOTP(totp_secret).now()
        logging.info(f"🔑 TOTP code generated: {totp_code[:2]}****")
        
        access_token = GrowwAPI.get_access_token(api_key=api_key, totp=totp_code)
        client = GrowwAPI(access_token)
        
        logging.info("✅ Groww API connected successfully")
        return client
    except Exception as e:
        logging.exception(f"❌ Groww API login failed: {e}")
        sys.exit(1)


def load_instrument_data(groww):
    """Load FNO instruments from Groww"""
    global instruments_data
    
    logging.info("📥 Loading FNO instruments from Groww...")
    try:
        instruments_data = groww.get_all_instruments()
        instruments_data = instruments_data[instruments_data["segment"] == "FNO"]
        logging.info(f"✅ Loaded {len(instruments_data):,} FNO instruments")
    except Exception as e:
        logging.exception(f"❌ Failed to load instruments: {e}")
        sys.exit(1)
