# init_db.py
import sqlite3
import os

DATABASE_DIR = 'database'
DATABASE_NAME = 'investment_tracker.db'
DATABASE_FILE = os.path.join(DATABASE_DIR, DATABASE_NAME)

def create_connection():
    conn = None
    try:
        os.makedirs(DATABASE_DIR, exist_ok=True)
        conn = sqlite3.connect(DATABASE_FILE)
        print(f"SQLite version: {sqlite3.sqlite_version}")
        print(f"Successfully connected to database at {DATABASE_FILE}")
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
    return conn

def create_table(conn, create_table_sql):
    try:
        c = conn.cursor()
        c.execute(create_table_sql)
        print(f"Executed: {create_table_sql.splitlines()[0]}...")
    except sqlite3.Error as e:
        print(f"Error creating table: {e}")

def main():
    sql_create_users_table = """ CREATE TABLE IF NOT EXISTS users (
                                        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                                        name TEXT NOT NULL UNIQUE
                                    ); """

    sql_create_platforms_table = """ CREATE TABLE IF NOT EXISTS platforms (
                                        platform_id INTEGER PRIMARY KEY AUTOINCREMENT,
                                        name TEXT NOT NULL UNIQUE
                                    ); """

    sql_create_accounts_table = """ CREATE TABLE IF NOT EXISTS accounts (
                                        account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                                        user_id INTEGER NOT NULL,
                                        platform_id INTEGER NOT NULL,
                                        account_type TEXT NOT NULL,
                                        account_name TEXT NOT NULL UNIQUE,
                                        cash_balance REAL DEFAULT 0.0,
                                        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                                        FOREIGN KEY (platform_id) REFERENCES platforms (platform_id) ON DELETE CASCADE
                                    ); """

    sql_create_assets_table = """ CREATE TABLE IF NOT EXISTS assets (
                                    asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    account_id INTEGER NOT NULL,
                                    ticker_symbol TEXT NOT NULL,
                                    name TEXT, 
                                    quantity REAL NOT NULL,
                                    average_cost REAL NOT NULL,     
                                    total_invested REAL NOT NULL, 
                                    current_price REAL,           
                                    price_yesterday REAL,         
                                    fifty_two_week_high REAL,     
                                    fifty_two_week_low REAL,      
                                    notes TEXT,                   
                                    FOREIGN KEY (account_id) REFERENCES accounts (account_id) ON DELETE CASCADE,
                                    UNIQUE(account_id, ticker_symbol) 
                                ); """

    sql_create_app_settings_table = """ CREATE TABLE IF NOT EXISTS app_settings (
                                            setting_key TEXT PRIMARY KEY,
                                            setting_value TEXT
                                        ); """

    sql_create_portfolio_history_table = """ CREATE TABLE IF NOT EXISTS portfolio_history (
                                                snapshot_date TEXT PRIMARY KEY, -- YYYY-MM-DD format
                                                total_portfolio_value REAL NOT NULL
                                            ); """

    conn = create_connection()

    if conn is not None:
        print("\nCreating tables...")
        create_table(conn, sql_create_users_table)
        create_table(conn, sql_create_platforms_table)
        create_table(conn, sql_create_accounts_table)
        create_table(conn, sql_create_assets_table)
        create_table(conn, sql_create_app_settings_table)
        create_table(conn, sql_create_portfolio_history_table) # Add new history table
        
        cursor = conn.cursor()
        cursor.execute("SELECT setting_value FROM app_settings WHERE setting_key = 'target_goal_value'")
        if cursor.fetchone() is None:
            try:
                cursor.execute("INSERT INTO app_settings (setting_key, setting_value) VALUES (?, ?)", 
                               ('target_goal_value', '100000'))
                conn.commit()
                print("Inserted default target_goal_value.")
            except sqlite3.Error as e:
                print(f"Error inserting default goal: {e}")
        
        print("\nAll table creation commands executed.")
        
        conn.close()
        print("Database connection closed.")
    else:
        print("Error! Cannot create the database connection.")

if __name__ == '__main__':
    print("Initializing database schema...")
    main()
    print("Database initialization process finished.")
