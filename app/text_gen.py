#### THIS CODE IS NOT USED RIGHT NOW


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



@app.post("/predict")
async def predict_translation(request: Request):
    return {"message": "will run"}
    

hf_api_key = os.environ.get("HUGGING_FACE_TOKEN")

#my_model_path = "app/MobileLLM-600M/MobileLLM-600M.Q8_0.gguf"
my_model_path = "app/models/qwen2.5-0.5b-instruct-fp16.gguf"
CONTEXT_SIZE = 512

zephyr_model = Llama(model_path=my_model_path,
                    n_ctx=CONTEXT_SIZE)

def generate_text_from_prompt(user_prompt,
                             max_tokens = 150,
                             temperature = 0.01,
                             top_p = 0.9,
                             echo = False,
                             stop = ["Q", "\n"]):

   # Define the parameters
   model_output = zephyr_model(
       user_prompt,
       max_tokens=max_tokens,
       temperature=temperature,
       top_p=top_p,
       echo=echo,
       stop=stop,
   )

   return model_output



def predict_and_translate(text: str):
    # Refined prompt to encourage unique responses
    prompt = (
        "You are a multilingual translator. "
        "Translate the following text to Portuguese (Brazilian) and provide both the predicted and translated sentences. "
        f"Text: '{text}'."
    )
    
    # Adjust parameters for better diversity
    result = generate_text_from_prompt(prompt, max_tokens=150, temperature=0.7, top_p=0.9)
    print("Model Output:", result)

    # Check if the output is structured as expected
    if 'choices' in result and len(result['choices']) > 0:
        return {"message": result['choices'][0]['text']}
    else:
        return {"error": "No valid response from the model."}