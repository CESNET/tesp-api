from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
import shutil

app = FastAPI()

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    with open(f"data/{file.filename}", "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"message": "File uploaded successfully."}

@app.get("/download/{filename}")
async def download_file(filename: str):
    return FileResponse(f"data/{filename}", headers={"Content-Disposition": f"attachment; filename={filename}"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

