# app.py
from flask import Flask, render_template, request, redirect, url_for, g, flash
import sqlite3
import os
import yfinance as yf 
import math
from datetime import date, timedelta 

app = Flask(__name__)

DATABASE_FILE = os.path.join(os.path.dirname(__file__), 'database', 'investment_tracker.db')
app.config['DATABASE'] = DATABASE_FILE
app.secret_key = 'your_very_secret_key_for_auto_exchange_rate' # IMPORTANT: Change this!

# --- Custom Jinja2 Filters ---
def format_currency(value, currency_symbol="$"):
    if value is None:
        return "N/A" 
    try:
        num_value = float(value)
        return f"{currency_symbol}{num_value:,.2f}"
    except (ValueError, TypeError):
        return value 

app.jinja_env.filters['currency'] = format_currency

def format_number_with_commas(value, decimal_places=None):
    if value is None:
        return "N/A"
    try:
        num_value = float(value)
        if decimal_places is not None:
            return "{:,.{}f}".format(num_value, decimal_places)
        if num_value == int(num_value): 
            return "{:,.0f}".format(int(num_value)) 
        return "{:,}".format(num_value) 
    except (ValueError, TypeError):
        return value 

app.jinja_env.filters['number_with_commas'] = format_number_with_commas

# --- Yahoo Finance Helper Functions ---
def fetch_market_data(ticker_symbol): # For stocks/assets
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        hist = ticker.history(period="5d") 

        current_price_hist = hist['Close'].iloc[-1] if not hist.empty else None
        price_yesterday_hist = hist['Close'].iloc[-2] if len(hist) >= 2 else None

        current_price = current_price_hist if current_price_hist is not None else info.get('currentPrice', info.get('regularMarketPreviousClose', info.get('bid', info.get('ask')))) # Added more fallbacks
        price_yesterday = price_yesterday_hist if price_yesterday_hist is not None else info.get('previousClose', info.get('regularMarketPreviousClose'))
        
        data = {
            'current_price': current_price,
            'price_yesterday': price_yesterday,
            'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
            'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
            'name': info.get('shortName') or info.get('longName')
        }
        
        for key in ['current_price', 'price_yesterday', 'fifty_two_week_high', 'fifty_two_week_low']:
            if data[key] is not None and not isinstance(data[key], (int, float)):
                print(f"Warning: yfinance data for {key} for {ticker_symbol} is not a number: {data[key]}. Setting to None.")
                data[key] = None
        
        return data
    except Exception as e:
        print(f"Error fetching market_data for {ticker_symbol} from yfinance: {e}")
        return None

def fetch_live_exchange_rate(currency_pair="CAD=X"):
    """Fetches the current exchange rate for a given currency pair from Yahoo Finance."""
    try:
        ticker = yf.Ticker(currency_pair)
        # For currencies, 'regularMarketPrice' or sometimes 'bid' might be available.
        # Or use a short history period.
        data = ticker.history(period="1d")
        if not data.empty:
            rate = data['Close'].iloc[-1]
            print(f"Fetched exchange rate for {currency_pair}: {rate}")
            return float(rate) if rate is not None else None
        else: # Fallback if history is empty
            info = ticker.info
            rate = info.get('regularMarketPrice') or info.get('bid')
            if rate:
                print(f"Fetched exchange rate for {currency_pair} from info: {rate}")
                return float(rate)
            print(f"Could not fetch exchange rate for {currency_pair} from history or info.")
            return None
    except Exception as e:
        print(f"Error fetching exchange rate for {currency_pair}: {e}")
        return None

def fetch_yearly_historical_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        end_date = date.today()
        start_date = end_date - timedelta(days=365)
        hist = ticker.history(start=start_date.isoformat(), end=end_date.isoformat(), interval="1d")
        
        if hist.empty:
            print(f"No yearly historical data found for {ticker_symbol}.")
            return []
        
        chart_data = []
        for index, row in hist.iterrows():
            chart_data.append([index.strftime('%Y-%m-%d'), row['Close']])
        return chart_data
    except Exception as e:
        print(f"Error fetching yearly historical data for {ticker_symbol}: {e}")
        return []

