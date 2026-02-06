# 📊 Pivot ITM Strategy Dashboard

A **stunning, production-grade real-time trading dashboard** for monitoring the Pivot ITM Options Trading Strategy. Built with Flask backend and a distinctive, modern UI that updates live every 2 seconds.

---

## ✨ Features

### 🎯 Real-time Monitoring
- **Live market data** - Spot price, pivot point, bias, distance
- **Strategy status** - Clear visual indicators of current state
- **Active trade tracking** - Entry price, current price, live P&L
- **Performance metrics** - Win rate, total P&L, max drawdown
- **Trade history** - Last 10 trades with full details
- **Event feed** - Chronological log of all strategy events

### 🎨 Distinctive Design
- **Cyberpunk-inspired aesthetic** with neon accents and glowing effects
- **Monospace typography** (JetBrains Mono) for technical precision
- **Smooth animations** - State transitions, data updates, event additions
- **Responsive grid layout** - Works on all screen sizes
- **Dark theme** optimized for extended trading sessions
- **Real-time connection indicator** - Know if dashboard is synced

### 🔧 Technical Excellence
- **Thread-safe state management** - Safe concurrent access
- **Zero database required** - All in-memory using Python collections
- **RESTful API** - Easy integration with any trading system
- **Auto-refresh** - Polls every 2 seconds for updates
- **No file I/O** - Perfect for cloud environments (Groww Cloud)

---

## 📁 File Structure

```
pivot_itm_trading/
├── shared_state.py           # Thread-safe state manager
├── dashboard_server.py       # Flask API server
├── templates/
│   └── dashboard.html        # Dashboard UI
├── dashboard_demo.py         # Standalone demo
├── integration_guide.py      # How to integrate with strategy
└── DASHBOARD_README.md       # This file
```

---

## 🚀 Quick Start

### Option 1: Run Demo (Test Dashboard)

```bash
# Install dependencies
pip install flask flask-cors

# Run demo with simulated trading
python dashboard_demo.py

# Open browser
http://127.0.0.1:5000
```

The demo will simulate:
- Market data updates
- Bias determination
- Two trades (one winner, one loser)
- Live P&L tracking
- Event logging

### Option 2: Integrate with Your Trading System

```bash
# 1. Copy these files to your project:
#    - shared_state.py
#    - dashboard_server.py
#    - templates/dashboard.html

# 2. Modify part3_position_and_main.py
# See integration_guide.py for detailed steps

# 3. Run your trading system
python part3_position_and_main.py

# 4. Dashboard auto-starts at:
http://127.0.0.1:5000
```

---

## 🔌 Integration Guide

### Step 1: Import Required Modules

```python
# Add to part3_position_and_main.py
from shared_state import state
from dashboard_server import start_dashboard
```

### Step 2: Start Dashboard in main()

```python
def main():
    initialize_logging()
    log_strategy_banner()
    
    # Start dashboard
    start_dashboard(host='127.0.0.1', port=5000)
    logging.info("📊 Dashboard: http://127.0.0.1:5000")
    
    # ... rest of main code ...
```

### Step 3: Update State Throughout Strategy

```python
# When market data changes
state.update_market(
    spot_price=spot,
    pivot=pivot_point,
    bias=daily_bias,
    status="OPEN"  # or "CLOSED"
)

# When strategy status changes
state.update_strategy_status("WAITING_FOR_PULLBACK")

# When entering a trade
state.enter_trade(
    symbol=symbol,
    direction=direction,
    entry_price=entry_price,
    quantity=quantity,
    stop_loss=stop_loss,
    profit_target=profit_target
)

# During trade - update current price
state.update_trade_price(current_price)

# When exiting trade
state.exit_trade(exit_price, exit_reason)

# Add important events
state.add_event("Bias determined: BULLISH")
state.add_event("Pullback detected")
```

### Step 4: Complete Integration Example

See `integration_guide.py` for full code examples of:
- Modified `enter_position()` function
- Modified `exit_position()` function
- Modified `check_stop_loss()` function
- Modified `check_profit_target()` function
- Modified main trading loop

