from groq import Groq
import speech_recognition as sr
import threading
import pygame
import os
import tempfile
import time
from gtts import gTTS


# ─────────────────────────────────────────
#  CONFIGURATION — paste your Groq key here
# ─────────────────────────────────────────
GROQ_API_KEY = "paste key in here"   # ← get from console.groq.com

# Model options (all free on Groq):
#   "llama-3.3-70b-versatile"   ← smartest, best for conversation
#   "llama-3.1-8b-instant"      ← fastest, lightweight
#   "mixtral-8x7b-32768"        ← good alternative
MODEL = "llama-3.3-70b-versatile"


# ─────────────────────────────────────────
#  SETUP
# ─────────────────────────────────────────
client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = (
    "You are a helpful, friendly voice assistant. "
    "Keep your responses concise and conversational since they will be spoken aloud. "
    "Avoid using bullet points, markdown, asterisks, or long lists. "
    "Speak naturally as if in a real conversation. "
    "Limit responses to 2-3 sentences unless more detail is truly needed."
)

# Conversation history — kept in memory for the session
conversation_history = [
    {"role": "system", "content": SYSTEM_PROMPT}
]

recognizer = sr.Recognizer()
recognizer.energy_threshold = 300
recognizer.pause_threshold = 0.8

pygame.mixer.init()

interrupt_flag = threading.Event()


# ─────────────────────────────────────────
#  STEP 1: Listen to user's voice
# ─────────────────────────────────────────
def listen():
    """Captures microphone input and converts it to text."""
    with sr.Microphone() as source:
        print("\n[Listening...] Speak now.")
        recognizer.adjust_for_ambient_noise(source, duration=0.3)
        try:
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
            text = recognizer.recognize_google(audio)
            print(f"You: {text}")
            return text
        except sr.WaitTimeoutError:
            print("(No speech detected, trying again...)")
            return None
        except sr.UnknownValueError:
            print("(Couldn't understand, please repeat)")
            return None
        except sr.RequestError:
            print("(Internet error — check your connection)")
            return None


# ─────────────────────────────────────────
#  STEP 2: Send text to Groq and get reply
# ─────────────────────────────────────────
def ask_groq(user_text):
    """
    Sends user_text to the Groq LLM and returns the assistant's reply.
    Maintains full conversation history so context is preserved.

    You can also call this directly with translated text:
        reply = ask_groq("What is the capital of France?")
    """
    # Append the user's message to history
    conversation_history.append({"role": "user", "content": user_text})

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=conversation_history,
            max_tokens=300,       # keep responses short for voice
            temperature=0.7,      # natural, slightly creative tone
        )

        reply = response.choices[0].message.content.strip()

        # Remove any markdown that slips through
        reply = reply.replace("*", "").replace("#", "").replace("`", "").replace("_", "")

        # Save assistant reply to history for context
        conversation_history.append({"role": "assistant", "content": reply})

    except Exception as e:
        reply = "Sorry, I had trouble getting a response right now."
        print(f"[Groq Error]: {e}")

    print(f"Assistant: {reply}")
    return reply


# ─────────────────────────────────────────
#  STEP 3: Convert text to speech (gTTS)
# ─────────────────────────────────────────
def speak(text):
    """
    Converts text to speech and plays it via pygame.
    Stops immediately if interrupt_flag is set (user spoke while AI was talking).
    """
    interrupt_flag.clear()

    try:
        tts = gTTS(text=text, lang="en", slow=False)
    except Exception as e:
        print(f"[TTS Error]: {e}")
        return

    # Save audio to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        temp_path = f.name

    try:
        tts.save(temp_path)
    except Exception as e:
        print(f"[TTS Save Error]: {e}")
        return

    # Play the audio
    pygame.mixer.music.load(temp_path)
    pygame.mixer.music.play()

    # Monitor playback — stop if interrupted
    while pygame.mixer.music.get_busy():
        if interrupt_flag.is_set():
            pygame.mixer.music.stop()
            print("[Interrupted — listening to you...]")
            break
        time.sleep(0.05)

    time.sleep(0.2)  # brief pause after speaking

    # Cleanup temp file
    try:
        os.remove(temp_path)
    except Exception:
        pass


# ─────────────────────────────────────────
#  STEP 4: Background interruption detector
# ─────────────────────────────────────────
def interruption_listener():
    """
    Runs in a background thread.
    If the user speaks while the AI is talking, sets interrupt_flag
    so speak() stops the audio immediately.
    """
    interrupt_recognizer = sr.Recognizer()
    interrupt_recognizer.energy_threshold = 1500
    interrupt_recognizer.dynamic_energy_threshold = False

    while True:
        if pygame.mixer.music.get_busy():
            try:
                with sr.Microphone() as source:
                    audio = interrupt_recognizer.listen(
                        source, timeout=1, phrase_time_limit=1
                    )
                    # Audio detected while AI was speaking → interrupt
                    interrupt_flag.set()
            except Exception:
                pass
        else:
            time.sleep(0.1)


# ─────────────────────────────────────────
#  STEP 5: Inject pre-translated text
# ─────────────────────────────────────────
def process_translated_input(translated_text: str):
    """
    Use this function to feed translated text directly into the chatbot
    instead of raw voice input. The model will respond and speak aloud.

    Example:
        process_translated_input("What is the weather like today?")
        process_translated_input("Tell me a joke.")
    """
    print(f"[Translated Input]: {translated_text}")
    reply = ask_groq(translated_text)
    speak(reply)


# ─────────────────────────────────────────
#  STEP 6: Main conversation loop
# ─────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Groq Voice Chatbot — say 'goodbye' to exit")
    print(f"  Model: {MODEL}")
    print("  Interruption: speak while it talks to stop it!")
    print("=" * 55)

    # Start background interruption detector
    interrupt_thread = threading.Thread(target=interruption_listener, daemon=True)
    interrupt_thread.start()

    # Greet the user
    speak("Hello! I'm your voice assistant powered by Groq. How can I help you today?")

    while True:
        user_input = listen()

        if user_input is None:
            continue

        # ── EXIT condition ──
        if any(word in user_input.lower() for word in ["goodbye", "bye", "exit", "quit", "stop"]):
            speak("Goodbye! Have a great day!")
            break

        # ── OPTION A: Use raw voice input (default) ──
        ai_reply = ask_groq(user_input)

        # ── OPTION B: Use translated text instead ──
        # Uncomment below and comment out the line above if you're
        # piping translated text from another part of your system:
        #
        #   translated = your_translation_function(user_input)
        #   ai_reply = ask_groq(translated)

        speak(ai_reply)


if __name__ == "__main__":
    main()