# --- Database Helper Functions ---
# ... (get_db, close_db, query_db functions remain the same) ...
def get_db():
    if 'db' not in g:
        os.makedirs(os.path.dirname(app.config['DATABASE']), exist_ok=True)
        g.db = sqlite3.connect(
            app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(query, args)
        query_type = query.lower().strip().split()[0] 

        if query_type == "select":
            rv = cur.fetchall()
            cur.close()
            return (rv[0] if rv else None) if one else rv
        else: 
            db.commit()
            if query_type == "insert":
                return_value = cur.lastrowid
            elif query_type in ["update", "delete"]:
                return_value = cur.rowcount 
            else:
                return_value = True 
            cur.close()
            return return_value
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        print(f"Query: {query}")
        print(f"Args: {args}")
        if cur: 
            cur.close()
        return None 
    
# --- Routes ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'set_goal': # For setting financial goal
            target_goal_str = request.form.get('target_goal_value')
            if target_goal_str:
                try:
                    target_goal = float(target_goal_str)
                    if target_goal < 0:
                        flash("Target goal value cannot be negative.", "warning")
                    else:
                        query_db("INSERT OR REPLACE INTO app_settings (setting_key, setting_value) VALUES (?, ?)",
                                 ['target_goal_value', str(target_goal)])
                        flash(f"Target goal updated to {format_currency(target_goal)} successfully!", "success")
                except ValueError:
                    flash("Invalid target goal value. Please enter a number.", "error")
            else:
                flash("Target goal value cannot be empty.", "warning")
            return redirect(url_for('index'))
        # Removed manual setting of exchange rate here, will be handled by refresh_all_assets_data

    # --- Global & Detailed Asset Calculations ---
    # ... (This entire section remains the same as in investment_tracker_app_py_latest_dashboard) ...
    global_total_invested_assets = 0.0 
    global_current_value_of_assets = 0.0
    global_total_cash = 0.0
    all_assets_detailed = [] 

    assets_query_for_dashboard = """
        SELECT 
            ast.asset_id, ast.ticker_symbol, ast.name as asset_name, ast.quantity, 
            ast.average_cost, ast.total_invested, ast.current_price, ast.price_yesterday, 
            ast.fifty_two_week_high, ast.fifty_two_week_low,
            acc.account_id, acc.account_name, acc.user_id, acc.platform_id,
            u.name as user_name, p.name as platform_name, acc.account_type 
        FROM assets ast
        JOIN accounts acc ON ast.account_id = acc.account_id
        JOIN users u ON acc.user_id = u.user_id
        JOIN platforms p ON acc.platform_id = p.platform_id
    """
    all_assets_raw = query_db(assets_query_for_dashboard)

    if all_assets_raw:
        for asset_row in all_assets_raw:
            asset_detail = dict(asset_row) 
            
            asset_detail['total_invested'] = asset_detail.get('total_invested', 0.0) or 0.0
            asset_detail['quantity'] = asset_detail.get('quantity', 0.0) or 0.0
            
            asset_detail['current_value'] = 0.0
            if asset_detail.get('current_price') is not None:
                asset_detail['current_value'] = asset_detail['quantity'] * asset_detail['current_price']
            
            asset_detail['profit_loss_dollars'] = asset_detail['current_value'] - asset_detail['total_invested']
            
            if asset_detail['total_invested'] > 0:
                asset_detail['profit_loss_percent'] = (asset_detail['profit_loss_dollars'] / asset_detail['total_invested']) * 100
            else:
                asset_detail['profit_loss_percent'] = 0.0 

            asset_detail['day_change_percent'] = 0.0
            if asset_detail.get('current_price') is not None and asset_detail.get('price_yesterday') is not None and asset_detail['price_yesterday'] > 0:
                asset_detail['day_change_percent'] = ((asset_detail['current_price'] - asset_detail['price_yesterday']) / asset_detail['price_yesterday']) * 100
            
            asset_detail['percent_to_52_week_high'] = None
            if asset_detail.get('current_price') is not None and asset_detail.get('fifty_two_week_high') is not None and asset_detail['fifty_two_week_high'] > 0:
                asset_detail['percent_to_52_week_high'] = ((asset_detail['current_price'] - asset_detail['fifty_two_week_high']) / asset_detail['fifty_two_week_high']) * 100
            
            all_assets_detailed.append(asset_detail)

            global_total_invested_assets += asset_detail['total_invested']
            global_current_value_of_assets += asset_detail['current_value']

    best_performing_asset = None
    worst_performing_asset = None
    if all_assets_detailed:
        valid_assets_for_ranking = [a for a in all_assets_detailed if a.get('profit_loss_percent') is not None and a.get('total_invested') > 0]
        if valid_assets_for_ranking:
            sorted_assets = sorted(valid_assets_for_ranking, key=lambda x: x['profit_loss_percent'], reverse=True)
            if sorted_assets: 
                best_performing_asset = sorted_assets[0]
                best_performing_asset['yearly_chart_data'] = fetch_yearly_historical_data(best_performing_asset['ticker_symbol'])
                
                worst_performing_asset = sorted_assets[-1]
                worst_performing_asset['yearly_chart_data'] = fetch_yearly_historical_data(worst_performing_asset['ticker_symbol'])
            all_assets_ranked = sorted_assets 
        else:
            all_assets_ranked = []
    else:
        all_assets_ranked = []

    global_cash_data = query_db("SELECT SUM(cash_balance) as total_cash FROM accounts", one=True)
    if global_cash_data and global_cash_data['total_cash'] is not None:
        global_total_cash = global_cash_data['total_cash']

    total_invested_assets_plus_cash = global_total_invested_assets + global_total_cash # New Metric

    global_profit_loss_amount = global_current_value_of_assets - global_total_invested_assets
    global_profit_loss_percent = (global_profit_loss_amount / global_total_invested_assets) * 100 if global_total_invested_assets > 0 else 0.0
    overall_portfolio_value = global_current_value_of_assets + global_total_cash

    today_str = date.today().isoformat()
    last_snapshot = query_db("SELECT snapshot_date FROM portfolio_history WHERE snapshot_date = ?", [today_str], one=True)
    if not last_snapshot:
        if overall_portfolio_value is not None: 
            query_db("INSERT INTO portfolio_history (snapshot_date, total_portfolio_value) VALUES (?, ?)",
                     [today_str, overall_portfolio_value])
            print(f"Recorded portfolio value for {today_str}: {overall_portfolio_value}")
    
    portfolio_history_db_rows = query_db(
        "SELECT snapshot_date, total_portfolio_value FROM portfolio_history ORDER BY snapshot_date ASC"
    )
    portfolio_history_for_chart_list_of_dicts = []
    if portfolio_history_db_rows:
        for row in portfolio_history_db_rows:
            portfolio_history_for_chart_list_of_dicts.append(dict(row))

    target_goal_row = query_db("SELECT setting_value FROM app_settings WHERE setting_key = 'target_goal_value'", one=True)
    target_goal_value = 100000.0 
    if target_goal_row and target_goal_row['setting_value']:
        try:
            target_goal_value = float(target_goal_row['setting_value'])
        except ValueError:
            print(f"Warning: Could not parse target_goal_value '{target_goal_row['setting_value']}' as float. Using default.")

    exchange_rate_row = query_db("SELECT setting_value FROM app_settings WHERE setting_key = 'usd_to_cad_exchange_rate'", one=True)
    usd_to_cad_exchange_rate = 1.35 # Default if not set
    if exchange_rate_row and exchange_rate_row['setting_value']:
        try:
            usd_to_cad_exchange_rate = float(exchange_rate_row['setting_value'])
        except ValueError:
            print(f"Warning: Could not parse usd_to_cad_exchange_rate. Using default.")

    
    dashboard_global_data = {
        'total_invested_assets': global_total_invested_assets, 
        'total_invested_assets_plus_cash': total_invested_assets_plus_cash, # New
        'current_value_of_assets': global_current_value_of_assets,
        'profit_loss_amount': global_profit_loss_amount,
        'profit_loss_percent': global_profit_loss_percent,
        'total_cash': global_total_cash,
        'overall_portfolio_value': overall_portfolio_value,
        'target_goal_value': target_goal_value,
        'best_performing_asset': best_performing_asset, 
        'worst_performing_asset': worst_performing_asset, 
        'all_assets_ranked': all_assets_ranked, 
        'portfolio_history_for_chart': portfolio_history_for_chart_list_of_dicts,
        'usd_to_cad_exchange_rate': usd_to_cad_exchange_rate # New
    }
    
    users = query_db("SELECT user_id, name FROM users ORDER BY name")
    breakdown_data = [] 
    all_accounts_performance_data = [] 

    for user_row in users:
        user_summary_data = {
            'user_name': user_row['name'],
            'user_id': user_row['user_id'], 
            'total_invested': 0.0,
            'current_value_of_assets': 0.0,
            'total_cash': 0.0,
            'platforms': []
        }
        user_platforms = query_db("""
            SELECT DISTINCT p.platform_id, p.name AS platform_name
            FROM platforms p
            JOIN accounts acc ON p.platform_id = acc.platform_id
            WHERE acc.user_id = ? ORDER BY p.name
        """, [user_row['user_id']])

        for platform_row in user_platforms:
            platform_summary_data = {
                'platform_name': platform_row['platform_name'],
                'total_invested': 0.0,
                'current_value_of_assets': 0.0,
                'total_cash': 0.0,
                'accounts': [] 
            }
            
            accounts_on_platform = query_db("""
                SELECT account_id, account_name, account_type, cash_balance
                FROM accounts
                WHERE user_id = ? AND platform_id = ?
                ORDER BY account_name
            """, [user_row['user_id'], platform_row['platform_id']])

            for account_row in accounts_on_platform:
                account_summary_data = {
                    'account_id': account_row['account_id'],
                    'account_name': account_row['account_name'],
                    'account_type': account_row['account_type'], 
                    'cash_balance': account_row['cash_balance'] or 0.0,
                    'total_invested': 0.0,
                    'current_value_of_assets': 0.0,
                    'assets': []
                }

                assets_in_account = [a for a in all_assets_detailed if a['account_id'] == account_row['account_id']]
                
                for asset_detail_item in assets_in_account: 
                    account_summary_data['assets'].append(asset_detail_item) 
                    account_summary_data['total_invested'] += asset_detail_item['total_invested']
                    account_summary_data['current_value_of_assets'] += asset_detail_item['current_value']
                
                account_summary_data['profit_loss_amount'] = account_summary_data['current_value_of_assets'] - account_summary_data['total_invested']
                account_summary_data['profit_loss_percent'] = (account_summary_data['profit_loss_amount'] / account_summary_data['total_invested']) * 100 if account_summary_data['total_invested'] > 0 else 0.0
                
                all_accounts_performance_data.append({
                    'user_name': user_row['name'],
                    'platform_name': platform_row['platform_name'],
                    'account_name': account_row['account_name'],
                    'display_name': f"{user_row['name']} - {account_row['account_name']} ({platform_row['platform_name']})",
                    'total_invested': account_summary_data['total_invested'],
                    'current_value_of_assets': account_summary_data['current_value_of_assets'], 
                    'total_value': account_summary_data['current_value_of_assets'] + account_summary_data['cash_balance'], 
                    'profit_loss_dollars': account_summary_data['profit_loss_amount'],
                    'profit_loss_percent': account_summary_data['profit_loss_percent']
                })

                platform_summary_data['accounts'].append(account_summary_data)
                
                platform_summary_data['total_invested'] += account_summary_data['total_invested']
                platform_summary_data['current_value_of_assets'] += account_summary_data['current_value_of_assets']
                platform_summary_data['total_cash'] += account_summary_data['cash_balance']
            
            platform_summary_data['profit_loss_amount'] = platform_summary_data['current_value_of_assets'] - platform_summary_data['total_invested']
            platform_summary_data['profit_loss_percent'] = (platform_summary_data['profit_loss_amount'] / platform_summary_data['total_invested']) * 100 if platform_summary_data['total_invested'] > 0 else 0.0

            user_summary_data['platforms'].append(platform_summary_data)
            
            user_summary_data['total_invested'] += platform_summary_data['total_invested']
            user_summary_data['current_value_of_assets'] += platform_summary_data['current_value_of_assets']
            user_summary_data['total_cash'] += platform_summary_data['total_cash']

        user_summary_data['profit_loss_amount'] = user_summary_data['current_value_of_assets'] - user_summary_data['total_invested']
        user_summary_data['profit_loss_percent'] = (user_summary_data['profit_loss_amount'] / user_summary_data['total_invested']) * 100 if user_summary_data['total_invested'] > 0 else 0.0
        
        breakdown_data.append(user_summary_data)

    account_type_values = {}
    if breakdown_data: 
        for user_summary in breakdown_data:
            for platform_summary in user_summary['platforms']:
                for account_summary in platform_summary['accounts']:
                    acc_type = account_summary['account_type']
                    account_total_value = (account_summary.get('current_value_of_assets', 0.0) or 0.0) + \
                                          (account_summary.get('cash_balance', 0.0) or 0.0)
                    
                    if acc_type not in account_type_values:
                        account_type_values[acc_type] = 0.0
                    account_type_values[acc_type] += account_total_value
    
    account_type_allocation_data_for_chart = [['Account Type', 'Total Value']]
    for acc_type, total_value in account_type_values.items():
        if total_value > 0: 
            account_type_allocation_data_for_chart.append([acc_type, total_value])
            
    dashboard_global_data['account_type_allocation_data_for_chart'] = account_type_allocation_data_for_chart if len(account_type_allocation_data_for_chart) > 1 else []
    
    user_allocation_data_for_chart = [['User', 'Total Portfolio Value']]
    if breakdown_data: 
        for user_summary in breakdown_data:
            user_portfolio_value = (user_summary.get('current_value_of_assets', 0.0) or 0.0) + \
                                   (user_summary.get('total_cash', 0.0) or 0.0)
            if user_portfolio_value > 0: 
                 user_allocation_data_for_chart.append([user_summary['user_name'], user_portfolio_value])
    dashboard_global_data['user_allocation_data_for_chart'] = user_allocation_data_for_chart if len(user_allocation_data_for_chart) > 1 else []

    individual_account_allocation_data = [['Account', 'Total Value']]
    if all_accounts_performance_data: 
        for acc_perf_data in all_accounts_performance_data:
            if acc_perf_data.get('total_value', 0.0) > 0:
                individual_account_allocation_data.append([acc_perf_data['display_name'], acc_perf_data['total_value']])
    dashboard_global_data['individual_account_allocation_data_for_chart'] = individual_account_allocation_data if len(individual_account_allocation_data) > 1 else []

    if all_accounts_performance_data:
        ranked_accounts = sorted(
            [acc for acc in all_accounts_performance_data if acc.get('total_invested', 0) > 0 and acc.get('profit_loss_percent') is not None], 
            key=lambda x: x['profit_loss_percent'], 
            reverse=True
        )
        dashboard_global_data['all_accounts_ranked_by_performance'] = ranked_accounts
    else:
        dashboard_global_data['all_accounts_ranked_by_performance'] = []

    return render_template('dashboard.html', 
                           title="Portfolio Dashboard", 
                           global_data=dashboard_global_data, 
                           breakdown_data=breakdown_data)

# --- Other Routes ---
# (Make sure to include all other routes: User, Platform, Account, Asset management (CRUD), and individual asset refresh)
@app.route('/users', methods=['GET', 'POST'])
def manage_users():
    if request.method == 'POST': 
        name = request.form.get('name', '').strip()
        if name:
            try:
                existing_user = query_db("SELECT user_id FROM users WHERE name = ?", [name], one=True)
                if existing_user:
                    flash(f"User '{name}' already exists.", "warning")
                else:
                    result = query_db("INSERT INTO users (name) VALUES (?)", [name])
                    if result is not None: 
                        flash(f"User '{name}' (ID: {result}) added successfully!", "success")
                    else:
                        flash(f"Failed to add user '{name}'. Database error occurred.", "error")
            except Exception as e:
                flash(f"An error occurred while adding user: {e}", "error")
                print(f"Error adding user {name}: {e}")
        else:
            flash("User name cannot be empty.", "warning")
        return redirect(url_for('manage_users'))

    users = query_db("SELECT * FROM users ORDER BY name")
    return render_template('users.html', users=users or [], title="Manage Users")

@app.route('/user/<int:user_id>/edit', methods=['GET', 'POST'])
def edit_user(user_id):
    user = query_db("SELECT * FROM users WHERE user_id = ?", [user_id], one=True)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for('manage_users'))

    if request.method == 'POST':
        new_name = request.form.get('name', '').strip()
        if not new_name:
            flash("User name cannot be empty.", "warning")
            return render_template('edit_user.html', user=user, title="Edit User")
        
        existing_user_with_new_name = query_db("SELECT user_id FROM users WHERE name = ? AND user_id != ?", [new_name, user_id], one=True)
        if existing_user_with_new_name:
            flash(f"Another user with the name '{new_name}' already exists.", "warning")
            return render_template('edit_user.html', user=user, title="Edit User")

        if new_name == user['name']:
            flash("No changes made to the user name.", "info")
            return redirect(url_for('manage_users'))

        try:
            rows_affected = query_db("UPDATE users SET name = ? WHERE user_id = ?", [new_name, user_id])
            if rows_affected is not None: 
                if rows_affected > 0: 
                    flash(f"User '{user['name']}' updated to '{new_name}' successfully!", "success")
                else: 
                    flash(f"User '{user['name']}' was not updated. No changes or user not found for update.", "info")
            else: 
                 flash(f"Failed to update user '{user['name']}'. Database error occurred.", "error")
        except Exception as e: 
            flash(f"An error occurred while updating user: {e}", "error")
            print(f"Error updating user {user_id}: {e}")
        return redirect(url_for('manage_users'))

    return render_template('edit_user.html', user=user, title=f"Edit User: {user['name']}")

