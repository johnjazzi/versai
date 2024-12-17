
### terminal 1
```
npm install
npm run dev
```

### terminal 2
```
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### convert facebook to 

```
ct2-transformers-converter --model facebook/nllb-200-distilled-600M --quantization int8_float32 --output_dir app/model/nllb-200-distilled-600M-int8_float32
```