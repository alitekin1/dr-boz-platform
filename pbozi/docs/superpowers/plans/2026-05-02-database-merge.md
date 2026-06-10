# Database Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge source database (/root/bozgpt/backups/jgpti_source_before_merge.db) into target database (/root/bozgpt/backend/jgpti.db) with zero data loss and correct foreign key re-mapping.

**Architecture:** A Python script using `sqlite3` to perform a multi-pass merge. First pass merges users and creates a mapping. Subsequent passes merge dependent tables in dependency order, updating foreign keys using the mappings.

**Tech Stack:** Python, sqlite3

---

### Task 1: Initialize Merge Script and Merge Users

**Files:**
- Create: `/root/bozgpt/backend/merge_databases.py`

- [ ] **Step 1: Write initial script structure and user merge logic**

```python
import sqlite3
import json
from datetime import datetime

SOURCE_DB = '/root/bozgpt/backups/jgpti_source_before_merge.db'
TARGET_DB = '/root/bozgpt/backend/jgpti.db'

def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def merge_users(source_conn, target_conn):
    print("Merging users...")
    source_users = source_conn.execute("SELECT * FROM user_preferences").fetchall()
    user_map = {} # source_id -> target_id
    
    for s_user in source_users:
        tg_id = s_user['telegram_user_id']
        t_user = target_conn.execute("SELECT * FROM user_preferences WHERE telegram_user_id = ?", (tg_id,)).fetchone()
        
        if t_user:
            # Aggregate balances
            new_balance = (t_user['credit_balance_usd'] or 0.0) + (s_user['credit_balance_usd'] or 0.0)
            new_total_charged = (t_user['total_charged_usd'] or 0.0) + (s_user['total_charged_usd'] or 0.0)
            
            # Update learning preferences if source is newer (using updated_at or completed_at)
            # For simplicity, if source has it and target doesn't, or source updated_at is newer
            update_fields = {
                "credit_balance_usd": new_balance,
                "total_charged_usd": new_total_charged
            }
            
            s_updated = s_user['updated_at'] or s_user['created_at']
            t_updated = t_user['updated_at'] or t_user['created_at']
            
            if s_updated and (not t_updated or s_updated > t_updated):
                for field in s_user.keys():
                    if field.startswith('learning_preferences_') or field in ['custom_personalization', 'preferred_name']:
                        if s_user[field] is not None:
                            update_fields[field] = s_user[field]
            
            sql = "UPDATE user_preferences SET " + ", ".join([f"{k} = ?" for k in update_fields.keys()]) + " WHERE id = ?"
            target_conn.execute(sql, list(update_fields.values()) + [t_user['id']])
            user_map[s_user['id']] = t_user['id']
        else:
            # Insert new user
            cols = [k for k in s_user.keys() if k != 'id']
            sql = f"INSERT INTO user_preferences ({', '.join(cols)}) VALUES ({', '.join(['?' for _ in cols])})"
            cursor = target_conn.execute(sql, [s_user[k] for k in cols])
            user_map[s_user['id']] = cursor.lastrowid
            
    print(f"Mapped {len(user_map)} users.")
    return user_map

# ... (main execution block)
```

- [ ] **Step 2: Commit initial script**

```bash
git add backend/merge_databases.py
git commit -m "feat: initial merge script with user merging logic"
```

### Task 2: Implement Generic Table Merge and Wallet Logic

**Files:**
- Modify: `/root/bozgpt/backend/merge_databases.py`

- [ ] **Step 1: Add `merge_wallets` and `merge_table` functions**

```python
def merge_wallets(source_conn, target_conn, user_map):
    print("Merging wallets...")
    source_wallets = source_conn.execute("SELECT * FROM wallets").fetchall()
    wallet_map = {}
    
    for s_wallet in source_wallets:
        t_user_id = user_map.get(s_wallet['user_id'])
        if not t_user_id: continue
        
        t_wallet = target_conn.execute("SELECT * FROM wallets WHERE user_id = ? AND currency = ?", (t_user_id, s_wallet['currency'])).fetchone()
        
        if t_wallet:
            # Aggregate balances
            new_balance = t_wallet['balance_minor'] + s_wallet['balance_minor']
            new_available = t_wallet['available_minor'] + s_wallet['available_minor']
            new_held = t_wallet['held_minor'] + s_wallet['held_minor']
            
            target_conn.execute(
                "UPDATE wallets SET balance_minor = ?, available_minor = ?, held_minor = ?, version = version + 1 WHERE id = ?",
                (new_balance, new_available, new_held, t_wallet['id'])
            )
            wallet_map[s_wallet['id']] = t_wallet['id']
        else:
            cols = [k for k in s_wallet.keys() if k != 'id']
            vals = [s_wallet[k] if k != 'user_id']
            # Wait, easier to reconstruct:
            vals = []
            for k in cols:
                if k == 'user_id': vals.append(t_user_id)
                else: vals.append(s_wallet[k])
                
            sql = f"INSERT INTO wallets ({', '.join(cols)}) VALUES ({', '.join(['?' for _ in cols])})"
            cursor = target_conn.execute(sql, vals)
            wallet_map[s_wallet['id']] = cursor.lastrowid
            
    return wallet_map

def merge_table(table_name, source_conn, target_conn, fk_mappings, unique_keys=None):
    """
    fk_mappings: { 'column_name': map_dict }
    unique_keys: list of columns to check for existing records
    """
    print(f"Merging table {table_name}...")
    source_rows = source_conn.execute(f"SELECT * FROM {table_name}").fetchall()
    row_map = {}
    added_count = 0
    
    for s_row in source_rows:
        # Check if exists if unique_keys provided
        if unique_keys:
            where_clause = " AND ".join([f"{k} = ?" for k in unique_keys])
            where_vals = [s_row[k] for k in unique_keys]
            t_row = target_conn.execute(f"SELECT id FROM {table_name} WHERE {where_clause}", where_vals).fetchone()
            if t_row:
                row_map[s_row['id']] = t_row['id']
                continue

        cols = [k for k in s_row.keys() if k != 'id']
        vals = []
        skip_row = False
        for k in cols:
            val = s_row[k]
            if k in fk_mappings:
                mapped_val = fk_mappings[k].get(val)
                if val is not None and mapped_val is None:
                    # Foreign key missing in target, might be a dangling ref or we missed a table
                    print(f"Warning: {table_name}.{k}={val} not found in map. Skipping row.")
                    skip_row = True
                    break
                val = mapped_val
            vals.append(val)
        
        if skip_row: continue
        
        sql = f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({', '.join(['?' for _ in cols])})"
        cursor = target_conn.execute(sql, vals)
        row_map[s_row['id']] = cursor.lastrowid
        added_count += 1
        
    print(f"Added {added_count} rows to {table_name}.")
    return row_map
```