@app.route('/platforms', methods=['GET', 'POST'])
def manage_platforms():
    if request.method == 'POST': 
        name = request.form.get('name', '').strip()
        if name:
            try:
                existing_platform = query_db("SELECT platform_id FROM platforms WHERE name = ?", [name], one=True)
                if existing_platform:
                    flash(f"Platform '{name}' already exists.", "warning")
                else:
                    result = query_db("INSERT INTO platforms (name) VALUES (?)", [name])
                    if result is not None:
                        flash(f"Platform '{name}' (ID: {result}) added successfully!", "success")
                    else:
                        flash(f"Failed to add platform '{name}'. Database error occurred.", "error")
            except Exception as e:
                flash(f"An error occurred while adding platform: {e}", "error")
                print(f"Error adding platform {name}: {e}")
        else:
            flash("Platform name cannot be empty.", "warning")
        return redirect(url_for('manage_platforms'))

    platforms = query_db("SELECT * FROM platforms ORDER BY name")
    return render_template('platforms.html', platforms=platforms or [], title="Manage Platforms")

@app.route('/platform/<int:platform_id>/edit', methods=['GET', 'POST'])
def edit_platform(platform_id):
    platform = query_db("SELECT * FROM platforms WHERE platform_id = ?", [platform_id], one=True)
    if not platform:
        flash("Platform not found.", "error")
        return redirect(url_for('manage_platforms'))

    if request.method == 'POST':
        new_name = request.form.get('name', '').strip()
        if not new_name:
            flash("Platform name cannot be empty.", "warning")
            return render_template('edit_platform.html', platform=platform, title="Edit Platform")

        existing_platform_with_new_name = query_db("SELECT platform_id FROM platforms WHERE name = ? AND platform_id != ?", [new_name, platform_id], one=True)
        if existing_platform_with_new_name:
            flash(f"Another platform with the name '{new_name}' already exists.", "warning")
            return render_template('edit_platform.html', platform=platform, title="Edit Platform")

        if new_name == platform['name']:
            flash("No changes made to the platform name.", "info")
            return redirect(url_for('manage_platforms'))

        try:
            rows_affected = query_db("UPDATE platforms SET name = ? WHERE platform_id = ?", [new_name, platform_id])
            if rows_affected is not None:
                if rows_affected > 0:
                    flash(f"Platform '{platform['name']}' updated to '{new_name}' successfully!", "success")
                else:
                    flash(f"Platform '{platform['name']}' was not updated. No changes or platform not found for update.", "info")
            else:
                flash(f"Failed to update platform '{platform['name']}'. Database error occurred.", "error")
        except Exception as e:
            flash(f"An error occurred while updating platform: {e}", "error")
            print(f"Error updating platform {platform_id}: {e}")
        return redirect(url_for('manage_platforms'))

    return render_template('edit_platform.html', platform=platform, title=f"Edit Platform: {platform['name']}")

