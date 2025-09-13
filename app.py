import io
import os
import base64
from flask import Flask, render_template, request, jsonify
from gtts import gTTS
from PyPDF2 import PdfReader
import docx
from deep_translator import GoogleTranslator
from openai import OpenAI
from ibm_watson import TextToSpeechV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

app = Flask(__name__)

# -----------------------
# OpenAI Client
# -----------------------
API_KEY = "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"
client = OpenAI(api_key=API_KEY)

# -----------------------
# IBM Watson TTS Setup
# -----------------------
IBM_API_KEY = "your-ibm-api-key"
IBM_URL = "your-ibm-service-url"

ibm_authenticator = IAMAuthenticator(IBM_API_KEY)
ibm_tts = TextToSpeechV1(authenticator=ibm_authenticator)
ibm_tts.set_service_url(IBM_URL)


# -----------------------
# Helpers
# -----------------------
def extract_text_from_file(uploaded_file) -> str:
    filename = uploaded_file.filename.lower()
    if filename.endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="ignore")
    elif filename.endswith(".pdf"):
        reader = PdfReader(uploaded_file)
        return "".join([page.extract_text() or "" for page in reader.pages])
    elif filename.endswith(".docx"):
        doc = docx.Document(uploaded_file)
        return "\n".join([para.text for para in doc.paragraphs])
    return ""


def synthesize_with_ibm(text: str) -> bytes:
    try:
        response = ibm_tts.synthesize(
            text,
            voice="en-US_AllisonV3Voice",
            accept="audio/mp3"
        ).get_result()
        return response.content
    except Exception as e:
        # fallback to gTTS if IBM fails
        print(f"IBM TTS failed: {e}, falling back to gTTS")
        return synthesize_with_gtts(text)


def synthesize_with_gtts(text: str) -> bytes:
    tts = gTTS(text=text, lang="en", slow=False)
    mp3_buf = io.BytesIO()
    tts.write_to_fp(mp3_buf)
    mp3_buf.seek(0)
    return mp3_buf.read()


def translate_text(text: str, target_lang: str) -> str:
    try:
        return GoogleTranslator(source="auto", target=target_lang).translate(text)
    except Exception:
        return text


def rewrite_text_with_tone(text, tone):
    if tone == "Neutral":
        return text
    elif tone == "Suspenseful":
        return f"🔦 The atmosphere grows tense...\n{text}\n...What happens next?"
    elif tone == "Inspiring":
        return f"✨ Believe in yourself! {text} 🌟"
    elif tone == "Happy":
        return f"😊 Here’s something cheerful: {text}"
    elif tone == "Sad":
        return f"😢 A somber moment: {text}"
    elif tone == "Excited":
        return f"🔥 Wow! {text} 🎉"
    return text


def to_base64(audio_bytes: bytes) -> str:
    return base64.b64encode(audio_bytes).decode("utf-8")


# -----------------------
# Routes
# -----------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/text2audio", methods=["GET", "POST"])
def text2audio():
    if request.method == "POST":
        text_input = request.form.get("text", "")
        tone = request.form.get("tone", "Neutral")
        translate_target = request.form.get("translate", None)

        if not text_input.strip():
            return jsonify({"error": "No text provided"}), 400

        processed_text = rewrite_text_with_tone(text_input, tone)

        if translate_target and translate_target != "none":
            processed_text = translate_text(processed_text, translate_target)

        audio_bytes = synthesize_with_ibm(processed_text)
        return jsonify({
            "audio_base64": to_base64(audio_bytes),
            "voice_lang_name": "English",
            "translate_lang_name": (
                GoogleTranslator().get_supported_languages(as_dict=True).get(translate_target, "None")
                if translate_target and translate_target != "none" else "None"
            )
        })

    return render_template(
        "text2audio.html",
        tts_langs={"en": "English"},
        translate_langs=GoogleTranslator().get_supported_languages(as_dict=True)
    )


@app.route("/file2audio", methods=["GET", "POST"])
def file2audio():
    if request.method == "POST":
        file = request.files.get("file")
        tone = request.form.get("tone", "Neutral")
        translate_target = request.form.get("translate", None)

        if not file:
            return jsonify({"error": "No file uploaded"}), 400

        text_input = extract_text_from_file(file)
        if not text_input.strip():
            return jsonify({"error": "Empty file or unsupported format"}), 400

        processed_text = rewrite_text_with_tone(text_input, tone)

        if translate_target and translate_target != "none":
            processed_text = translate_text(processed_text, translate_target)

        audio_bytes = synthesize_with_ibm(processed_text)
        return jsonify({
            "audio_base64": to_base64(audio_bytes),
            "voice_lang_name": "English",
            "translate_lang_name": (
                GoogleTranslator().get_supported_languages(as_dict=True).get(translate_target, "None")
                if translate_target and translate_target != "none" else "None"
            )
        })

    return render_template(
        "file2audio.html",
        tts_langs={"en": "English"},
        translate_langs=GoogleTranslator().get_supported_languages(as_dict=True)
    )


@app.route("/assistant", methods=["GET", "POST"])
def assistant():
    if request.method == "POST":
        command = request.form.get("command", "")
        tone = request.form.get("tone", "Neutral")
        translate_target = request.form.get("translate", None)

        if not command.strip():
            return jsonify({"error": "No command provided"}), 400

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": command}]
            )
            generated_text = response.choices[0].message.content.strip()
        except Exception as e:
            return jsonify({"error": f"OpenAI error: {str(e)}"}), 500

        processed_text = rewrite_text_with_tone(generated_text, tone)

        if translate_target and translate_target != "none":
            processed_text = translate_text(processed_text, translate_target)

        audio_bytes = synthesize_with_ibm(processed_text)
        return jsonify({
            "audio_base64": to_base64(audio_bytes),
            "voice_lang_name": "English",
            "translate_lang_name": (
                GoogleTranslator().get_supported_languages(as_dict=True).get(translate_target, "None")
                if translate_target and translate_target != "none" else "None"
            )
        })

    return render_template(
        "assistant.html",
        tts_langs={"en": "English"},
        translate_langs=GoogleTranslator().get_supported_languages(as_dict=True)
    )


if __name__ == "__main__":
    app.run(debug=True)
