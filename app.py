# app.py
from flask import Flask
import threading
from bot import client, worker  # Import from your actual bot

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def start_bot():
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(worker())
    client.start()
    client.run_until_disconnected()

if __name__ == '__main__':
    threading.Thread(target=start_bot).start()
    app.run(host='0.0.0.0', port=10000)