@app.route('/platform/<int:platform_id>/delete', methods=['POST'])
def delete_platform(platform_id):
    platform_to_delete = query_db("SELECT name FROM platforms WHERE platform_id = ?", [platform_id], one=True)

    if not platform_to_delete:
        flash("Platform not found or already deleted.", "error")
        return redirect(url_for('manage_platforms'))
    
    platform_name = platform_to_delete['name']

    try:
        rows_affected = query_db("DELETE FROM platforms WHERE platform_id = ?", [platform_id])
        if rows_affected is not None and rows_affected > 0:
            flash(f"Platform '{platform_name}' and all its associated accounts and assets deleted successfully!", "success")
        elif rows_affected == 0:
            flash(f"Platform '{platform_name}' not found or already deleted.", "warning")
        else: 
            flash(f"Failed to delete platform '{platform_name}'. Database error occurred.", "error")
    except Exception as e:
        flash(f"An error occurred while deleting platform: {e}", "error")
        print(f"Error deleting platform {platform_id}: {e}")
        
    return redirect(url_for('manage_platforms'))

# --- Account Management Routes ---
@app.route('/accounts', methods=['GET', 'POST'])
def manage_accounts():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        platform_id = request.form.get('platform_id')
        account_type = request.form.get('account_type', '').strip()
        account_name = request.form.get('account_name', '').strip()
        cash_balance_str = request.form.get('cash_balance', '0.0').strip()

        if not user_id or not platform_id or not account_type or not account_name :
            flash("User, Platform, Account Type, and Account Name are all required fields.", "error")
        else:
            try:
                cash_balance = float(cash_balance_str) if cash_balance_str else 0.0
                existing_account = query_db("SELECT account_id FROM accounts WHERE account_name = ?", [account_name], one=True)
                if existing_account:
                    flash(f"Account with name '{account_name}' already exists.", "warning")
                else:
                    result = query_db("INSERT INTO accounts (user_id, platform_id, account_type, account_name, cash_balance) VALUES (?, ?, ?, ?, ?)",
                                     [user_id, platform_id, account_type, account_name, cash_balance])
                    if result is not None:
                        flash(f"Account '{account_name}' (ID: {result}) added successfully!", "success")
                    else:
                        flash(f"Failed to add account '{account_name}'. Database error occurred.", "error")
            except ValueError:
                flash(f"Invalid cash balance '{cash_balance_str}'. Please enter a valid number.", "error")
            except Exception as e:
                flash(f"An unexpected error occurred while adding account: {e}", "error")
                print(f"Error adding account {account_name}: {e}")
        return redirect(url_for('manage_accounts'))

    users = query_db("SELECT user_id, name FROM users ORDER BY name")
    platforms = query_db("SELECT platform_id, name FROM platforms ORDER BY name")
    accounts_query = """
        SELECT 
            a.account_id, a.account_name, a.account_type, a.cash_balance,
            u.name as user_name,
            p.name as platform_name
        FROM accounts a
        JOIN users u ON a.user_id = u.user_id
        JOIN platforms p ON a.platform_id = p.platform_id
        ORDER BY u.name, p.name, a.account_name;
    """
    accounts = query_db(accounts_query)
    return render_template('accounts.html', 
                           users=users or [], 
                           platforms=platforms or [],
                           accounts=accounts or [],
                           title="Manage Accounts")

