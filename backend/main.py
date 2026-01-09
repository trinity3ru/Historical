"""
API на FastAPI для анализа исторических объектов.
Шаг 2: добавлен эндпоинт /analyze, валидация файла и вызов Gemini.
"""

import logging
import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, Field
from PIL import Image

# Загружаем переменные окружения из .env, чтобы не хранить ключ в коде.
# Загружаем переменные окружения из .env, чтобы не хранить ключ в коде.
load_dotenv()

GEMINI_API_KEY: Final[str | None] = os.getenv("GEMINI_API_KEY")
MAX_FILE_SIZE: Final[int] = 5 * 1024 * 1024  # 5 MB ограничение на учебный проект
ALLOWED_TYPES: Final[set[str]] = {"image/png", "image/jpeg", "image/webp"}

# Создаём клиент Gemini один раз.
if GEMINI_API_KEY:
    genai_client = genai.Client(api_key=GEMINI_API_KEY)
else:
    genai_client = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("historical-backend")


class HealthResponse(BaseModel):
    status: str
    has_api_key: bool


class HistoricalObject(BaseModel):
    objectName: str = Field(..., description="Название объекта")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность 0-1")
    description: str = Field(..., description="Краткое описание")


class AnalyzeResponse(BaseModel):
    objects: list[HistoricalObject]


app = FastAPI(
    title="Historical Object Finder API",
    description="API для анализа изображений с помощью Gemini",
    version="0.2.0",
)

# Разрешаем CORS, чтобы фронтенд мог обращаться к API с другого домена/порта.
# Для учебного проекта allow_origins="*" допустимо, в проде лучше перечислять домены.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """
    Простой health-check.
    Отдельно показываем, видит ли процесс переменную GEMINI_API_KEY,
    чтобы удобнее диагностировать окружение.
    """
    return HealthResponse(status="ok", has_api_key=bool(GEMINI_API_KEY))


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_image(file: UploadFile = File(...)) -> AnalyzeResponse:
    """
    Принимает изображение, валидирует, вызывает Gemini и возвращает список объектов.
    """
    if genai_client is None:
        logger.error("GEMINI_API_KEY is not set")
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY не задан")

    if file.content_type not in ALLOWED_TYPES:
        logger.warning("Unsupported content type: %s", file.content_type)
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый тип файла: {file.content_type}",
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        logger.warning("Empty file received")
        raise HTTPException(status_code=400, detail="Файл пустой")
    if len(raw_bytes) > MAX_FILE_SIZE:
        logger.warning("File too large: %s bytes", len(raw_bytes))
        raise HTTPException(status_code=400, detail="Файл слишком большой (лимит 5MB)")

    # Пробуем нормализовать изображение через Pillow, чтобы избежать ошибок
    # "Unable to process input image" от Gemini при нестандартных файловых структурах.
    try:
        with Image.open(BytesIO(raw_bytes)) as img:
            rgb_img = img.convert("RGB")
            buf = BytesIO()
            rgb_img.save(buf, format="PNG")
            normalized_bytes = buf.getvalue()
            normalized_mime = "image/png"
            logger.info(
                "Image normalized: orig_size=%s normalized_size=%s mode=%s format=%s",
                len(raw_bytes),
                len(normalized_bytes),
                img.mode,
                img.format,
            )
    except Exception as pillow_err:  # noqa: BLE001
        logger.exception("Pillow failed to process image")
        raise HTTPException(
            status_code=400,
            detail=f"Не удалось обработать изображение (Pillow): {pillow_err}",
        ) from pillow_err

    # Временное сохранение на диск (учебная демонстрация) и базовая очистка.
    suffix = Path(file.filename or "").suffix or ".img"
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(normalized_bytes)
            tmp_path = tmp.name

        prompt = (
            "Analyze the image to identify historical objects. "
            "For each historical object found, provide its name, your confidence "
            "level (0 to 1), and a brief description. "
            "If no such objects are found, return an empty array."
        )

        image_part = genai_types.Part.from_bytes(
            data=normalized_bytes, mime_type=normalized_mime
        )
        text_part = genai_types.Part.from_text(prompt)

        # Описываем схему, которую просим у модели.
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "objectName": {"type": "string"},
                    "confidence": {"type": "number"},
                    "description": {"type": "string"},
                },
                "required": ["objectName", "confidence", "description"],
            },
        }

        response = genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                {
                    "role": "user",
                    "parts": [image_part, text_part],
                }
            ],
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
            },
        )

        text = (response.text or "").strip()
        logger.info(
            "Gemini response length=%s status=%s",
            len(text),
            getattr(response, "prompt_feedback", None),
        )
        if not text:
            return AnalyzeResponse(objects=[])

        try:
            import json

            parsed = json.loads(text)
        except Exception as parse_err:  # noqa: BLE001
            # Документируем ошибку, чтобы в UI можно было подсказать пользователю.
            raise HTTPException(
                status_code=502,
                detail=f"Не удалось разобрать ответ модели как JSON: {parse_err}",
            ) from parse_err

        objects: list[HistoricalObject] = []
        if isinstance(parsed, list):
            for item in parsed:
                try:
                    objects.append(HistoricalObject(**item))
                except Exception:
                    # Пропускаем некорректные элементы, оставшиеся вернём.
                    logger.warning("Skip invalid item from model response: %s", item)
                    continue

        return AnalyzeResponse(objects=objects)

    except HTTPException:
        raise
    except Exception as err:  # noqa: BLE001
        # Логируем сжатое описание ошибки для диагностики.
        logger.exception("Unexpected error during analysis")
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {err}") from err
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                # Если файл не удалился, просто продолжаем; на учебном проекте допустимо.
                logger.warning("Failed to delete temp file: %s", tmp_path)
                pass

