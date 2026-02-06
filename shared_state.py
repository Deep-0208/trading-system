"""
Pivot ITM Trading System - Shared State Manager
In-memory state accessible by both strategy engine and dashboard
"""

import threading
from datetime import datetime
from collections import deque

class SharedState:
    """Thread-safe singleton for sharing state between strategy and dashboard"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._lock = threading.RLock()
        
        # Market data
        self.market_status = "CLOSED"
        self.spot_price = None
        self.pivot = None
        self.bias = None
        
        # Strategy state
        self.status = "WAITING_FOR_MARKET"
        self.distance_to_pivot = None
        self.in_trade = False
        
        # Current trade
        self.current_trade = {}
        
        # Trade history (keep last 100)
        self.trades = deque(maxlen=100)
        
        # Event feed (keep last 200)
        self.events = deque(maxlen=200)
        
        # Performance metrics
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0.0
        self.max_drawdown = 0.0
        
        # Mode
        self.mode = "PAPER"
        
        # Date
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        
        self._initialized = True
    
    def update_market(self, spot_price=None, pivot=None, bias=None, status=None):
        """Update market data"""
        with self._lock:
            if spot_price is not None:
                self.spot_price = spot_price
            if pivot is not None:
                self.pivot = pivot
            if bias is not None:
                self.bias = bias
            if status is not None:
                self.market_status = status
            
            # Calculate distance to pivot
            if self.spot_price and self.pivot:
                self.distance_to_pivot = round(self.spot_price - self.pivot, 2)
    
    def update_strategy_status(self, status):
        """Update strategy status"""
        with self._lock:
            self.status = status
            self.add_event(f"Status: {status}")
    
    def enter_trade(self, symbol, direction, entry_price, quantity, stop_loss, profit_target):
        """Record trade entry"""
        with self._lock:
            self.in_trade = True
            self.current_trade = {
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "quantity": quantity,
                "stop_loss": stop_loss,
                "profit_target": profit_target,
                "entry_time": datetime.now().strftime("%H:%M:%S"),
                "current_price": entry_price,
                "pnl": 0.0,
                "pnl_percent": 0.0
            }
            self.add_event(f"Trade entered: {direction} {symbol} @ ₹{entry_price}")
    
    def update_trade_price(self, current_price):
        """Update current trade price and PnL"""
        with self._lock:
            if self.in_trade and self.current_trade:
                self.current_trade["current_price"] = current_price
                entry = self.current_trade["entry_price"]
                qty = self.current_trade["quantity"]
                pnl = (current_price - entry) * qty
                pnl_percent = ((current_price - entry) / entry) * 100
                self.current_trade["pnl"] = round(pnl, 2)
                self.current_trade["pnl_percent"] = round(pnl_percent, 2)
    
    def exit_trade(self, exit_price, exit_reason):
        """Record trade exit"""
        with self._lock:
            if not self.in_trade:
                return
            
            # Calculate final PnL
            entry = self.current_trade["entry_price"]
            qty = self.current_trade["quantity"]
            pnl = (exit_price - entry) * qty
            pnl_percent = ((exit_price - entry) / entry) * 100
            
            # Create trade record
            trade_record = {
                "entry_time": self.current_trade["entry_time"],
                "exit_time": datetime.now().strftime("%H:%M:%S"),
                "direction": self.current_trade["direction"],
                "symbol": self.current_trade["symbol"],
                "entry_price": entry,
                "exit_price": exit_price,
                "quantity": qty,
                "pnl": round(pnl, 2),
                "pnl_percent": round(pnl_percent, 2),
                "exit_reason": exit_reason
            }
            
            # Add to history
            self.trades.append(trade_record)
            
            # Update metrics
            self.total_trades += 1
            self.total_pnl += pnl
            if pnl > 0:
                self.wins += 1
            else:
                self.losses += 1
            
            # Update max drawdown
            if self.total_pnl < self.max_drawdown:
                self.max_drawdown = self.total_pnl
            
            # Clear current trade
            self.in_trade = False
            self.current_trade = {}
            
            self.add_event(f"Trade exited: {exit_reason} | P&L: ₹{pnl:.2f} ({pnl_percent:+.2f}%)")
    
    def add_event(self, message):
        """Add event to feed"""
        with self._lock:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.events.append({"time": timestamp, "message": message})
    
    def get_state(self):
        """Get complete state snapshot"""
        with self._lock:
            win_rate = (self.wins / self.total_trades * 100) if self.total_trades > 0 else 0
            
            return {
                "market_status": self.market_status,
                "spot_price": self.spot_price,
                "pivot": self.pivot,
                "bias": self.bias,
                "status": self.status,
                "distance_to_pivot": self.distance_to_pivot,
                "in_trade": self.in_trade,
                "current_trade": dict(self.current_trade),
                "trades": list(self.trades),
                "events": list(self.events),
                "metrics": {
                    "total_trades": self.total_trades,
                    "wins": self.wins,
                    "losses": self.losses,
                    "win_rate": round(win_rate, 1),
                    "total_pnl": round(self.total_pnl, 2),
                    "max_drawdown": round(self.max_drawdown, 2)
                },
                "mode": self.mode,
                "current_date": self.current_date
            }

# Global instance
state = SharedState()
