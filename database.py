"""
Database management module
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional

class Database:
    def __init__(self, db_path: str = 'AITradeGame.db'):
        self.db_path = db_path
        
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Providers table (API提供方)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                api_url TEXT NOT NULL,
                api_key TEXT NOT NULL,
                models TEXT,  -- JSON string or comma-separated list of models
                provider_type TEXT DEFAULT 'openai',  -- openai, anthropic, gemini, etc.
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Migration: Add provider_type column if it doesn't exist
        cursor.execute("PRAGMA table_info(providers)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'provider_type' not in columns:
            cursor.execute("ALTER TABLE providers ADD COLUMN provider_type TEXT DEFAULT 'openai'")

        # Models table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                provider_id INTEGER,
                model_name TEXT NOT NULL,
                initial_capital REAL DEFAULT 10000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (provider_id) REFERENCES providers(id)
            )
        ''')
        
        # Portfolios table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                coin TEXT NOT NULL,
                quantity REAL NOT NULL,
                avg_price REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                side TEXT DEFAULT 'long',
                stop_loss REAL DEFAULT NULL,
                profit_target REAL DEFAULT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id),
                UNIQUE(model_id, coin, side)
            )
        ''')

        # Migration: Add stop_loss / profit_target columns if they don't exist
        cursor.execute("PRAGMA table_info(portfolios)")
        portfolio_columns = [col[1] for col in cursor.fetchall()]
        if 'stop_loss' not in portfolio_columns:
            cursor.execute("ALTER TABLE portfolios ADD COLUMN stop_loss REAL DEFAULT NULL")
        if 'profit_target' not in portfolio_columns:
            cursor.execute("ALTER TABLE portfolios ADD COLUMN profit_target REAL DEFAULT NULL")
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                coin TEXT NOT NULL,
                signal TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                side TEXT DEFAULT 'long',
                pnl REAL DEFAULT 0,
                fee REAL DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')
        
        # Conversations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                user_prompt TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                cot_trace TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')
        
        # Account values history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                total_value REAL NOT NULL,
                cash REAL NOT NULL,
                positions_value REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')

        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trading_frequency_minutes INTEGER DEFAULT 60,
                trading_fee_rate REAL DEFAULT 0.002,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Insert default settings if no settings exist
        cursor.execute('SELECT COUNT(*) FROM settings')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO settings (trading_frequency_minutes, trading_fee_rate)
                VALUES (60, 0.002)
            ''')

        conn.commit()
        conn.close()
    
    # ============ Model Management (Moved) ============
    
    def delete_model(self, model_id: int):
        """Delete model and related data"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM models WHERE id = ?', (model_id,))
        cursor.execute('DELETE FROM portfolios WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM trades WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM conversations WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM account_values WHERE model_id = ?', (model_id,))
        conn.commit()
        conn.close()
    
    # ============ Portfolio Management ============
    
    def update_position(self, model_id: int, coin: str, quantity: float,
                       avg_price: float, leverage: int = 1, side: str = 'long',
                       stop_loss: float = None, profit_target: float = None):
        """Update position (stop_loss / profit_target 为 AI 设定的风控价，用于引擎兜底执行)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO portfolios (model_id, coin, quantity, avg_price, leverage, side, stop_loss, profit_target, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(model_id, coin, side) DO UPDATE SET
                quantity = excluded.quantity,
                avg_price = excluded.avg_price,
                leverage = excluded.leverage,
                stop_loss = excluded.stop_loss,
                profit_target = excluded.profit_target,
                updated_at = CURRENT_TIMESTAMP
        ''', (model_id, coin, quantity, avg_price, leverage, side, stop_loss, profit_target))
        conn.commit()
        conn.close()
    
    def get_portfolio(self, model_id: int, current_prices: Dict = None) -> Dict:
        """Get portfolio with positions and P&L
        
        Args:
            model_id: Model ID
            current_prices: Current market prices {coin: price} for unrealized P&L calculation
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Get positions
        cursor.execute('''
            SELECT * FROM portfolios WHERE model_id = ? AND quantity > 0
        ''', (model_id,))
        positions = [dict(row) for row in cursor.fetchall()]
        
        # Get initial capital
        cursor.execute('SELECT initial_capital FROM models WHERE id = ?', (model_id,))
        initial_capital = cursor.fetchone()['initial_capital']
        
        # Calculate realized P&L and total fees (pnl 已含开仓/平仓手续费，故为净盈亏)
        cursor.execute('''
            SELECT COALESCE(SUM(pnl), 0) as total_pnl,
                   COALESCE(SUM(fee), 0) as total_fee
            FROM trades WHERE model_id = ?
        ''', (model_id,))
        pnl_row = cursor.fetchone()
        realized_pnl = pnl_row['total_pnl']
        total_fee = pnl_row['total_fee']
        
        # Calculate margin used
        margin_used = sum([p['quantity'] * p['avg_price'] / p['leverage'] for p in positions])
        
        # Calculate unrealized P&L (if prices provided)
        unrealized_pnl = 0
        if current_prices:
            for pos in positions:
                coin = pos['coin']
                if coin in current_prices:
                    current_price = current_prices[coin]
                    entry_price = pos['avg_price']
                    quantity = pos['quantity']
                    
                    # Add current price to position
                    pos['current_price'] = current_price
                    
                    # Calculate position P&L
                    if pos['side'] == 'long':
                        pos_pnl = (current_price - entry_price) * quantity
                    else:  # short
                        pos_pnl = (entry_price - current_price) * quantity
                    
                    pos['pnl'] = pos_pnl
                    unrealized_pnl += pos_pnl
                else:
                    pos['current_price'] = None
                    pos['pnl'] = 0
        else:
            for pos in positions:
                pos['current_price'] = None
                pos['pnl'] = 0
        
        # Cash = initial capital + realized P&L - margin used
        cash = initial_capital + realized_pnl - margin_used
        
        # Position value = quantity * entry price (not margin!)
        positions_value = sum([p['quantity'] * p['avg_price'] for p in positions])
        
        # Total account value = initial capital + realized P&L + unrealized P&L
        total_value = initial_capital + realized_pnl + unrealized_pnl
        
        conn.close()
        
        return {
            'model_id': model_id,
            'cash': cash,
            'positions': positions,
            'positions_value': positions_value,
            'margin_used': margin_used,
            'total_value': total_value,
            'realized_pnl': realized_pnl,
            'unrealized_pnl': unrealized_pnl,
            'total_fee': total_fee
        }
    
    def close_position(self, model_id: int, coin: str, side: str = 'long'):
        """Close position"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM portfolios WHERE model_id = ? AND coin = ? AND side = ?
        ''', (model_id, coin, side))
        conn.commit()
        conn.close()
    
    # ============ Trade Records ============
    
    def add_trade(self, model_id: int, coin: str, signal: str, quantity: float,
              price: float, leverage: int = 1, side: str = 'long', pnl: float = 0, fee: float = 0):  # 新增fee参数
        """Add trade record with fee"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (model_id, coin, signal, quantity, price, leverage, side, pnl, fee)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (model_id, coin, signal, quantity, price, leverage, side, pnl, fee))  # 传入fee值
        conn.commit()
        conn.close()
    
    def get_trades(self, model_id: int, limit: int = 50,
                   start_time: str = None, end_time: str = None) -> List[Dict]:
        """Get trade history

        Args:
            model_id: Model ID
            limit: Max records to return
            start_time: Optional UTC time string 'YYYY-MM-DD HH:MM:SS' (inclusive)
            end_time: Optional UTC time string 'YYYY-MM-DD HH:MM:SS' (inclusive)
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        sql = 'SELECT * FROM trades WHERE model_id = ?'
        params = [model_id]
        if start_time:
            sql += ' AND timestamp >= ?'
            params.append(start_time)
        if end_time:
            sql += ' AND timestamp <= ?'
            params.append(end_time)
        sql += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # ============ Round-Trip Trade View ============

    def get_round_trips(self, model_id: int, limit: int = 100,
                        start_time: str = None, end_time: str = None) -> Dict:
        """构建回合配对视图：把开仓和平仓配成完整的一笔交易，并计算复盘统计

        配对规则:
        - buy_to_enter / sell_to_enter 视为开仓；同一(币种, 方向)的后续开仓会覆盖旧持仓，故直接新建回合
        - close_position 匹配最近一次同(币种, 方向)的开仓
        - 无匹配开仓的平仓（修复 bug 前的历史持仓）通过 net_pnl + fee 反推开仓价
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        sql = 'SELECT * FROM trades WHERE model_id = ?'
        params = [model_id]
        if start_time:
            sql += ' AND timestamp >= ?'
            params.append(start_time)
        if end_time:
            sql += ' AND timestamp <= ?'
            params.append(end_time)
        sql += ' ORDER BY timestamp ASC, id ASC'
        cursor.execute(sql, params)
        trades = [dict(row) for row in cursor.fetchall()]
        conn.close()

        open_signals = {'buy_to_enter', 'sell_to_enter'}
        round_trips = []
        open_map = {}            # (coin, side) -> 当前未平仓的回合
        closed_count = 0
        win_count = 0
        total_realized_pnl = 0.0
        total_fee = 0.0

        def _finalize_close(rt: Dict, close_price: float, close_time: str,
                            pnl: float, fee: float) -> None:
            """填充平仓信息并累计统计"""
            # 回合净盈亏 = 平仓净利润 - 开仓费；回合总费用 = 开仓费 + 平仓费
            open_fee = rt.get('open_fee') or 0.0
            net_pnl = pnl - open_fee
            rt['close_price'] = close_price
            rt['close_time'] = close_time
            rt['pnl'] = net_pnl
            rt['fee'] = open_fee + fee
            rt['status'] = 'closed'

            # 收益率（按价格涨跌幅）
            if rt['open_price'] and rt['open_price'] > 0:
                if rt['side'] == 'long':
                    rt['return_pct'] = (close_price - rt['open_price']) / rt['open_price'] * 100
                else:
                    rt['return_pct'] = (rt['open_price'] - close_price) / rt['open_price'] * 100

            # 持仓时长
            if rt['open_time']:
                try:
                    fmt = '%Y-%m-%d %H:%M:%S'
                    open_dt = datetime.strptime(rt['open_time'], fmt)
                    close_dt = datetime.strptime(close_time, fmt)
                    rt['duration_seconds'] = int((close_dt - open_dt).total_seconds())
                except (ValueError, TypeError):
                    rt['duration_seconds'] = None

            nonlocal closed_count, win_count, total_realized_pnl
            closed_count += 1
            if net_pnl > 0:
                win_count += 1
            total_realized_pnl += net_pnl

        for trade in trades:
            coin = trade['coin']
            signal = trade['signal']
            side = trade.get('side') or 'long'
            fee = trade.get('fee') or 0.0
            total_fee += fee

            key = (coin, side)

            if signal in open_signals:
                # 同一(币种,方向)已有未平仓回合：旧持仓会被新开仓覆盖，标记为 replaced
                old_rt = open_map.get(key)
                if old_rt is not None:
                    old_rt['status'] = 'replaced'
                    old_rt['replaced_by'] = trade['timestamp']
                # 开仓：新建一个回合
                rt = {
                    'coin': coin,
                    'side': side,
                    'quantity': trade['quantity'],
                    'leverage': trade['leverage'],
                    'open_price': trade['price'],
                    'open_time': trade['timestamp'],
                    'close_price': None,
                    'close_time': None,
                    'pnl': None,
                    'fee': fee,
                    'open_fee': fee,
                    'duration_seconds': None,
                    'return_pct': None,
                    'status': 'open'
                }
                open_map[key] = rt
                round_trips.append(rt)

            elif signal == 'close_position':
                rt = open_map.pop(key, None)
                if rt is not None:
                    _finalize_close(rt, trade['price'], trade['timestamp'],
                                    trade.get('pnl') or 0.0, fee)
                else:
                    # 孤儿平仓（历史遗留），从 net_pnl + fee 反推开仓价
                    # net_pnl = (close - entry) * qty - fee (long)
                    qty = trade['quantity']
                    close_price = trade['price']
                    pnl = trade.get('pnl') or 0.0
                    entry = None
                    if qty > 0:
                        gross = pnl + fee
                        if side == 'long':
                            entry = close_price - gross / qty
                        else:
                            entry = close_price + gross / qty
                    rt = {
                        'coin': coin,
                        'side': side,
                        'quantity': qty,
                        'leverage': trade['leverage'],
                        'open_price': round(entry, 8) if entry else None,
                        'open_time': None,
                        'close_price': close_price,
                        'close_time': trade['timestamp'],
                        'pnl': None,
                        'fee': fee,
                        'duration_seconds': None,
                        'return_pct': None,
                        'status': 'open'
                    }
                    _finalize_close(rt, close_price, trade['timestamp'], pnl, fee)
                    round_trips.append(rt)

            # hold 等其他信号忽略

        # 排序：已平仓 > 持仓中 > 被替换，同状态内按时间倒序
        status_rank = {'closed': 2, 'open': 1, 'replaced': 0}
        round_trips.sort(key=lambda r: (status_rank.get(r['status'], 0),
                                        r.get('close_time') or r.get('open_time') or ''),
                         reverse=True)

        closed_returns = [r['return_pct'] for r in round_trips
                          if r['status'] == 'closed' and r['return_pct'] is not None]
        stats = {
            'total_trades': len(trades),
            'total_round_trips': len(round_trips),
            'closed_round_trips': closed_count,
            'open_round_trips': sum(1 for r in round_trips if r['status'] == 'open'),
            'win_rate': (win_count / closed_count * 100) if closed_count > 0 else 0.0,
            'total_realized_pnl': total_realized_pnl,
            'total_fee': total_fee,
            'avg_return_pct': (round(sum(closed_returns) / len(closed_returns), 2)
                               if closed_returns else None)
        }

        return {
            'round_trips': round_trips[:limit],
            'stats': stats
        }

    # ============ Conversation History ============
    
    def add_conversation(self, model_id: int, user_prompt: str, 
                        ai_response: str, cot_trace: str = ''):
        """Add conversation record"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversations (model_id, user_prompt, ai_response, cot_trace)
            VALUES (?, ?, ?, ?)
        ''', (model_id, user_prompt, ai_response, cot_trace))
        conn.commit()
        conn.close()
    
    def get_conversations(self, model_id: int, limit: int = 20,
                          start_time: str = None, end_time: str = None) -> List[Dict]:
        """Get conversation history

        Args:
            model_id: Model ID
            limit: Max records to return
            start_time: Optional UTC time string 'YYYY-MM-DD HH:MM:SS' (inclusive)
            end_time: Optional UTC time string 'YYYY-MM-DD HH:MM:SS' (inclusive)
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        sql = 'SELECT * FROM conversations WHERE model_id = ?'
        params = [model_id]
        if start_time:
            sql += ' AND timestamp >= ?'
            params.append(start_time)
        if end_time:
            sql += ' AND timestamp <= ?'
            params.append(end_time)
        sql += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    # ============ Account Value History ============
    
    def record_account_value(self, model_id: int, total_value: float, 
                            cash: float, positions_value: float):
        """Record account value snapshot"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO account_values (model_id, total_value, cash, positions_value)
            VALUES (?, ?, ?, ?)
        ''', (model_id, total_value, cash, positions_value))
        conn.commit()
        conn.close()
    
    def get_account_value_history(self, model_id: int, limit: int = 100,
                                  start_time: str = None, end_time: str = None) -> List[Dict]:
        """Get account value history

        Args:
            model_id: Model ID
            limit: Max records to return
            start_time: Optional UTC time string 'YYYY-MM-DD HH:MM:SS' (inclusive)
            end_time: Optional UTC time string 'YYYY-MM-DD HH:MM:SS' (inclusive)
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        sql = 'SELECT * FROM account_values WHERE model_id = ?'
        params = [model_id]
        if start_time:
            sql += ' AND timestamp >= ?'
            params.append(start_time)
        if end_time:
            sql += ' AND timestamp <= ?'
            params.append(end_time)
        sql += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_aggregated_account_value_history(self, limit: int = 100) -> List[Dict]:
        """Get aggregated account value history across all models"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get the most recent timestamp for each time point across all models
        cursor.execute('''
            SELECT timestamp,
                   SUM(total_value) as total_value,
                   SUM(cash) as cash,
                   SUM(positions_value) as positions_value,
                   COUNT(DISTINCT model_id) as model_count
            FROM (
                SELECT timestamp,
                       total_value,
                       cash,
                       positions_value,
                       model_id,
                       ROW_NUMBER() OVER (PARTITION BY model_id, DATE(timestamp) ORDER BY timestamp DESC) as rn
                FROM account_values
            ) grouped
            WHERE rn <= 10  -- Keep up to 10 records per model per day for aggregation
            GROUP BY DATE(timestamp), HOUR(timestamp)
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        result = []
        for row in rows:
            result.append({
                'timestamp': row['timestamp'],
                'total_value': row['total_value'],
                'cash': row['cash'],
                'positions_value': row['positions_value'],
                'model_count': row['model_count']
            })

        return result

    def get_multi_model_chart_data(self, limit: int = 100,
                                   start_time: str = None, end_time: str = None) -> List[Dict]:
        """Get chart data for all models to display in multi-line chart

        Args:
            limit: Max records per model
            start_time: Optional UTC time string 'YYYY-MM-DD HH:MM:SS' (inclusive)
            end_time: Optional UTC time string 'YYYY-MM-DD HH:MM:SS' (inclusive)
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get all models
        cursor.execute('SELECT id, name FROM models')
        models = cursor.fetchall()

        chart_data = []

        for model in models:
            model_id = model['id']
            model_name = model['name']

            # Get account value history for this model
            sql = 'SELECT timestamp, total_value FROM account_values WHERE model_id = ?'
            params = [model_id]
            if start_time:
                sql += ' AND timestamp >= ?'
                params.append(start_time)
            if end_time:
                sql += ' AND timestamp <= ?'
                params.append(end_time)
            sql += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)
            cursor.execute(sql, params)

            history = cursor.fetchall()

            if history:
                # Convert to list of dicts with model info
                model_data = {
                    'model_id': model_id,
                    'model_name': model_name,
                    'data': [
                        {
                            'timestamp': row['timestamp'],
                            'value': row['total_value']
                        } for row in history
                    ]
                }
                chart_data.append(model_data)

        conn.close()
        return chart_data

    # ============ Settings Management ============

    def get_settings(self) -> Dict:
        """Get system settings"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT trading_frequency_minutes, trading_fee_rate
            FROM settings
            ORDER BY id DESC
            LIMIT 1
        ''')

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'trading_frequency_minutes': row['trading_frequency_minutes'],
                'trading_fee_rate': row['trading_fee_rate']
            }
        else:
            # Return default settings if none exist
            return {
                'trading_frequency_minutes': 60,
                'trading_fee_rate': 0.002
            }

    def update_settings(self, trading_frequency_minutes: int, trading_fee_rate: float) -> bool:
        """Update system settings"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE settings
                SET trading_frequency_minutes = ?,
                    trading_fee_rate = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id FROM settings ORDER BY id DESC LIMIT 1
                )
            ''', (trading_frequency_minutes, trading_fee_rate))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating settings: {e}")
            conn.close()
            return False

    # ============ Provider Management ============

    def add_provider(self, name: str, api_url: str, api_key: str, models: str = '', provider_type: str = 'openai') -> int:
        """Add new API provider"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO providers (name, api_url, api_key, models, provider_type)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, api_url, api_key, models, provider_type))
        provider_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return provider_id

    def get_provider(self, provider_id: int) -> Optional[Dict]:
        """Get provider information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM providers WHERE id = ?', (provider_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_providers(self) -> List[Dict]:
        """Get all API providers"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM providers ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def delete_provider(self, provider_id: int):
        """Delete provider"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM providers WHERE id = ?', (provider_id,))
        conn.commit()
        conn.close()

    def update_provider(self, provider_id: int, name: str, api_url: str, api_key: str, models: str, provider_type: str = 'openai'):
        """Update provider information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE providers
            SET name = ?, api_url = ?, api_key = ?, models = ?, provider_type = ?
            WHERE id = ?
        ''', (name, api_url, api_key, models, provider_type, provider_id))
        conn.commit()
        conn.close()

    # ============ Model Management (Updated) ============

    def add_model(self, name: str, provider_id: int, model_name: str, initial_capital: float = 10000) -> int:
        """Add new trading model"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO models (name, provider_id, model_name, initial_capital)
            VALUES (?, ?, ?, ?)
        ''', (name, provider_id, model_name, initial_capital))
        model_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return model_id

    def get_model(self, model_id: int) -> Optional[Dict]:
        """Get model information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.*, p.api_key, p.api_url
            FROM models m
            LEFT JOIN providers p ON m.provider_id = p.id
            WHERE m.id = ?
        ''', (model_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_models(self) -> List[Dict]:
        """Get all trading models"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.*, p.name as provider_name
            FROM models m
            LEFT JOIN providers p ON m.provider_id = p.id
            ORDER BY m.created_at DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

