#!/usr/bin/env python3
"""Voice-cloning server for the Talking Portrait page ("เซิร์ฟเวอร์ของตัวเอง").

API (CORS enabled, so index.html can call it from the browser):
  GET  /health                              -> {"ok": true, "mode": "f5" | "mock"}
  POST /clone   multipart: name, file       -> {"voice_id": "..."}
  POST /tts     JSON {voice_id, text, language} -> audio/wav

Run:
  pip install fastapi uvicorn python-multipart
  python3 tools/voice_server.py --mock            # no model: /tts returns the reference clip
  pip install f5-tts                              # needs an NVIDIA GPU for usable speed
  python3 tools/voice_server.py --ckpt path/to/model.safetensors --vocab path/to/vocab.txt

For Thai, point --ckpt/--vocab at a community Thai F5-TTS checkpoint. The F5-TTS
path has not been run in this repository's tests; only --mock has.
ffmpeg must be installed to accept browser recordings (webm/ogg/m4a).
"""
import argparse, io, json, os, re, shutil, subprocess, uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=8000)
ap.add_argument("--data", default="voice_data", help="folder for reference clips")
ap.add_argument("--mock", action="store_true", help="no model; /tts echoes the reference clip")
ap.add_argument("--model", default="F5TTS_v1_Base")
ap.add_argument("--ckpt", default="")
ap.add_argument("--vocab", default="")
ap.add_argument("--origin", action="append", default=[],
                help="allowed page origin (repeatable); default allows any origin")
args = ap.parse_args()

os.makedirs(args.data, exist_ok=True)
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=args.origin or ["*"], allow_methods=["*"], allow_headers=["*"])

_tts = None


def engine():
    global _tts
    if _tts is None:
        from f5_tts.api import F5TTS  # imported lazily so --mock needs no model
        kw = {"model": args.model}
        if args.ckpt:
            kw["ckpt_file"] = args.ckpt
        if args.vocab:
            kw["vocab_file"] = args.vocab
        _tts = F5TTS(**kw)
    return _tts


def to_wav(src, dst):
    """Convert any browser audio to 24 kHz mono wav; plain wav is copied if ffmpeg is missing."""
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", "24000", dst], check=True)
    elif src.lower().endswith(".wav"):
        shutil.copyfile(src, dst)
    else:
        raise HTTPException(400, "install ffmpeg to accept this audio format")


def voice_path(voice_id):
    if not re.fullmatch(r"[0-9a-f]{32}", voice_id or ""):
        raise HTTPException(404, "unknown voice_id")
    p = os.path.join(args.data, voice_id + ".wav")
    if not os.path.exists(p):
        raise HTTPException(404, "unknown voice_id")
    return p


@app.get("/health")
def health():
    return {"ok": True, "mode": "mock" if args.mock else "f5"}


@app.post("/clone")
async def clone(name: str = Form(""), file: UploadFile = File(...)):
    vid = uuid.uuid4().hex
    ext = os.path.splitext(file.filename or "")[1].lower() or ".bin"
    raw = os.path.join(args.data, vid + ".src" + ext)
    with open(raw, "wb") as f:
        f.write(await file.read())
    try:
        to_wav(raw, os.path.join(args.data, vid + ".wav"))
    finally:
        os.remove(raw)
    with open(os.path.join(args.data, vid + ".json"), "w", encoding="utf-8") as f:
        json.dump({"name": name}, f, ensure_ascii=False)
    return {"voice_id": vid}


class TTSReq(BaseModel):
    voice_id: str
    text: str
    language: str = "th"


@app.post("/tts")
def tts(req: TTSReq):
    ref = voice_path(req.voice_id)
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "text is empty")
    if args.mock:
        with open(ref, "rb") as f:
            return Response(f.read(), media_type="audio/wav")
    out = os.path.join(args.data, uuid.uuid4().hex + ".out.wav")
    try:
        # empty ref_text lets F5-TTS transcribe the reference clip itself
        engine().infer(ref_file=ref, ref_text="", gen_text=text, file_wave=out)
        with open(out, "rb") as f:
            return Response(f.read(), media_type="audio/wav")
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"detail": {"message": str(e)}}, status_code=500)
    finally:
        if os.path.exists(out):
            os.remove(out)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)
