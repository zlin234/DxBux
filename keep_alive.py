from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "I'm alive"

def keep_alive():
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8080}).start()