---

## 📊 Dashboard Layout

```
┌─────────────────────────────────────────────────────────────┐
│  ⚡ PIVOT ITM STRATEGY                    [PAPER MODE]      │
│  Real-time Trading Dashboard v2.1                           │
└─────────────────────────────────────────────────────────────┘

┌──────────────┬──────────────────────────────┬──────────────┐
│ MARKET DATA  │   STRATEGY STATUS            │  METRICS     │
│              │                              │              │
│ • Date       │   ┌────────────────────┐     │ Total Trades │
│ • Status     │   │ WAITING FOR        │     │ Win Rate     │
│ • Spot       │   │ PULLBACK           │     │ Net P&L      │
│ • Pivot      │   └────────────────────┘     │ Max Drawdown │
│ • Bias       │                              │              │
│ • Distance   │                              │              │
└──────────────┴──────────────────────────────┴──────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    LIVE TRADE MONITOR                       │
│                                                             │
│ Symbol  Direction  Entry  Current  P&L Amount  P&L %       │
└─────────────────────────────────────────────────────────────┘

┌──────────────────────────────────┬──────────────────────────┐
│      TRADE HISTORY               │      EVENT FEED          │
│                                  │                          │
│ Time  Dir  Entry  Exit  P&L  %   │ 09:20  Bias: BULLISH    │
│                                  │ 09:48  Waiting pullback  │
│ [Last 10 trades]                 │ 10:01  Pullback detected │
│                                  │ 10:02  Trade entered     │
└──────────────────────────────────┴──────────────────────────┘

                           [●] Connected
```

---

## 🎨 Dashboard Components

### 1. **Market Status Panel** (Top Left)
- Current date
- Market status (OPEN/CLOSED)
- NIFTY spot price (large, highlighted)
- Pivot point
- Daily bias (BULLISH/BEARISH/NEUTRAL)
- Distance from pivot

### 2. **Strategy Status Card** (Top Center)
- Current state with visual indicator
- Glowing animation when in trade
- Color-coded:
  - Green glow = Waiting/Ready
  - Red glow = In trade

Possible states:
- `WAITING_FOR_MARKET`
- `WAITING_FOR_BIAS`
- `WAITING_FOR_PULLBACK`
- `READY_TO_ENTER`
- `IN_TRADE`
- `TRADE_CLOSED`
- `MARKET_CLOSED`

### 3. **Performance Metrics** (Top Right)
- Total trades today
- Win rate percentage
- Net P&L (color-coded)
- Max drawdown

### 4. **Live Trade Monitor** (Middle)
Shows when in trade:
- Symbol
- Direction (CALL/PUT)
- Entry price
- Current price
- P&L amount (with glow effect)
- P&L percentage

### 5. **Trade History Table** (Bottom Left)
Last 10 trades showing:
- Entry/Exit times
- Direction badge
- Entry/Exit prices
- P&L (color-coded)
- Exit reason

### 6. **Event Feed** (Bottom Right)
Scrollable chronological log of:
- System events
- Strategy decisions
- Trade executions
- Errors/warnings

---

## 🎛️ API Endpoints

### `GET /api/state`
Returns complete state snapshot:
```json
{
  "market_status": "OPEN",
  "spot_price": 25210.0,
  "pivot": 25118.2,
  "bias": "BULLISH",
  "status": "IN_TRADE",
  "distance_to_pivot": 91.8,
  "in_trade": true,
  "current_trade": {
    "symbol": "NIFTY25200CE",
    "direction": "CALL",
    "entry_price": 142.50,
    "current_price": 148.30,
    "pnl": 377.00,
    "pnl_percent": 4.07
  },
  "trades": [...],
  "events": [...],
  "metrics": {
    "total_trades": 2,
    "wins": 1,
    "losses": 1,
    "win_rate": 50.0,
    "total_pnl": 142.50,
    "max_drawdown": -895.00
  }
}
```

