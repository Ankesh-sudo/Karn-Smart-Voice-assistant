from datetime import datetime

def route_query(text: str):

    text = text.lower()

    if "hello" in text:
        return "Hello Ankesh. Karn backend is active."

    if "your name" in text:
        return "I am Karn, your intelligent assistant."

    if "time" in text:
        return f"The current time is {datetime.now().strftime('%H:%M')}"

    return f"You said: {text}"