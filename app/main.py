from fastapi import FastAPI, Request, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocketState
import asyncio
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional
from faster_whisper import WhisperModel
import json
import io
import threading
import time
import subprocess
from datetime import datetime

import transformers
import ctranslate2


app = FastAPI()
executor = ThreadPoolExecutor(max_workers=12)


class AudioProcessor:
    def __init__(self):
        print("init audio processor")
        self.current_task: Optional[Future] = None
        self.model = WhisperModel("small", device="cpu", compute_type="float32")
        self.last_prediction_time = datetime.now()
        self.cancel_flag = threading.Event()  # Use an event for cancellation

    def cancel_current_task(self):
        # cancel the tasks but if its been more than 5 seconds, dont cancel it an let at least 1 through.
        if (datetime.now() - self.last_prediction_time).total_seconds() < 2:
            if self.current_task and not self.current_task.done():
                self.cancel_flag.set()  # Set the cancel flag
                print("Cancelled previous processing task")

    def process_audio(self, audio_data, websocket: WebSocket):
        start_time = datetime.now()
        """Process audio data in a separate thread"""
        audio_file = io.BytesIO(audio_data)
        segments, info = self.model.transcribe(
            audio_file, 
            beam_size=5
        )
        
        text_out = []
        for segment in segments:
            if self.cancel_flag.is_set():
                print("Processing cancelled")
                return None, None  # Exit early if cancelled
            text_out.append(segment.text)
            print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))

        self.last_prediction_time = datetime.now()
        time_taken = self.last_prediction_time - start_time
        print(f"Transcription Took: {time_taken} milliseconds")

        start_time = datetime.now()
        translate_out = translator.translate_text(" ".join(text_out), source_lang=info.language)
        end_time = datetime.now()
        time_taken = end_time - start_time
        print(f"Translation Took: {time_taken} milliseconds")

        print(translate_out)

        if websocket and websocket.client_state == WebSocketState.CONNECTED:
            print("sending response")
            response = {    
                "message": json.dumps(text_out),
                "info": json.dumps(info.language),
                "translation": json.dumps(translate_out)
            }
            asyncio.run( websocket.send_json(response))
           

        return 
    
    async def send_response(self, websocket: WebSocket, text_out, info, translate_out):
        # This function will handle sending the response back to the client
        if websocket.client_state == WebSocketState.CONNECTED:
            response = {    
                "message": json.dumps(text_out),
                "info": json.dumps(info.language),
                "translation": json.dumps(translate_out)
            }
            await websocket.send_json(response)
    

class Translator: 
    def __init__(self):
        print("init translator")
        self.current_task: Optional[Future] = None
        self.translator = ctranslate2.Translator("./app/models/nllb-200-distilled-600M")
        self.tokenizer_eng = transformers.AutoTokenizer.from_pretrained("facebook/nllb-200-distilled-600M", src_lang="eng_Latn")
        self.tokenizer_por = transformers.AutoTokenizer.from_pretrained("facebook/nllb-200-distilled-600M", src_lang="por_Latn")
        self.language_map = {
            "en": "eng_Latn",
            "pt": "por_Latn"
        }
        self.last_prediction_time = datetime.now()
        self.cancel_flag = threading.Event()  # Use an event for cancellation

    def translate_text(self, text, source_lang="en", target_lang="pt"):
        start_time = datetime.now()

        if source_lang == "en":
            tokenizer = self.tokenizer_eng
            target_lang = "pt"
        else:
            tokenizer = self.tokenizer_por
            target_lang = "en"

        source = tokenizer.convert_ids_to_tokens(tokenizer.encode(text))
        target_prefix = [self.language_map[target_lang]]
        results = self.translator.translate_batch([source], target_prefix=[target_prefix])
        target = results[0].hypotheses[0][1:]

        return tokenizer.decode(tokenizer.convert_tokens_to_ids(target))


audio_processor = AudioProcessor()
translator = Translator()

#warm up the model
# TODO: have warm settings be in configs
# print("warming up models")
# warm_up_audio = open('./app/tests/table.m4a', 'rb').read()
# audio_processor.process_audio(warm_up_audio, None)
# warm_up_text = "welcome to advance python"
# translator.translate_text(warm_up_text, source_lang="en", target_lang="pt")
# print("models warmed up")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)


@app.get("/")
def read_root():
    return {"message": "Translator backend is running!"}


model_size = "small"
model = WhisperModel(model_size, device="cpu", compute_type="float32")
data = None
transcript = []
last_transcription = None


async def audio_handler(websocket: WebSocket):
    global data
    global transcript
    global last_transcription
    data = None # reset the data state for next connection

    try:
        await websocket.accept()  # Ensure the WebSocket is accepted
        while True:
            try:

                ## attempt to decode
                message = await asyncio.wait_for(websocket.receive_bytes(), timeout=10.0)
                if message == b'{"reset":true}':
                    transcript.append(last_transcription)
                    data = None
                    print("resetting chunk")
                    continue

                if data == None:
                    data = message
                else:
                    data = data + message

            except asyncio.TimeoutError:
                print("No data received for 10 seconds, closing connection.")
                data = None
                if websocket.client_state == WebSocketState.CONNECTED:  # Check if connected before closing
                    await websocket.close()
                break  # Exit the loop if no data is received within the timeout
            
            except WebSocketDisconnect:
                data = None
                if websocket.client_state == WebSocketState.CONNECTED:  # Check if connected before closing
                    await websocket.close()
                print("Client disconnected")
                break  # Break the loop on WebSocket disconnect

            print("Received audio data, length:", len(data))
            print()

            if not data:
                print("Received empty audio data, skipping processing.")
                continue

            if not data.startswith(b'\x1A\x45\xDF\xA3'):
                print("Received data is not in the expected WebM format.")
                continue

            thread = threading.Thread(
                target=audio_processor.process_audio, 
                args=(data, websocket)
            )
            thread.start()

    except WebSocketDisconnect:
        print("Client disconnected")
    finally:
        print("WebSocket connection closed")
        data = None  # Reset the data state for next connection


@app.get("/translate")
def translate_text(text: str, source_lang: str, target_lang: str):
    return translator.translate_text(text, source_lang, target_lang)


@app.websocket("/audio")
async def websocket_endpoint(websocket: WebSocket):
    await audio_handler(websocket)
    

@app.on_event("shutdown")
def shutdown_event():
    executor.shutdown(wait=True)  # Wait for all threads to finish
