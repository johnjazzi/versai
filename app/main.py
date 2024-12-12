from fastapi import FastAPI, Request, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import time
from openai import OpenAI
import os
from typing import Optional
from llama_cpp import Llama
from faster_whisper import WhisperModel
import io
from pydub import AudioSegment

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

last_request_id: Optional[int] = None
last_response: Optional[JSONResponse] = None


async def debounce_predict(request_id: int, request: Request):
    global last_request_id, last_response
    # Wait for a short period to allow for debouncing
    await asyncio.sleep(0.5)
    # Check if the current request is the last one
    if request_id == last_request_id:
        request_data = await request.json()
        last_response = JSONResponse(predict_and_translate(request_data.get('text')))
    else:
        last_response = JSONResponse(content={"message": "debounced"})


@app.get("/")
def read_root():
    return {"message": "Translator backend is running!"}


@app.post("/")
async def process_request(request: Request):
    global last_request_id, last_response
    # Increment the request ID
    last_request_id = (last_request_id or 0) + 1
    current_request_id = last_request_id

    # Run the debounce logic
    await debounce_predict(current_request_id, request)

    # Return the response for the current request
    return last_response




model_size = "tiny"
model = WhisperModel(model_size, device="cpu", compute_type="float32")


# print("Transcribing...")
# segments, info = model.transcribe("app/tests/table.m4a", beam_size=5)
# print("Detected language '%s' with probability %f" % (info.language, info.language_probability))
# for segment in segments:
#     print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))

print("Transcribing...")
segments, info = model.transcribe("app/tests/received_audio.webm", beam_size=5)
print("Detected language '%s' with probability %f" % (info.language, info.language_probability))
for segment in segments:
    print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))



async def audio_handler(websocket: WebSocket):
    await websocket.accept()  # Accept the WebSocket connection
    try:
        while True:
            try:
                # Set a timeout for receiving data

                data = await websocket.receive_bytes()
                print("Received audio data, length:", len(data))

                # Check if the received data is empty
                if not data:
                    print("Received empty audio data, skipping processing.")
                    continue  # Skip processing if data is empty

                print("Received audio data (first 20 bytes):", data[:20])

                if not data.startswith(b'\x1A\x45\xDF\xA3'):
                    print("Received data is not in the expected WebM format.")
                    continue  # Skip processing if data is not valid

                with open("received_audio.webm", "wb") as audio_file:  
                        audio_file.write(data)  

                audio_file = io.BytesIO(data)
                # Now you can process the mp3_buffer as needed
                # For example, you can save it or transcribe it
                segments, info = model.transcribe(audio_file, beam_size=5)

                print("Detected language '%s' with probability %f" % (info.language, info.language_probability))

                for segment in segments:
                    print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))

                response = {"message": "Audio processed"}
                await websocket.send_json(response)  # Send a response back to the client
            finally:
                print("done")
            # except asyncio.TimeoutError():
            #     print("No data received for 5 seconds, stopping processing.")
            #     break  # Exit the loop without closing the connection
    except WebSocketDisconnect:
        print("Client disconnected")

@app.websocket("/audio")
async def websocket_endpoint(websocket: WebSocket):
    await audio_handler(websocket)
    
    