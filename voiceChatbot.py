# import speech_recognition as sr
# import threading
# import pygame
# import os
# import tempfile
# import time
# from google import genai
# from google.genai import types
# # import google.generativeai as genai
# # from gtts import gTTS

from google import genai
from google.genai import types
import speech_recognition as sr
import threading
import pygame
import os
import tempfile
import time
from gtts import gTTS


# CONFIGURATION

GEMINI_API_KEY = "AIzaSyAZSLLkUnKeH23FHn7wxOL68pBkUwdotSg "   # ← paste your key here


# SETUP

# genai.configure(api_key=GEMINI_API_KEY)

# Use Gemini 1.5 Flash — fast and conversational
# model = genai.GenerativeModel(
#     model_name="gemini-1.5-flash",
#     system_instruction=(
#         "You are a helpful, friendly voice assistant. "
#         "Keep your responses concise and conversational since they will be spoken aloud. "
#         "Avoid using bullet points, markdown, asterisks, or long lists. "
#         "Speak naturally as if in a real conversation."
#     )
# )
client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = (
    "You are a helpful, friendly voice assistant. "
    "Keep your responses concise and conversational since they will be spoken aloud. "
    "Avoid using bullet points, markdown, asterisks, or long lists. "
    "Speak naturally as if in a real conversation."
)

conversation_history = []

# Start a persistent chat session (maintains conversation history automatically)
# chat_session = model.start_chat(history=[])

recognizer = sr.Recognizer()
recognizer.energy_threshold = 300
recognizer.pause_threshold = 0.8

pygame.mixer.init()

interrupt_flag = threading.Event()



# STEP 1: Listen to user's voice

def listen():
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



# STEP 2: Send text to Gemini and get reply
# The translated text you provide goes here
# as part of the conversation flow.

# def ask_gemini(user_text):
#     """
#     Sends user_text (which can be translated text or raw speech)
#     to Gemini and returns the assistant's reply.
#     """
#     try:
#         response = chat_session.send_message(user_text)
#         reply = response.text.strip()

#         # Clean up any leftover markdown symbols that sneak through
#         reply = reply.replace("*", "").replace("#", "").replace("`", "")

#     except Exception as e:
#         reply = "Sorry, I had trouble getting a response right now."
#         print(f"Gemini error: {e}")

#     print(f"Assistant: {reply}")
#     return reply

# def ask_gemini(user_text):
#     conversation_history.append(
#         types.Content(role="user", parts=[types.Part(text=user_text)])
#     )

#     try:
#         response = client.models.generate_content(
#             model="gemini-2.0-flash-lite",
#             contents=conversation_history,
#             config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
#         )
#         reply = response.text.strip().replace("*", "").replace("#", "").replace("`", "")

#         conversation_history.append(
#             types.Content(role="model", parts=[types.Part(text=reply)])
#         )

#     except Exception as e:
#         reply = "Sorry, I had trouble getting a response right now."
#         print(f"Gemini error: {e}")

#     print(f"Assistant: {reply}")
#     return reply

import time

def ask_gemini(user_text):
    conversation_history.append(
        types.Content(role="user", parts=[types.Part(text=user_text)])
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",   # ← switched model
                contents=conversation_history,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
            )
            reply = response.text.strip().replace("*", "").replace("#", "").replace("`", "")

            conversation_history.append(
                types.Content(role="model", parts=[types.Part(text=reply)])
            )
            print(f"Assistant: {reply}")
            return reply

        except Exception as e:
            error_str = str(e)
            if "429" in error_str and attempt < max_retries - 1:
                wait_time = 60  # wait 60 seconds before retrying
                print(f"[Rate limited] Waiting {wait_time}s before retry {attempt+2}/{max_retries}...")
                time.sleep(wait_time)
            else:
                print(f"Gemini error: {e}")
                return "Sorry, I had trouble getting a response right now."


# STEP 3: Convert text to speech using gTTS

def speak(text):
    """
    Converts text to speech and plays it.
    Stops immediately if the interrupt_flag is set
    (i.e., the user starts speaking while AI is talking).
    """
    interrupt_flag.clear()

    try:
        tts = gTTS(text=text, lang="en", slow=False)
    except Exception as e:
        print(f"[TTS Error] {e}")
        return

    # Save to a temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        temp_path = f.name

    try:
        tts.save(temp_path)
    except Exception as e:
        print(f"[TTS Save Error] {e}")
        return

    # Play the audio
    pygame.mixer.music.load(temp_path)
    pygame.mixer.music.play()

    # Wait while playing — stop immediately if interrupted
    while pygame.mixer.music.get_busy():
        if interrupt_flag.is_set():
            pygame.mixer.music.stop()
            print("[Interrupted — listening to you...]")
            break
        time.sleep(0.05)

    # Small gap after speaking finishes
    time.sleep(0.2)

    # Cleanup
    try:
        os.remove(temp_path)
    except Exception:
        pass



# STEP 4: Background thread that detects
# if you speak while the AI is talking

def interruption_listener():
    """
    Runs in the background. If the user starts speaking
    while the AI is playing audio, it sets interrupt_flag
    so speak() stops immediately.
    """
    interrupt_recognizer = sr.Recognizer()
    interrupt_recognizer.energy_threshold = 1500
    interrupt_recognizer.dynamic_energy_threshold = False  # prevent auto-adjustment

    while True:
        if pygame.mixer.music.get_busy():
            try:
                with sr.Microphone() as source:
                    # Short listen window — just enough to detect speech
                    audio = interrupt_recognizer.listen(
                        source, timeout=1, phrase_time_limit=1
                    )
                    # If we captured audio while AI was speaking → interrupt
                    interrupt_flag.set()
            except Exception:
                pass
        else:
            time.sleep(0.1)



# STEP 5: (Optional) Inject translated text
# If you have pre-translated text you want
# to feed into the chatbot, call this.

def process_translated_input(translated_text: str):
    """
    Use this function to pass translated text directly
    to the Gemini model instead of voice input.
    The model will generate a response and speak it aloud.

    Example usage:
        process_translated_input("What is the weather like today?")
    """
    print(f"[Translated Input]: {translated_text}")
    reply = ask_gemini(translated_text)
    speak(reply)



# STEP 6: Main conversation loop

def main():
    print("=" * 55)
    print("  Gemini Voice Chatbot — say 'goodbye' to exit")
    print("  Supports interruption: just speak while it talks!")
    print("=" * 55)

        # ← ADD THIS TEMPORARILY
    print("Available models:")
    for model in client.models.list():
        print(model.name)
    # ← REMOVE AFTER CHECKING

    # Start interruption detector in background
    interrupt_thread = threading.Thread(target=interruption_listener, daemon=True)
    interrupt_thread.start()

    # Greet the user
    speak("Hello! I'm your voice assistant powered by Gemini. How can I help you today?")

    while True:
        user_input = listen()

        if user_input is None:
            continue

        # Exit condition
        if any(word in user_input.lower() for word in ["goodbye", "bye", "exit", "quit", "stop"]):
            speak("Goodbye! Have a great day!")
            break

        # ── If you want to pass translated text instead of raw speech,
        #    replace `user_input` below with your translated string, e.g.:
        #    translated = your_translation_function(user_input)
        #    ai_reply = ask_gemini(translated)

        ai_reply = ask_gemini(user_input)
        speak(ai_reply)


if __name__ == "__main__":
    main()