@app.route('/account/<int:account_id>/edit', methods=['GET', 'POST'])
def edit_account(account_id):
    account = query_db("SELECT * FROM accounts WHERE account_id = ?", [account_id], one=True)
    if not account:
        flash("Account not found.", "error")
        return redirect(url_for('manage_accounts'))

    if request.method == 'POST':
        new_user_id = request.form.get('user_id')
        new_platform_id = request.form.get('platform_id')
        new_account_type = request.form.get('account_type', '').strip()
        new_account_name = request.form.get('account_name', '').strip()
        new_cash_balance_str = request.form.get('cash_balance', '0.0').strip()

        if not all([new_user_id, new_platform_id, new_account_type, new_account_name]):
            flash("User, Platform, Account Type, and Account Name are required.", "error")
            users_for_form = query_db("SELECT user_id, name FROM users ORDER BY name")
            platforms_for_form = query_db("SELECT platform_id, name FROM platforms ORDER BY name")
            return render_template('edit_account.html', account=account, 
                                   users=users_for_form or [], platforms=platforms_for_form or [], 
                                   title=f"Edit Account: {account['account_name']}")
        
        try:
            new_cash_balance = float(new_cash_balance_str) if new_cash_balance_str else 0.0
        except ValueError:
            flash(f"Invalid cash balance '{new_cash_balance_str}'. Please enter a valid number.", "error")
            users_for_form = query_db("SELECT user_id, name FROM users ORDER BY name")
            platforms_for_form = query_db("SELECT platform_id, name FROM platforms ORDER BY name")
            return render_template('edit_account.html', account=account, 
                                   users=users_for_form or [], platforms=platforms_for_form or [], 
                                   title=f"Edit Account: {account['account_name']}")

        existing_account_with_new_name = query_db("SELECT account_id FROM accounts WHERE account_name = ? AND account_id != ?", 
                                                  [new_account_name, account_id], one=True)
        if existing_account_with_new_name:
            flash(f"Another account with the name '{new_account_name}' already exists.", "warning")
            users_for_form = query_db("SELECT user_id, name FROM users ORDER BY name")
            platforms_for_form = query_db("SELECT platform_id, name FROM platforms ORDER BY name")
            return render_template('edit_account.html', account=account, 
                                   users=users_for_form or [], platforms=platforms_for_form or [], 
                                   title=f"Edit Account: {account['account_name']}")
        
        if (int(new_user_id) == account['user_id'] and
            int(new_platform_id) == account['platform_id'] and
            new_account_type == account['account_type'] and
            new_account_name == account['account_name'] and
            new_cash_balance == account['cash_balance']):
            flash("No changes detected for the account.", "info")
            return redirect(url_for('manage_accounts'))

        try:
            update_query = """UPDATE accounts SET 
                                user_id = ?, platform_id = ?, account_type = ?, 
                                account_name = ?, cash_balance = ? 
                              WHERE account_id = ?"""
            rows_affected = query_db(update_query, 
                                     [new_user_id, new_platform_id, new_account_type, 
                                      new_account_name, new_cash_balance, account_id])
            
            if rows_affected is not None:
                if rows_affected > 0:
                    flash(f"Account '{account['account_name']}' updated successfully!", "success")
                else:
                    flash(f"Account '{account['account_name']}' was not updated. (No rows affected)", "info")
            else:
                flash(f"Failed to update account '{account['account_name']}'. Database error occurred.", "error")
        except Exception as e:
            flash(f"An error occurred while updating account: {e}", "error")
            print(f"Error updating account {account_id}: {e}")
        
        return redirect(url_for('manage_accounts'))

    users_for_form = query_db("SELECT user_id, name FROM users ORDER BY name")
    platforms_for_form = query_db("SELECT platform_id, name FROM platforms ORDER BY name")
    return render_template('edit_account.html', account=account, 
                           users=users_for_form or [], platforms=platforms_for_form or [], 
                           title=f"Edit Account: {account['account_name']}")

@app.route('/account/<int:account_id>/delete', methods=['POST'])
def delete_account(account_id):
    account_to_delete = query_db("SELECT account_name FROM accounts WHERE account_id = ?", [account_id], one=True)

    if not account_to_delete:
        flash("Account not found or already deleted.", "error")
        return redirect(url_for('manage_accounts'))
    
    account_name = account_to_delete['account_name']

    try:
        rows_affected = query_db("DELETE FROM accounts WHERE account_id = ?", [account_id])
        if rows_affected is not None and rows_affected > 0:
            flash(f"Account '{account_name}' and all its associated assets deleted successfully!", "success")
        elif rows_affected == 0:
            flash(f"Account '{account_name}' not found or already deleted.", "warning")
        else: 
            flash(f"Failed to delete account '{account_name}'. Database error occurred.", "error")
    except Exception as e:
        flash(f"An error occurred while deleting account: {e}", "error")
        print(f"Error deleting account {account_id}: {e}")
        
    return redirect(url_for('manage_accounts'))

