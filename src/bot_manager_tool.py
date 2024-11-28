# src/bot_manager_tool.py

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database.db_manager import DatabaseManager
from database.models import Bot
from src.twitter_poster import post_or_reply_to_tweet, create_api



sys.path.append(str(Path(__file__).resolve().parent.parent))

# Check individual bot configuration
def check_bots_config():
    db = DatabaseManager()
    bots = db.get_active_bots()
    
    if not bots:
        print("\n❌ No active bots found.")
        return
    
    print("\n=== List of Active Clients ===")
    for index, bot in enumerate(bots, 1):
        print(f"{index}. {bot.name}")
    print("-" * 50)
    
    try:
        choice = int(input("\nSelect a bot to view its information (or 0 to cancel): "))
        if choice == 0:
            print("Operation canceled.")
            return
        if 1 <= choice <= len(bots):
            selected_bot = bots[choice - 1]
            print("\n=== Configuration of the Selected Bot ===")
            print(f"Bot: {selected_bot.name}")
            print("-" * 50)
            print(f"ID: {selected_bot.id}")
            print(f"Identity: {selected_bot.identity[:50]}...")
            print(f"RSS URL: {selected_bot.rss_url}")
            print("API Keys:")
            print(f"- API Key: {'✓' if selected_bot.api_key else '✗'} ({len(selected_bot.api_key) if selected_bot.api_key else 0} characters)")
            print(f"- API Secret: {'✓' if selected_bot.api_secret else '✗'} ({len(selected_bot.api_secret) if selected_bot.api_secret else 0} characters)")
            print(f"- Access Token: {'✓' if selected_bot.access_token else '✗'} ({len(selected_bot.access_token) if selected_bot.access_token else 0} characters)")
            print(f"- Access Token Secret: {'✓' if selected_bot.access_token_secret else '✗'} ({len(selected_bot.access_token_secret) if selected_bot.access_token_secret else 0} characters)")
            print(f"- Bearer Token: {'✓' if selected_bot.bearer_token else '✗'} ({len(selected_bot.bearer_token) if selected_bot.bearer_token else 0} characters)")
            print(f"Status: {'Active' if selected_bot.is_active else 'Inactive'}")
            print("-" * 50)
        else:
            print("\n❌ Invalid number. Please choose a number from the list.")
    except ValueError:
        print("\n❌ Please enter a valid number.")
    except Exception as e:
        print(f"\n❌ Error: {e}")

# List Bots
def list_bots():
    db = DatabaseManager()
    session = db.get_session()
    try:
        bots = session.query(Bot).all()
        if not bots:
            print("\nNo bots in the database.")
            return []
            
        print("\nList of available bots:")
        print("-" * 50)
        for index, bot in enumerate(bots, 1):
            status = "🟢 Active" if bot.is_active else "🔴 Inactive"
            print(f"{index}. {bot.name} (ID: {bot.id}) - {status}")
        print("-" * 50)
        return bots
    finally:
        session.close()

# Delete Bot Interactively
def delete_bot_interactive():
    db = DatabaseManager()
    bots = list_bots()
    
    if not bots:
        return
    
    while True:
        choice = input("\nEnter the number of the bot to delete (or 'q' to quit): ")
        
        if choice.lower() == 'q':
            print("Operation canceled.")
            return
            
        try:
            index = int(choice)
            if 1 <= index <= len(bots):
                bot = bots[index-1]
                # Ask for confirmation
                confirm = input(f"\n⚠️  Are you sure you want to delete the bot '{bot.name}'? (y/n): ")
                if confirm.lower() == 'y':
                    success = db.delete_bot(bot.name)
                    if success:
                        print(f"\n✅ Bot '{bot.name}' successfully deleted!")
                    else:
                        print(f"\n❌ Error deleting bot '{bot.name}'")
                else:
                    print("\nDeletion canceled.")
                break
            else:
                print("\n❌ Invalid number. Please choose a number from the list.")
        except ValueError:
            print("\n❌ Please enter a valid number.")
        except Exception as e:
            print(f"\n❌ Error: {e}")

# Fix Bot IDs
def fix_bot_ids():
    db = DatabaseManager()
    session = db.get_session()
    try:
        bots = session.query(Bot).order_by(Bot.id).all()
        
        print("\nResetting bot IDs...")
        for new_id, bot in enumerate(bots, 1):
            old_id = bot.id
            bot.id = new_id
            print(f"{bot.name}: {old_id} -> {new_id}")
            
        session.commit()
        print("✅ IDs successfully corrected!")
        return True
        
    except Exception as e:
        print(f"❌ Error correcting IDs: {e}")
        session.rollback()
        return False
    finally:
        session.close()

# Swap Bot Order
def swap_bot_order():
    db = DatabaseManager()
    session = db.get_session()
    try:
        list_bots()
        
        bot1_id = int(input("\nEnter the ID of the first bot: "))
        bot2_id = int(input("Enter the ID of the second bot: "))
        
        bot1 = session.query(Bot).filter_by(id=bot1_id).first()
        bot2 = session.query(Bot).filter_by(id=bot2_id).first()
        
        if not bot1 or not bot2:
            print("❌ One or both bots not found. Please fix IDs and try again.")
            fix_bot_ids()
            return
        
        print(f"\nSwapping bots:")
        print(f"1. {bot1.name} (ID: {bot1.id})")
        print(f"2. {bot2.name} (ID: {bot2.id})")
        
        with session.no_autoflush:
            temp_id = 9999
            bot1.id = temp_id
            session.commit()

            bot1.id = bot2_id
            bot2.id = bot1_id
            session.commit()
        
        print("\n✅ Bot order swapped successfully!")
        print("\n🔄 Fixing IDs after swap...")
        fix_bot_ids()
        
    except ValueError:
        print("\n❌ Please enter valid numbers.")
    except Exception as e:
        print(f"\n❌ Error swapping bot order: {e}")
        session.rollback()
        print("Attempting to fix IDs...")
        fix_bot_ids()
    finally:
        session.close()

# Main Menu
def main():
    while True:
        print("\n=== Bot Manager Tool ===")
        print("1. Check Bot Configurations")
        print("2. List Bots")
        print("3. Delete a Bot")
        print("4. Swap Bot Order")
        print("5. Fix Bot IDs")
        print("6. Exit")
        
        choice = input("\nYour choice (1-6): ")
        
        if choice == '1':
            check_bots_config()
        elif choice == '2':
            list_bots()
        elif choice == '3':
            delete_bot_interactive()
        elif choice == '5':
            fix_bot_ids()
        elif choice == '4':
            swap_bot_order()
        elif choice == '6':
            print("\nGoodbye!")
            break
        else:
            print("\n❌ Invalid choice. Please select between 1 and 6.")

if __name__ == "__main__":
    main()