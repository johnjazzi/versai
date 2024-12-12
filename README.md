
###terminal 1
npm run dev

### terminal 2
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