### `GET /api/health`
Health check endpoint:
```json
{
  "status": "ok",
  "timestamp": 1706543210.123
}
```

---

## 🔧 Configuration

### Change Dashboard Port

```python
# In dashboard_server.py or your main file
start_dashboard(host='127.0.0.1', port=8080)
```

### Customize Update Interval

```javascript
// In dashboard.html, change this line (in milliseconds)
setInterval(fetchState, 2000);  // Default: 2 seconds
```

### Modify Event History Size

```python
# In shared_state.py
self.events = deque(maxlen=200)  # Keep last 200 events
self.trades = deque(maxlen=100)  # Keep last 100 trades
```

---

## 🎨 Design Philosophy

This dashboard follows the **cyberpunk-technical** aesthetic:

- **Typography**: JetBrains Mono for code-like precision
- **Colors**: Neon accents (green/blue/red) on dark background
- **Motion**: Subtle glows, pulses, and slide-ins
- **Layout**: Grid-based, information-dense
- **Feel**: Professional trading terminal meets modern design

**No generic AI aesthetics** - Every detail is intentionally designed:
- Custom gradient backgrounds
- Animated border accents
- Color-coded data points
- Smooth state transitions
- Distinctive monospace feel

---

## 🔒 Safety Features

- **Thread-safe** - Multiple threads can safely update state
- **Read-only UI** - Dashboard cannot execute trades
- **Isolated from strategy** - UI crashes don't affect trading
- **Connection monitoring** - Visual indicator of sync status
- **Error handling** - Graceful degradation on API failures

---

## 📈 Performance

- **Memory efficient** - Circular buffers limit history size
- **Fast updates** - 2-second polling interval
- **No blocking** - Dashboard runs in separate thread
- **Lightweight** - Minimal CPU usage
- **Scalable** - Can handle high-frequency updates

---

## 🐛 Troubleshooting

### Dashboard won't load
```bash
# Check if Flask is installed
pip install flask flask-cors

# Check if port 5000 is available
# Try different port: start_dashboard(port=8080)
```

### Data not updating
```bash
# Verify state.update_*() calls in your trading code
# Check browser console for API errors
# Verify Flask server is running (check logs)
```

### Connection shows "Disconnected"
```bash
# Check if Flask server is running
# Verify API endpoint: http://127.0.0.1:5000/api/health
# Check for firewall/network issues
```

---

## 🚀 Advanced Usage

### Custom Themes

Edit CSS variables in `dashboard.html`:
```css
:root {
    --accent-green: #00ff88;  /* Change to your color */
    --accent-red: #ff3366;
    --accent-blue: #00d4ff;
}
```

### Additional Metrics

Add to `shared_state.py`:
```python
self.avg_profit = 0.0
self.avg_loss = 0.0
# Update in exit_trade()
```

Update dashboard.html to display them.

### Export Trade Data

```python
# In your code
trades_list = list(state.trades)
df = pd.DataFrame(trades_list)
df.to_csv('trades_export.csv')
```

---

## 📝 Requirements

```
flask>=2.0.0
flask-cors>=3.0.0
```

**Python**: 3.8+

**Browser**: Modern browser (Chrome, Firefox, Safari, Edge)

---

## 🎯 Roadmap (Future Enhancements)

- [ ] WebSocket support for real-time push updates
- [ ] Historical chart visualization
- [ ] Trade statistics graphs
- [ ] Multi-day comparison view
- [ ] Export/import trade history
- [ ] Telegram integration for alerts
- [ ] Mobile responsive improvements
- [ ] Dark/light theme toggle
- [ ] Customizable layout

---

## 📞 Support

Issues or questions?
1. Check `integration_guide.py` for examples
2. Run `dashboard_demo.py` to verify dashboard works
3. Review browser console for JavaScript errors
4. Check Flask logs for backend errors

---

## 📄 License

Part of the Pivot ITM Trading System v2.1

---

**Built with ❤️ for algorithmic traders**

*"Trade smarter, not harder"* 📈