- [ ] **Step 2: Commit changes**

```bash
git add backend/merge_databases.py
git commit -m "feat: add generic merge_table and wallet merging logic"
```

### Task 3: Execute Full Merge Order

**Files:**
- Modify: `/root/bozgpt/backend/merge_databases.py`

- [ ] **Step 1: Implement full merge execution in `main`**

```python
def main():
    s_conn = get_connection(SOURCE_DB)
    t_conn = get_connection(TARGET_DB)
    
    try:
        user_map = merge_users(s_conn, t_conn)
        wallet_map = merge_wallets(s_conn, t_conn, user_map)
        
        # Dependency order
        # 1. providers (match by name)
        provider_map = merge_table('providers', s_conn, t_conn, {}, unique_keys=['name'])
        
        # 2. models (match by name)
        model_map = merge_table('models', s_conn, t_conn, {'provider_id': provider_map}, unique_keys=['name'])
        
        # 3. projects
        project_map = merge_table('projects', s_conn, t_conn, {'owner_user_id': user_map})
        
        # 4. system_prompts (match by name)
        prompt_map = merge_table('system_prompts', s_conn, t_conn, {}, unique_keys=['name'])
        
        # 5. chats
        chat_map = merge_table('chats', s_conn, t_conn, {
            'project_id': project_map,
            'model_id': model_map,
            'user_preference_id': user_map
        })
        
        # 6. documents
        document_map = merge_table('documents', s_conn, t_conn, {'project_id': project_map})
        
        # 7. uploaded_files
        file_map = merge_table('uploaded_files', s_conn, t_conn, {
            'user_id': user_map,
            'chat_id': chat_map,
            'project_id': project_map
        })
        
        # 8. messages
        message_map = merge_table('messages', s_conn, t_conn, {'chat_id': chat_map})
        
        # 9. usage_events
        usage_map = merge_table('usage_events', s_conn, t_conn, {
            'user_id': user_map,
            'chat_id': chat_map,
            'message_id': message_map,
            'uploaded_file_id': file_map,
            'provider_id': provider_map,
            'model_id': model_map
        })
        
        # 10. credit_ledger_entries
        ledger_map = merge_table('credit_ledger_entries', s_conn, t_conn, {
            'user_id': user_map,
            'wallet_id': wallet_map,
            'usage_event_id': usage_map
        })
        
        # 11. telegram_groups
        group_map = merge_table('telegram_groups', s_conn, t_conn, {
            'created_by_user_id': user_map,
            'app_chat_id': chat_map
        }, unique_keys=['telegram_chat_id'])
        
        # 12. telegram_group_members
        merge_table('telegram_group_members', s_conn, t_conn, {
            'group_id': group_map,
            'user_id': user_map
        })
        
        # 13. group_usage_events
        group_usage_map = merge_table('group_usage_events', s_conn, t_conn, {
            'group_id': group_map,
            'usage_event_id': usage_map,
            'triggered_by_user_id': user_map
        })
        
        # 14. group_usage_shares
        merge_table('group_usage_shares', s_conn, t_conn, {
            'group_usage_event_id': group_usage_map,
            'group_id': group_map,
            'user_id': user_map,
            'ledger_entry_id': ledger_map
        })
        
        # 15. tool_calls
        merge_table('tool_calls', s_conn, t_conn, {
            'chat_id': chat_map,
            'message_id': message_map
        })
        
        # 16. feedback_entries
        merge_table('feedback_entries', s_conn, t_conn, {
            'user_id': user_map,
            'chat_id': chat_map,
            'message_id': message_map
        })
        
        # 17. admin_actions
        merge_table('admin_actions', s_conn, t_conn, {
            'admin_user_id': user_map
        })
        
        t_conn.commit()
        print("Merge completed successfully.")
        
    except Exception as e:
        t_conn.rollback()
        print(f"Error during merge: {e}")
        raise
    finally:
        s_conn.close()
        t_conn.close()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

Run: `python3 backend/merge_databases.py`
Expected: Output showing rows added per table and "Merge completed successfully."

- [ ] **Step 3: Commit and clean up**

```bash
git add backend/merge_databases.py
git commit -m "feat: complete database merge logic and execute"
rm /root/bozgpt/source_schema.txt /root/bozgpt/target_schema.txt /root/bozgpt/db_comparison.json /root/bozgpt/inspect_schemas.py /root/bozgpt/target_tables_info.txt
```

---
