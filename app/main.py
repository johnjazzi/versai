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

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=1)

class AudioProcessor:
    def __init__(self):
        self.current_task: Optional[Future] = None
        self.model = WhisperModel("small", device="cpu", compute_type="float32")
        self.last_prediction_time = 0
        self.cancel_flag = threading.Event()  # Use an event for cancellation

    def cancel_current_task(self):
        # cancel the tasks but if its been more than 5 seconds, dont cancel it an let at least 1 through.
        if time.time() - self.last_prediction_time > 5:
            if self.current_task and not self.current_task.done():
                self.cancel_flag.set()  # Set the cancel flag
                print("Cancelled previous processing task")

    def process_audio(self, audio_data):
        """Process audio data in a separate thread"""
        audio_file = io.BytesIO(audio_data)
        segments, info = self.model.transcribe(audio_file, beam_size=5)
        
        text_out = []
        for segment in segments:
            if self.cancel_flag.is_set():
                print("Processing cancelled")
                return None, None  # Exit early if cancelled
            text_out.append(segment.text)
            print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))
        
        self.last_prediction_time = time.time()
        self.cancel_flag.clear()  # Clear the flag after processing
        return text_out, info

audio_processor = AudioProcessor()

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
data = 1

# print("Transcribing...")
# segments, info = model.transcribe("app/tests/table.m4a", beam_size=5)
# print("Detected language '%s' with probability %f" % (info.language, info.language_probability))
# for segment in segments:
#     print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))



async def audio_handler(websocket: WebSocket):
    global data

    try:
        await websocket.accept()  # Ensure the WebSocket is accepted
        while True:
            try:

                ## attempt to decode
                message = await asyncio.wait_for(websocket.receive_bytes(), timeout=10.0)
                if message == b'{"reset":true}':
                    data = 1
                    print("resetting chunk")
                    continue

                if data == 1:
                    data = message
                else:
                    data = data + message

            except asyncio.TimeoutError:
                print("No data received for 10 seconds, closing connection.")
                data = 1 
                if websocket.client_state == WebSocketState.CONNECTED:  # Check if connected before closing
                    await websocket.close()
                break  # Exit the loop if no data is received within the timeout
            
            except WebSocketDisconnect:
                data = 1 
                if websocket.client_state == WebSocketState.CONNECTED:  # Check if connected before closing
                    await websocket.close()
                print("Client disconnected")
                break  # Break the loop on WebSocket disconnect

            except Exception as e:
                print(f"{e}")
                try:
                    message = await websocket.receive_text()
                    print(message)
                    print("printing at websocket recive line 106" , message['type'])
                    if message['reset'] == True:
                        data = 1
                except Exception as e:
                    print(f"Error receiving data: {e}")
                    data = 1
                    if websocket.client_state == WebSocketState.CONNECTED:  # Check if connected before closing
                        await websocket.close()
                    break

            print("Received audio data, length:", len(data))

            if not data:
                print("Received empty audio data, skipping processing.")
                continue

            if not data.startswith(b'\x1A\x45\xDF\xA3'):
                print("Received data is not in the expected WebM format.")
                continue

            # Process audio in a separate thread
            audio_processor.cancel_current_task() # cancel the current task
            loop = asyncio.get_event_loop()
            audio_processor.current_task = loop.run_in_executor(
                executor, 
                audio_processor.process_audio, 
                data
            )

            try:
                text_out, info = await audio_processor.current_task
                print("Detected language '%s' with probability %f" % (info.language, info.language_probability))
                response = {"message": json.dumps(text_out)}
                if websocket.client_state == WebSocketState.CONNECTED:
                    response = {"message": json.dumps(text_out)}
                    await websocket.send_json(response)
                else:
                    print("WebSocket is not connected, skipping send.")

            except asyncio.CancelledError:
                print("Processing was cancelled due to new data")
                continue
            except Exception as e:
                print(f"Error processing audio: {e}")
                continue
            finally:
                print("Processing complete")

    except WebSocketDisconnect:
        print("Client disconnected")
    finally:
        print("WebSocket connection closed")
        data = 1  # Reset the data state for next connection

@app.websocket("/audio")
async def websocket_endpoint(websocket: WebSocket):
    await audio_handler(websocket)
    

@app.on_event("shutdown")
def shutdown_event():
    executor.shutdown(wait=True)  # Wait for all threads to finish