# --- Asset Management Routes (for a specific account) ---
@app.route('/account/<int:account_id>/assets', methods=['GET', 'POST'])
def manage_account_assets(account_id):
    account_details_query = """
        SELECT a.account_id, a.account_name, u.name as user_name, p.name as platform_name
        FROM accounts a
        JOIN users u ON a.user_id = u.user_id
        JOIN platforms p ON a.platform_id = p.platform_id
        WHERE a.account_id = ?;
    """
    account = query_db(account_details_query, [account_id], one=True)
    sell_simulation_results = None 
    buy_simulation_inputs = {} 
    buy_simulation_results = None  
    # Removed show_sell_form_for_asset_id and show_buy_form_for_asset_id initializations
    # Their visibility will be controlled by presence of results in template

    if not account:
        flash(f"Account with ID {account_id} not found.", "error")
        return redirect(url_for('manage_accounts'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_asset':
            # ... (add_asset logic as before) ...
            ticker_symbol = request.form.get('ticker_symbol', '').strip().upper()
            asset_name_manual = request.form.get('asset_name', '').strip() 
            quantity_str = request.form.get('quantity', '').strip()
            average_cost_str = request.form.get('average_cost', '').strip()
            total_invested_str = request.form.get('total_invested', '').strip()
            
            if not all([ticker_symbol, quantity_str, average_cost_str, total_invested_str]):
                flash("Ticker, Quantity, Average Cost, and Total Invested are required.", "error")
            else:
                try:
                    quantity = float(quantity_str)
                    average_cost = float(average_cost_str) 
                    total_invested = float(total_invested_str)

                    if quantity <= 0 or average_cost < 0 or total_invested < 0:
                        flash("Quantity must be positive. Costs must be non-negative.", "warning")
                    else:
                        existing_asset = query_db("SELECT asset_id FROM assets WHERE account_id = ? AND ticker_symbol = ?", 
                                                  [account_id, ticker_symbol], one=True)
                        if existing_asset:
                            flash(f"Asset '{ticker_symbol}' already exists in this account. Use 'Edit' to modify.", "warning")
                        else:
                            market_data = fetch_market_data(ticker_symbol)
                            fetched_name = asset_name_manual 
                            current_price, price_yesterday, fifty_two_week_high, fifty_two_week_low = None, None, None, None

                            if market_data:
                                if not fetched_name and market_data.get('name'): 
                                    fetched_name = market_data.get('name')
                                current_price = market_data.get('current_price')
                                price_yesterday = market_data.get('price_yesterday')
                                fifty_two_week_high = market_data.get('fifty_two_week_high')
                                fifty_two_week_low = market_data.get('fifty_two_week_low')
                            else:
                                flash(f"Could not fetch market data for {ticker_symbol}. Prices will be blank. Please refresh later.", "warning")
                            
                            insert_query = """INSERT INTO assets 
                                              (account_id, ticker_symbol, name, quantity, average_cost, total_invested, 
                                               current_price, price_yesterday, fifty_two_week_high, fifty_two_week_low) 
                                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                            result = query_db(insert_query,
                                     [account_id, ticker_symbol, fetched_name, 
                                      quantity, average_cost, total_invested, 
                                      current_price, price_yesterday, fifty_two_week_high, fifty_two_week_low])
                            
                            if result is not None:
                                flash(f"Asset '{ticker_symbol}' added. Market data fetched if available.", "success")
                            else:
                                flash(f"Failed to add asset '{ticker_symbol}'. Database error occurred", "error")
                except ValueError:
                    flash("Invalid number for Quantity, Average Cost, or Total Invested.", "error")
                except Exception as e:
                    flash(f"An error occurred while adding asset: {e}", "error")
                    print(f"Error adding asset {ticker_symbol} to account {account_id}: {e}")
            return redirect(url_for('manage_account_assets', account_id=account_id))
        
        elif action == 'simulate_sell':
            asset_id_to_simulate_str = request.form.get('simulate_sell_asset_id')
            hypothetical_sale_price_str = request.form.get('hypothetical_sale_price')

            if not asset_id_to_simulate_str or not hypothetical_sale_price_str:
                flash("Asset ID and hypothetical sale price are required for simulation.", "error")
            else:
                try:
                    asset_id_to_simulate = int(asset_id_to_simulate_str)
                    # show_sell_form_for_asset_id = asset_id_to_simulate # No longer needed, visibility based on results
                    hypothetical_sale_price = float(hypothetical_sale_price_str)

                    asset_to_simulate = query_db("SELECT quantity, total_invested, average_cost FROM assets WHERE asset_id = ?", 
                                                 [asset_id_to_simulate], one=True)
                    
                    if not asset_to_simulate:
                        flash("Asset for simulation not found.", "error")
                    elif hypothetical_sale_price < 0:
                        flash("Hypothetical sale price cannot be negative.", "warning")
                    else:
                        quantity = asset_to_simulate['quantity'] or 0
                        original_cost = asset_to_simulate['total_invested']
                        if original_cost is None and asset_to_simulate['average_cost'] is not None and quantity is not None:
                             original_cost = quantity * asset_to_simulate['average_cost']
                        elif original_cost is None:
                            original_cost = 0 

                        total_proceeds = quantity * hypothetical_sale_price 
                        profit_dollars = total_proceeds - original_cost
                        profit_percent = (profit_dollars / original_cost) * 100 if original_cost > 0 else 0.0
                        
                        sell_simulation_results = { # This will make the form visible in the template
                            'asset_id': asset_id_to_simulate,
                            'hypothetical_sale_price': hypothetical_sale_price,
                            'total_proceeds': total_proceeds,
                            'original_cost': original_cost,
                            'profit_dollars': profit_dollars,
                            'profit_percent': profit_percent
                        }
                        flash(f"Sell simulation calculated.", "info")

                except ValueError:
                    flash("Invalid number for asset ID or hypothetical sale price.", "error")
                except Exception as e:
                    flash(f"An error occurred during sell simulation: {e}", "error")
                    print(f"Error during sell simulation: {e}")
        
        elif action == 'simulate_buy_existing_asset': 
            asset_id_to_buy_str = request.form.get('simulate_buy_asset_id')
            investment_amount_str = request.form.get('buy_investment_amount', '').strip()
            shares_to_buy_str = request.form.get('buy_shares_to_buy', '').strip()
            
            buy_simulation_inputs = { # Always store inputs to re-populate form
                'asset_id': int(asset_id_to_buy_str) if asset_id_to_buy_str else None, 
                'investment_amount': investment_amount_str,
                'shares_to_buy': shares_to_buy_str
            }

            if not asset_id_to_buy_str:
                flash("Asset ID is missing for buy simulation.", "error")
            elif not investment_amount_str and not shares_to_buy_str:
                flash("Either Investment Amount or Number of Shares to Buy is required.", "error")
            else:
                try:
                    asset_id_to_buy = int(asset_id_to_buy_str)
                    # show_buy_form_for_asset_id = asset_id_to_buy # No longer needed

                    existing_asset = query_db("SELECT asset_id, quantity, total_invested, average_cost, current_price, ticker_symbol FROM assets WHERE asset_id = ?",
                                              [asset_id_to_buy], one=True)
                    
                    if not existing_asset:
                        flash("Asset to simulate buy for not found.", "error")
                    elif existing_asset['current_price'] is None:
                        flash(f"Current price for {existing_asset['ticker_symbol']} is not available. Please refresh asset data.", "warning")
                    else:
                        current_asset_price = existing_asset['current_price']
                        shares_purchased = 0.0
                        cost_of_purchase = 0.0
                        
                        valid_input_provided = False
                        if investment_amount_str:
                            investment_amount = float(investment_amount_str)
                            if investment_amount <= 0:
                                flash("Investment Amount must be positive.", "warning")
                            else:
                                shares_purchased = investment_amount / current_asset_price
                                cost_of_purchase = shares_purchased * current_asset_price 
                                valid_input_provided = True
                        elif shares_to_buy_str:
                            shares_purchased = float(shares_to_buy_str)
                            if shares_purchased <= 0:
                                flash("Number of Shares to Buy must be positive.", "warning")
                            else:
                                cost_of_purchase = shares_purchased * current_asset_price
                                valid_input_provided = True
                        
                        if valid_input_provided and shares_purchased > 0:
                            current_quantity = existing_asset['quantity'] or 0
                            current_total_invested = existing_asset['total_invested'] or 0
                            
                            new_total_quantity = current_quantity + shares_purchased
                            new_total_invested_for_asset = current_total_invested + cost_of_purchase
                            new_average_cost = new_total_invested_for_asset / new_total_quantity if new_total_quantity > 0 else 0
                            
                            new_current_total_value = new_total_quantity * current_asset_price
                            new_profit_loss_dollars = new_current_total_value - new_total_invested_for_asset
                            new_profit_loss_percent = (new_profit_loss_dollars / new_total_invested_for_asset) * 100 if new_total_invested_for_asset > 0 else 0.0

                            current_asset_value = (existing_asset['quantity'] or 0) * (existing_asset['current_price'] or 0)
                            current_profit_loss_dollars = current_asset_value - (existing_asset['total_invested'] or 0)
                            current_profit_loss_percent = (current_profit_loss_dollars / (existing_asset['total_invested'] or 1)) * 100 if (existing_asset['total_invested'] or 0) > 0 else 0.0

                            buy_simulation_results = { # This will make the form visible
                                'asset_id': asset_id_to_buy,
                                'ticker_symbol': existing_asset['ticker_symbol'],
                                'shares_purchased': shares_purchased,
                                'cost_of_purchase': cost_of_purchase,
                                'new_total_quantity': new_total_quantity,
                                'new_total_invested': new_total_invested_for_asset,
                                'new_average_cost': new_average_cost,
                                'new_current_total_value': new_current_total_value,
                                'new_profit_loss_dollars': new_profit_loss_dollars,
                                'new_profit_loss_percent': new_profit_loss_percent,
                                'current_profit_loss_dollars': current_profit_loss_dollars, 
                                'current_profit_loss_percent': current_profit_loss_percent  
                            }
                            flash(f"Buy simulation calculated.", "info")
                        elif not valid_input_provided and not (investment_amount_str or shares_to_buy_str): # Only flash if both are truly empty
                             flash("No input provided for buy simulation (Amount or Shares).", "error")
                except ValueError:
                    flash("Invalid number for Investment Amount or Shares to Buy.", "error")
                except Exception as e:
                    flash(f"An error occurred during buy simulation: {e}", "error")
                    print(f"Error during buy simulation: {e}")

    assets_query = """
        SELECT asset_id, ticker_symbol, name, quantity, average_cost, total_invested, 
               current_price, price_yesterday, fifty_two_week_high, fifty_two_week_low, account_id 
        FROM assets 
        WHERE account_id = ? 
        ORDER BY ticker_symbol;
    """
    assets_db_rows = query_db(assets_query, [account_id])
    
    assets_list_for_template = []
    if assets_db_rows:
        for asset_row in assets_db_rows:
            asset_item = dict(asset_row)
            asset_item['total_invested'] = asset_item.get('total_invested', 0.0) or 0.0
            asset_item['quantity'] = asset_item.get('quantity', 0.0) or 0.0
            
            asset_item['current_value'] = 0.0
            if asset_item.get('current_price') is not None:
                asset_item['current_value'] = asset_item['quantity'] * asset_item['current_price']
            
            asset_item['profit_loss_dollars'] = asset_item['current_value'] - asset_item['total_invested']
            
            if asset_item['total_invested'] > 0:
                asset_item['profit_loss_percent'] = (asset_item['profit_loss_dollars'] / asset_item['total_invested']) * 100
            else:
                asset_item['profit_loss_percent'] = 0.0

            asset_item['day_change_percent'] = 0.0
            if asset_item.get('current_price') is not None and asset_item.get('price_yesterday') is not None and asset_item['price_yesterday'] > 0:
                asset_item['day_change_percent'] = ((asset_item['current_price'] - asset_item['price_yesterday']) / asset_item['price_yesterday']) * 100
            
            asset_item['percent_to_52_week_high'] = None
            if asset_item.get('current_price') is not None and asset_item.get('fifty_two_week_high') is not None and asset_item['fifty_two_week_high'] > 0:
                asset_item['percent_to_52_week_high'] = ((asset_item['current_price'] - asset_item['fifty_two_week_high']) / asset_item['fifty_two_week_high']) * 100
            
            assets_list_for_template.append(asset_item)


    return render_template('manage_assets.html', 
                           account=account, 
                           assets=assets_list_for_template, 
                           title=f"Manage Assets for {account['account_name']}",
                           sell_simulation_results=sell_simulation_results,
                           # show_sell_form_for_asset_id=show_sell_form_for_asset_id, # Removed
                           buy_simulation_inputs=buy_simulation_inputs, 
                           buy_simulation_results=buy_simulation_results
                           # show_buy_form_for_asset_id=show_buy_form_for_asset_id # Removed
                           ) 


@app.route('/asset/<int:asset_id>/edit', methods=['GET', 'POST'])
def edit_asset(asset_id):
    asset_query = """
        SELECT assets.*, accounts.account_name 
        FROM assets 
        JOIN accounts ON assets.account_id = accounts.account_id
        WHERE assets.asset_id = ?
    """
    asset = query_db(asset_query, [asset_id], one=True)

    if not asset:
        flash("Asset not found.", "error")
        return redirect(url_for('manage_accounts')) 

    parent_account_id = asset['account_id']

    if request.method == 'POST':
        new_ticker_symbol = request.form.get('ticker_symbol', '').strip().upper()
        new_asset_name = request.form.get('asset_name', '').strip() 
        new_quantity_str = request.form.get('quantity', '').strip()
        new_average_cost_str = request.form.get('average_cost', '').strip()
        new_total_invested_str = request.form.get('total_invested', '').strip()
        
        if not all([new_ticker_symbol, new_quantity_str, new_average_cost_str, new_total_invested_str]):
            flash("Ticker, Quantity, Average Cost, and Total Invested are required.", "error")
            return render_template('edit_asset.html', asset=asset, title=f"Edit Asset: {asset['ticker_symbol']}")

        try:
            new_quantity = float(new_quantity_str)
            new_average_cost = float(new_average_cost_str)
            new_total_invested = float(new_total_invested_str)
        except ValueError:
            flash("Invalid number for Quantity, Average Cost, or Total Invested.", "error")
            return render_template('edit_asset.html', asset=asset, title=f"Edit Asset: {asset['ticker_symbol']}")

        if new_quantity <= 0 or new_average_cost < 0 or new_total_invested < 0:
            flash("Quantity must be positive. Costs must be non-negative.", "warning")
            return render_template('edit_asset.html', asset=asset, title=f"Edit Asset: {asset['ticker_symbol']}")

        ticker_changed = new_ticker_symbol != asset['ticker_symbol']
        if ticker_changed:
            conflicting_asset = query_db("SELECT asset_id FROM assets WHERE account_id = ? AND ticker_symbol = ? AND asset_id != ?",
                                         [parent_account_id, new_ticker_symbol, asset_id], one=True)
            if conflicting_asset:
                flash(f"Another asset with ticker '{new_ticker_symbol}' already exists in this account.", "warning")
                return render_template('edit_asset.html', asset=asset, title=f"Edit Asset: {asset['ticker_symbol']}")
        
        if (not ticker_changed and
            new_asset_name == (asset['name'] or '') and 
            new_quantity == asset['quantity'] and
            new_average_cost == asset['average_cost'] and
            new_total_invested == asset['total_invested']):
            flash("No changes detected for the manually entered asset details.", "info")
            return redirect(url_for('manage_account_assets', account_id=parent_account_id))

        try:
            update_asset_query = """UPDATE assets SET 
                                    ticker_symbol = ?, name = ?, quantity = ?, 
                                    average_cost = ?, total_invested = ? 
                                  WHERE asset_id = ?"""
            rows_affected = query_db(update_asset_query,
                                     [new_ticker_symbol, new_asset_name if new_asset_name else asset['name'], 
                                      new_quantity, new_average_cost, new_total_invested, 
                                      asset_id])
            
            if rows_affected is not None:
                if rows_affected > 0:
                    flash(f"Asset manual details updated successfully!", "success")
                    if ticker_changed:
                         query_db("""UPDATE assets SET current_price = NULL, price_yesterday = NULL, 
                                     fifty_two_week_high = NULL, fifty_two_week_low = NULL 
                                     WHERE asset_id = ?""", [asset_id])
                         flash("Ticker symbol changed. Market data has been cleared. Please refresh data for new ticker.", "info")
                else:
                    flash(f"Asset manual details were not updated (no rows affected).", "info")
            else:
                flash(f"Failed to update asset manual details. Database error occurred.", "error")
        except Exception as e:
            flash(f"An error occurred while updating asset: {e}", "error")
            print(f"Error updating asset {asset_id}: {e}")
        
        return redirect(url_for('manage_account_assets', account_id=parent_account_id))

    return render_template('edit_asset.html', asset=asset, title=f"Edit Asset: {asset['ticker_symbol']} in {asset['account_name']}")

@app.route('/asset/<int:asset_id>/delete', methods=['POST'])
def delete_asset(asset_id):
    asset_to_delete = query_db("SELECT account_id, ticker_symbol FROM assets WHERE asset_id = ?", [asset_id], one=True)
    
    if not asset_to_delete:
        flash("Asset not found or already deleted.", "error")
        return redirect(url_for('manage_accounts')) 

    parent_account_id = asset_to_delete['account_id']
    asset_ticker = asset_to_delete['ticker_symbol']

    try:
        rows_affected = query_db("DELETE FROM assets WHERE asset_id = ?", [asset_id])
        if rows_affected is not None and rows_affected > 0:
            flash(f"Asset '{asset_ticker}' deleted successfully!", "success")
        elif rows_affected == 0:
             flash(f"Asset '{asset_ticker}' not found or already deleted.", "warning")
        else: 
            flash(f"Failed to delete asset '{asset_ticker}'. Database error occurred.", "error")
    except Exception as e:
        flash(f"An error occurred while deleting asset: {e}", "error")
        print(f"Error deleting asset {asset_id}: {e}")
        
    return redirect(url_for('manage_account_assets', account_id=parent_account_id))

@app.route('/asset/<int:asset_id>/refresh', methods=['POST'])
def refresh_asset_data(asset_id):
    asset = query_db("SELECT asset_id, ticker_symbol, account_id, name FROM assets WHERE asset_id = ?", [asset_id], one=True)
    if not asset:
        flash("Asset not found.", "error")
        return redirect(request.referrer or url_for('manage_accounts'))

    market_data = fetch_market_data(asset['ticker_symbol'])
    if market_data:
        name_to_update = asset['name'] 
        if market_data.get('name'): 
            if not name_to_update: 
                name_to_update = market_data.get('name')
            
        update_query = """UPDATE assets SET
                            current_price = ?,
                            price_yesterday = ?,
                            fifty_two_week_high = ?,
                            fifty_two_week_low = ?,
                            name = ? 
                          WHERE asset_id = ?"""
        
        rows_affected = query_db(update_query, [
            market_data.get('current_price'),
            market_data.get('price_yesterday'),
            market_data.get('fifty_two_week_high'),
            market_data.get('fifty_two_week_low'),
            name_to_update, 
            asset_id
        ])
        if rows_affected is not None:
            flash(f"Market data for '{asset['ticker_symbol']}' refreshed successfully!", "success")
        else:
            flash(f"Failed to update market data for '{asset['ticker_symbol']}' in database.", "error")
    else:
        flash(f"Could not fetch new market data for '{asset['ticker_symbol']}'. Previous data retained if any.", "warning")

    return redirect(url_for('manage_account_assets', account_id=asset['account_id']))

@app.route('/assets/refresh_all', methods=['POST'])
def refresh_all_assets_data():
    unique_tickers_rows = query_db("SELECT DISTINCT ticker_symbol FROM assets")
    if not unique_tickers_rows:
        flash("No assets found in the database to refresh.", "info")
        return redirect(url_for('index'))

    successful_refreshes = 0
    failed_tickers = []
    updated_tickers_count = 0 

    unique_tickers_to_process = {row['ticker_symbol'] for row in unique_tickers_rows}

    for ticker_symbol in unique_tickers_to_process:
        print(f"Refreshing data for {ticker_symbol}...")
        market_data = fetch_market_data(ticker_symbol)
        if market_data:
            current_asset_names_rows = query_db("SELECT asset_id, name FROM assets WHERE ticker_symbol = ?", [ticker_symbol])
            asset_names_map = {row['asset_id']: row['name'] for row in current_asset_names_rows}
            name_from_api = market_data.get('name')
            
            update_query = """UPDATE assets SET
                                current_price = ?,
                                price_yesterday = ?,
                                fifty_two_week_high = ?,
                                fifty_two_week_low = ?
                              WHERE ticker_symbol = ?"""
            
            rows_affected_price_update = query_db(update_query, [
                market_data.get('current_price'),
                market_data.get('price_yesterday'),
                market_data.get('fifty_two_week_high'),
                market_data.get('fifty_two_week_low'),
                ticker_symbol
            ])

            if rows_affected_price_update is not None: 
                updated_tickers_count +=1
                for asset_id, current_db_name in asset_names_map.items():
                    if name_from_api and not current_db_name: 
                        query_db("UPDATE assets SET name = ? WHERE asset_id = ?", [name_from_api, asset_id])
            else: 
                failed_tickers.append(ticker_symbol)
        else:
            failed_tickers.append(ticker_symbol)
            print(f"Failed to fetch data for {ticker_symbol}")

    # Also refresh the USD/CAD exchange rate
    current_exchange_rate = fetch_live_exchange_rate("CAD=X") # Fetches USD to CAD
    if current_exchange_rate:
        query_db("INSERT OR REPLACE INTO app_settings (setting_key, setting_value) VALUES (?, ?)",
                 ['usd_to_cad_exchange_rate', str(current_exchange_rate)])
        flash(f"USD/CAD exchange rate updated to {current_exchange_rate:.4f}.", "info")
    else:
        flash("Could not refresh USD/CAD exchange rate.", "warning")


    if updated_tickers_count > 0:
        flash(f"Market data refresh attempted for {len(unique_tickers_to_process)} unique tickers. Data updated for {updated_tickers_count} tickers.", "success")
    if failed_tickers:
        unique_failed_tickers = sorted(list(set(failed_tickers))) 
        flash(f"Failed to fetch/update data for tickers: {', '.join(unique_failed_tickers)}", "error")
    if updated_tickers_count == 0 and not failed_tickers and unique_tickers_rows:
         flash("No asset data needed an update or failed to update.", "info")
        
    return redirect(url_for('index'))


if __name__ == '__main__':
    db_dir = os.path.dirname(DATABASE_FILE)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        print(f"Created database directory: {db_dir}")
    app.run(debug=True)

